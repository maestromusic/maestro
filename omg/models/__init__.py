#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import logging, copy, os
from PyQt4 import QtCore

from omg import tags, database, covers, config, realfiles, absPath, relPath
from omg.database import queries
from functools import reduce
db = database.get()

logger = logging.getLogger(name="omg")

class Node:
    """(Abstract) base class for elements in a RootedTreeModel...that is almost everything in playlists, browser etc.. Node implements the methods required by RootedTreeModel as well as some basic tree-structure methods. To implement getParent, setParent and getChildren, it uses self.parent as parent and self.contents as the list of children, but does not create these variables. Subclasses must either create self.contents and self.parent or overwrite the methods."""
    
    def hasChildren(self):
        """Return whether this node has at least one child node."""
        return len(self.getChildren()) > 0
        
    def getChildren(self):
        """Return the list of children."""
        # This is a default implementation and does not mean that every node has a contents-attribute
        return self.contents
    
    def getChildrenCount(self):
        """Return the number of children or None if it is unknown."""
        return len(self.getChildren())
    
    def getParent(self):
        """Return the parent of this element."""
        # This is a default implementation and does not mean that every node has a parent-attribute
        return self.parent
    
    def setParent(self,parent):
        """Set the parent of this node."""
        # This is a default implementation and does not mean that every node has a parent-attribute
        self.parent = parent
        
    def isFile(self):
        """Return whether this node holds a file. Note that this is in general not the opposite of isContainer as e.g. rootnodes are neither."""
        return False
    
    def isContainer(self):
        """Return whether this node holds a container. Note that this is in general not the opposite of isFile as e.g. rootnodes are neither."""
        return False

    def copy(self,contents=None):
        """Return a copy of this node. All attributes will be copied by reference, with the exception of the list of contents: If this instance contains a content-attribute, the new node will contain a deep copy of it. Note that a shallow copy makes no sense, because the parent-attributes have to be adjusted. If you do not want this behaviour, you may specify the parameter <contents> and the contents will be set to that parameter. The parents of all elements of <contents> will be adjusted in this case, too."""
        newNode = copy.copy(self)
        if contents is None:
            if hasattr(self,'contents'):
                newNode.contents = [node.copy() for node in self.contents]
                for node in newNode.contents:
                    node.setParent(newNode)
        else:
            assert isinstance(contents,list)
            newNode.contents = contents
            for node in newNode.contents:
                node.setParent(newNode)
        return newNode
    
    def getParents(self):
        """Returns a generator yielding all parents of this node in the current tree structure, from the direct parent to the root-node."""
        parent = self.getParent()
        while parent is not None:
            yield parent
            parent = parent.getParent()
    
    def getLevel(self):
        """Return the level of this node in the current tree structure. The root node will have level 0."""
        if self.getParent() is None:
            return 0
        else: return 1 + self.getParent().getLevel()
        
    def index(self,node):
        """Return the index of <node> in this node's contents or raise a ValueError if the node is not found. See also find."""
        contents = self.getChildren()
        for i in range(0,len(contents)):
            if contents[i] == node:
                return i
        raise ValueError("Node.index: Node {0} is not contained in element {1}.".format(node,self))
        
    def find(self,node):
        """Return the index of <node> in this node's contents or -1 if the node is not found. See also index."""
        contents = self.getChildren()
        for i in range(0,len(contents)):
            if contents[i] == node:
                return i
        return -1
        
    def getAllFiles(self):
        """Generator which will return all files contained in this element or in child-elements of it."""
        assert self.getChildren() is not None
        if self.isFile():
            yield self
        else:
            for element in self.getChildren():
                for file in element.getAllFiles():
                    yield file
                        
    def getFileCount(self):
        """Return the number of files contained in this element or in child-elements of it."""
        if self.isFile():
            return 1
        else: return sum(element.getFileCount() for element in self.getChildren())
        
    def getOffset(self):
        """Get the offset of this element in the current tree structure."""
        if self.getParent() is None:
            return 0
        else:
            offset = self.getParent().getOffset()
            for child in self.getParent().getChildren():
                if child == self:
                    return offset
                else: offset = offset + child.getFileCount()
            raise ValueError("Node.getOffset: Node {0} is not contained in its parent {1}."
                                .format(self,self.getParent()))
    
    def getChildOffset(self,childIndex):
        """Return the offset of the child with index <childIndex> in this node."""
        if childIndex < 0 or childIndex >= self.getChildrenCount():
            raise IndexError("childIndex {} is out of bounds.".format(childIndex))
        offset = 0
        for node in self.getChildren()[:childIndex]:
            offset = offset + node.getFileCount()
        return offset
        
    def getFileAtOffset(self,offset):
        """Get the file at the given <offset>. Note that <offset> is relative to this element, not to the whole playlist (unless the element is the rootnode)."""
        assert self.getChildren() is not None
        offset = int(offset)
        if offset == 0 and self.isFile():
            return self
        else: 
            child,innerOffset = self.getChildAtOffset(offset)
            if child.isFile():
                return child
            else: return child.getFileAtOffset(innerOffset)
        
    def getChildIndexAtOffset(self,offset):
        """Return a tuple: the index of the child C that contains the file F with the given offset (relative to this element) and the offset of F relative to C ("inner offset").
        For example: If this element is the rootnode and the playlist contains an album with 13 songs and one with 12 songs, then getChildIndexAtOffset(17) will return (1,3), since the 18th file if the playlist (i.e. with offset 17), is contained in the second album (i.e with index 1) and it is the 4th song on that album (i.e. it has offset 3 relative to the album).
        """
        offset = int(offset)
        if offset < 0:
            raise IndexError("Offset {0} is out of bounds".format(offset))
        cOffset = 0
        for i in range(0,self.getChildrenCount()):
            fileCount = self.getChildren()[i].getFileCount()
            if offset < cOffset + fileCount:
                return i,offset-cOffset
            else: cOffset = cOffset + fileCount
        if offset == cOffset:
            return None,None
        raise IndexError("Offset {0} is out of bounds".format(offset))
    
    def getChildAtOffset(self,offset):
        """Return the child containing the file with the given (relative) offset, and the offset of that file relative to the child. This is a convenience-method for getChildren()[getChildIndexAtOffset(offset)[0]]. Confer getChildIndexAtOffset."""
        index,innerOffset = self.getChildIndexAtOffset(offset)
        if index is None:
            return None,None
        else: return self.getChildren()[index],innerOffset


class RootNode(Node):
    """Rootnode at the top of a RootedTreeModel."""
    def __init__(self):
        self.contents = []
    
    def getParent(self):
        return None
    
    def setParent(self):
        raise RuntimeError("Cannot set the parent of a RootNode.")


class Element(Node):
    """Abstract base class for elements (files or containers) in playlists, browser, etc.. Contains methods to load tags and contents from the database or from files."""
    tags = None # tags.Storage to store the tags. None until they are loaded
    position = None
    length = None
    changesPending = False #if changes were made to the element that have not yet been commited (valid only for DB-elements)
    
    def __init__(self):
        raise RuntimeError(
                "Cannot instantiate abstract base class Element. Use Container, File or models.createElement.")
    
    def isInDB(self):
        """Return whether this element is contained in the database."""
        return self.id is not None
        
    def copy(self,contents=None):
        """Reimplementation of Node.copy: In addition to contents the tags are also not copied by reference. Instead the copy will contain a copy of this node's tags.Storage-instance."""
        newNode = Node.copy(self,contents)
        newNode.tags = self.tags.copy()
        return newNode

    def loadTags(self,recursive=False,tagList=None):
        """Delete the stored tags and load them again. If this element is contained in the DB, tags will be loaded from there. Otherwise if this is a file, tags will be loaded from that file or no tags will be loaded if this is a container. If <recursive> is True, all tags from children of this node (recursively) will be loaded, too. If <tagList> is not None only tags in the given list will be loaded (e.g. only title-tags)."""
        if self.isInDB():
            self.tags = tags.Storage()
            # Prepare a where clause to select only the tags in tagList
            if tagList is not None:
                additionalWhereClause = " AND tag_id IN ({0})".format(",".join(str(tag.id) for tag in tagList))
            else: additionalWhereClause = ''
            result = db.query("""
                SELECT tag_id,value_id 
                FROM tags
                WHERE element_id = {0} {1}
                """.format(self.id,additionalWhereClause))
            for row in result:
                tag = tags.get(row[0])
                value = tag.getValue(row[1])
                if value is None:
                    logger.warning("Database is corrupt: Element {0} has a {1}-tag with id {2} but "
                                  +"this id does not exist in tag_{1}.".format(self.id,tag.name,row[1]))
                    continue
                self.tags[tag].append(value)
        elif self.isFile():
            self.readTagsFromFilesystem()
        else:
            self.tags = tags.Storage()
            
        if recursive:
            for element in self.getChildren():
                element.loadTags(recursive,tagList)
    
    def ensureTagsAreLoaded(self,recursive=False):
        """Load tags if they are not loaded yet."""
        if self.tags is None:
            self.loadTags()
        if recursive:
            for element in self.getChildren():
                element.ensureTagsAreLoaded()
    
    def getPosition(self,refresh=False):
        """Return the position of this element. For elements in the database this is the number from the contents-table, not the index of this element in the parent's list of children! To get the latter, use parent.index(self). The value will be cached and will be only recomputed if <refresh> is True. This method returns None if the element has no parent or the parent is not of type Element.
           For elements outside the DB, you have to take care of self.position directly."""
        if not self.isInDB():
            return self.position
        if (self.position != None) and not refresh:
            return self.position
        else:
            # Without parent, there can't be a position
            if self.parent is None or not isinstance(self.parent,Element) or not self.parent.isInDB():
                return None
            self.position = db.query("SELECT position FROM contents WHERE container_id = ? AND element_id = ?", 
                                 self.parent.id,self.id).getSingle()
            return self.position
    
    def setPosition(self, position):
        if position != self.position:
            self.position = position
            self.changesPending = True
        
    def getParentIds(self,recursive):
        """Return a list containing the ids of all parents of this element from the database. If <recursive> is True all ancestors will be added recursively."""
        if not self.isInDB():
            raise RuntimeError("getParentIds can only be used on elements contained in the database.")
        newList = list(db.query("SELECT container_id FROM contents WHERE element_id = ?",self.id).getSingleColumn())
        if not recursive:
            return newList
        resultList = newList
        while len(newList) > 0:
            newList = list(db.query("""
                    SELECT container_id
                    FROM contents
                    WHERE element_id IN ({0})
                    """.format(",".join(str(n) for n in newList))).getSingleColumn())
            newList = [id for id in newList if id not in resultList] # Do not add twice
            resultList.extend(newList)
        return resultList
    
    def isAlbum(self):
        """Return whether this element is an album (that is, whether it is a container and has a album-tag matching a title-tag.)"""
        return self.isContainer() and not set(self.tags[tags.ALBUM]).isdisjoint(set(self.tags[tags.TITLE]))
        
    def hasAlbumTitle(self,container):
        """Return whether the given container has a title-tag equal to an album-tag of this element. Thus, to check whether <container> is an album of this element, it remains to check that it is a parent (see getParentIds)."""
        for title in container.tags[tags.TITLE]:
            if title in self.tags[tags.ALBUM]:
                return True
        return False

    def isContainedInAlbum(self):
        """Check whether this element is in the current tree-structure contained in an album of itself."""
        if tags.ALBUM in self.tags:
            parent = self.getParent()
            while isinstance(parent,Element):
                if self.hasAlbumTitle(parent):
                    return True
                parent = parent.getParent()
        return False
        
    def getAlbumIds(self):
        """Return the ids of all album-containers of this element from the database. This can only be used for elements in the database."""
        if not self.isInDB():
            raise RuntimeError("getAlbumIds can only be used on elements contained in the database.")
        parentIds = self.getParentIds(True)
        albumTitles = self.tags[tags.ALBUM]
        if len(albumTitles) > 0:
            albums = []
            for id in parentIds:
                titles = db.query("""
                    SELECT tag_{0}.value
                    FROM tags JOIN tag_{0} ON tags.value_id = tag_{0}.id
                    WHERE tags.element_id = {1} AND tags.tag_id = {2}
                    """.format(tags.TITLE.name,id,tags.TITLE.id)).getSingleColumn()
                for title in titles:
                    if title in albumTitles:
                        albums.append(id)
            return albums
        else: return []
        
    def hasCover(self):
        """Return whether this element has a cover."""
        return self.isInDB() and covers.hasCover(self.id)
        
    def getCover(self,size=None,cache=True):
        """Get this elements's cover with <size>x<size> pixels or the large version if <size> is None. If <cache> is True, this method will store the cover in this Element-instance. Warning: Subsequent calls of this method will return the stored cover only if <cache> is again True."""
        if cache:
            try:
                return self._covers[size]
            except AttributeError: pass
            except KeyError: pass
        cover = covers.getCover(self.id,size)
        if cache:
            if not hasattr(self,"_covers"):
                self._covers = {}
            self._covers[size] = cover
        return cover
        
    def delete(self):
        """Deletes the element from the database."""
        if not self.isInDB():
            raise RuntimeError("delete can only be used on elements contained in the database.")
        if self.isFile():
            queries.delFile(id = self.id)
        else:
            queries.delContainer(self.id)
        if isinstance(self.parent, Element):
            self.parent.changesPending = True
        self.parent.contents.remove(self)
        self.id = None
            
    # Misc
    #====================================================
    def getTitle(self):
        """Convenience method to get the formatted title of this element."""
        from omg.gui import formatter
        return formatter.Formatter(self).title()
    
    def toolTipText(self):
        """Return a HTML-text which may be used in tooltips for this element."""
        from omg.gui import formatter
        return formatter.HTMLFormatter(self).detailView()
    
    def __str__(self):
        if self.tags is not None:
            return "<{} {}{}>".format(type(self).__name__,self.getTitle(),'' if self.isInDB() else " (external)")
        else: return "<{} {}>".format(type(self).__name__,self.id if self.isInDB() else "(external)")
    

class Container(Element):
    
    contents = None
    
    """Element-subclass for containers."""
    def __init__(self,id=None,tags=None,contents=None):
        """Initialize this element with the given id, which must be an integer or None (for external containers). Optionally you may specify a tags.Storage object holding the tags of this element and/or a list of contents. Note that the list won't be copied but the parents will be changed to this container."""
        if id is not None and not isinstance(id,int):
            raise ValueError("id must be either None or an integer. I got {}".format(id))
        self.id = id
        self.tags = tags
        if contents is None:
            self.contents = []
        else: self.setContents(contents)
    
    def setContents(self,contents):
        """Set the list of contents of this container to <contents>. Note that the list won't be copied but the parents will be set to this container."""
        assert isinstance(contents,list)
        self.contents = contents
        for element in self.contents:
            element.setParent(self)
        
    def isFile(self):
        return False
    
    def isContainer(self):
        return True
    
    def loadContents(self,recursive=False,table="elements"):
        """Delete the stored contents-list and fetch the contents from the database. You may use the <table>-parameter to restrict the child elements to a specific table: The table with name <table> must contain a column 'id' and this method will only fetch elements which appear in that column. If <recursive> is true loadContents will be called recursively for all child elements.
        If this container is not contained in the DB, this method won't do anything (except the recursive call if <recursive> is True)."""
        if self.isInDB():
            additionalJoin = "JOIN elements ON elements.id = {}.id".format(table) if table != 'elements' else ''
            result = db.query("""
                    SELECT contents.element_id,elements.file
                    FROM contents JOIN {0} ON contents.container_id = {1} AND contents.element_id = {0}.id {2}
                    ORDER BY contents.position
                    """.format(table,self.id,additionalJoin))
            self.setContents([createElement(id,file=file) for id,file in result])
            
        if recursive:
            for element in self.contents:
                if element.isContainer():
                    element.loadContents(recursive,table)
                
    def getLength(self,refresh=False):
        """Return the length of this element, i.e. the sum of the lengths of all contents."""
        return sum(element.getLength(refresh) for element in self.contents)

    def commit(self, toplevel = False):
        """Commit this container into the database"""
        logger.debug("commiting container {}".format(self))
        wasInDB = self.isInDB()
        if not wasInDB:
            self.id = database.queries.addContainer(
                            "spast", tags = self.tags, file = False, elements = len(self.contents), toplevel = toplevel)
        else:
            database.queries.delContents(self.id)
        for elem in self.contents:
            elem.commit()
            database.queries.addContent(self.id, elem.getPosition(), elem.id)
        if wasInDB:
            database.queries.updateElementCounter(self.id)
        self.changesPending = False

    
    def updateSameTags(self, metaContainer = False):
        """Sets the tags of this element to be exactly those which are the same for all contents."""
        self.commonTags = set(x for x in reduce(lambda x,y: x & y, [set(tr.tags.keys()) for tr in self.contents]) \
                              if (x.name not in tags.TOTALLY_IGNORED_TAGS))
        if metaContainer:
            self.commonTags = self.commonTags - {tags.TITLE, tags.ALBUM}
        self.commonTagValues = {}
        differentTags=set()
        for file in self.contents:
            t = file.tags
            for tag in self.commonTags:
                if tag not in self.commonTagValues:
                    self.commonTagValues[tag] = t[tag]
                if self.commonTagValues[tag] != t[tag]:
                    differentTags.add(tag)
        self.sameTags = self.commonTags - differentTags
        newTags = tags.Storage()
        for tag in self.sameTags:
            newTags[tag] = self.commonTagValues[tag]
        if self.tags:
            self.tags.merge(newTags)
        else:
            self.tags = newTags
            
class File(Element):
    def __init__(self, id = None, tags = None, length = None, path = None):
        """Initialize this element with the given id, which must be an integer or None (for external files). Optionally you may specify a tags.Storage object holding the tags of this element and/or a file path."""
        if id is not None and not isinstance(id,int):
            raise ValueError("id must be either None or an integer. I got {}".format(id))
        self.id = id
        self.tags = tags
        self.length = length
        if path is not None and not isinstance(path,str):
            raise ValueError("path must be either None or a string. I got {}".format(id))
        self.path = path
    
    def hasChildren(self):
        return False
    
    def getChildren(self):
        return []

    def getChildrenCount(self):
        return 0
        
    def isFile(self):
        return True
    
    def isContainer(self):
        return False
    
    def readTagsFromFilesystem(self):
        if self.path is None:
            raise RuntimeError("I need a path to read tags from the filesystem.")
        real = realfiles.File(absPath(self.path))
        try:
            real.read()
        except realfiles.ReadTagError as e:
            logger.warning("Failed to read tags from file {}: {}".format(self.path, str(e)))
        if self.tags != real.tags:
            self.changesPending = True
        self.tags = real.tags
        self.length = real.length
    
    def writeTagsToFilesystem(self):
        real = realfiles.File(absPath(self.path))
        real.tags = self.tags
        real.save_tags()
            
    def getPath(self,refresh=True):
        """Return the path of this file. If the file is in the DB and no path is stored yet or <refresh> is True, the path will be fetched from the database and cached for subsequent calls."""
        if self.isInDB():
            if refresh or not hasattr(self,'path'):
                path = db.query("SELECT path FROM files WHERE element_id = {0}".format(self.id)).getSingle()
                if path is None:
                    raise ValueError("The element with id {0} has no path. Maybe it is a container.".format(self.id))
                self.path = path
            return self.path
        else:
            if hasattr(self,'path'):
                return self.path
            else: return None
    
    def getLength(self,refresh=False):
        """Return the length of this file. If the file is in the DB and no length is stored yet or <refresh> is True, the length will be fetched from the database and cached for subsequent calls."""
        if self.isInDB() and (refresh or not self.length):
            self.length = db.query("SELECT length FROM files WHERE element_id = {0}".format(self.id)).getSingle()
        return self.length
    
    def computeHash(self):
        """Computes the hash of the audio stream."""
    
        import hashlib,tempfile,subprocess
        handle, tmpfile = tempfile.mkstemp()
        subprocess.check_call(
            ["mplayer", "-dumpfile", tmpfile, "-dumpaudio", absPath(self.path)], #TODO: konfigurierbar machen
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        # wtf ? for some reason handle is int instead of file handle, as said in documentation
        with open(tmpfile,"br") as handle:
            self.hash = hashlib.sha1(handle.read()).hexdigest()
        os.remove(tmpfile)
        
    def commit(self, toplevel = False):
        """Save this file into the database. After that, the object has an id attribute"""
        if self.isInDB(): #TODO: tags commiten
            return
        logger.debug("commiting file {}".format(self.path))
        self.id = database.queries.addContainer(
                                        os.path.basename(self.path),
                                        tags = self.tags,
                                        file = True,
                                        elements = 0,
                                        toplevel = toplevel)
        querytext = "INSERT INTO files (element_id,path,hash,length) VALUES(?,?,?,?);"
        if self.length is None:
            self.length = 0
        if not hasattr(self, "hash"):
            self.computeHash()
        db.query(querytext, self.id, relPath(self.path), self.hash, int(self.length))
        self.changesPending = False

def createElement(id,tags=None,contents=None,file=None):
    """Create an element with the given id, tags and contents. Depending on <file> an instance of Container or of File will be created. If <file> is None, the file-flag (elements.file) will be read from the database. Note that contents will be ignored if a File-instance is created."""
    if file is None:
        file = db.query("SELECT file FROM elements WHERE id=?",id).getSingle()
        if file is None:
            raise ValueError("There is no element with id {}".format(id))
    if file:
        return File(id,tags=tags)
    else: return Container(id,tags=tags,contents=contents)