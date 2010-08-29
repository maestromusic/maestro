#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import logging, copy
from PyQt4 import QtCore

from omg import tags, database, covers, config
from omg.database import queries
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

    def copy(self,contents=-1): # In subclasses like Element None is a legal value for contents.
        """Return a copy of this node. All attributes will be copied by reference, with the exception of the list of contents: If this instance contains a content-attribute, the new node will contain a deep copy of it. Note that a shallow copy makes no sense, because the parent-attributes have to be adjusted. If you do not want this behaviour, you may specify the parameter <contents> and the contents will be set to that parameter. The parents of all elements of <contents> will be adjusted in this case, too."""
        newNode = copy.copy(self)
        if contents == -1:
            if hasattr(self,'contents'):
                newNode.contents = [node.copy(True) for node in self.contents]
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
        assert self.getChildren() is not None
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
        assert self.getChildren() is not None
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
    """Base class for elements (files or containers) in playlists, browser, etc.. Contains methods to load tags and contents from the database and to get the path, cover, length etc.."""
    tags = None # tags.Storage to store the tags. None until they are loaded
    contents = None # list of contents. None until they are loaded; [] if this element has no contents
    
    def __init__(self,id,tags=None,contents=None):
        """Initialize this element with the given id, which must be an integer. Optionally you may specify a tags.Storage object holding the tags of this element."""
        assert isinstance(id,int)
        self.id = id
        self.tags = tags
        self.contents = contents
    
    def copy(self,contents=-1):
        """Reimplementation of Node.copy: In addition to contents the tags are also not copied by reference. Instead the copy will contain a copy of this node's tags.Storage-instance."""
        newNode = Node.copy(self,contents)
        newNode.tags = self.tags.copy()
        return newNode
        
    def hasChildren(self):
        """Return whether this node has at least one child node or None if it is unknown since the contents are not loaded yet."""
        return self.contents is not None and len(self.contents) > 0
    
    def getChildrenCount(self):
        """Return the number of children or None if it is unknown since the contents are not loaded yet."""
        if self.contents is None:
            return 0
        else: return len(self.contents)
        
    def isFile(self):
        """Return whether this Element holds a file or None if it is unknown since the contents are not loaded yet."""
        if self.contents is None:
            return None
        else: return len(self.contents) == 0
    
    def isContainer(self):
        """Return whether this Element holds a container or None if it is unknown since the contents are not loaded yet."""
        if self.contents is None:
            return None
        else: return len(self.contents) > 0
        
    def getPath(self,refresh=True):
        """Return the path of this Element and cache it for subsequent calls.  If <refresh> is True the cached value must be recomputed. If the element has no path (e.g. containers), a ValueError is raised."""
        if refresh or not hasattr(self,'path'):
            path = db.query("SELECT path FROM files WHERE element_id = {0}".format(self.id)).getSingle()
            if path is None:
                raise ValueError("The element with id {0} has no path. Maybe it is a container.".format(self.id))
            self.path = path
        return self.path
        
    def loadContents(self,recursive=False,table="elements"):
        """Delete the stored contents-list and fetch the contents from the database. You may use the <table>-parameter to restrict the child elements to a specific table: The table with name <table> must contain a column 'id' and this method will only fetch elements which appear in that column. If <recursive> is true loadContents will be called recursively for all child elements."""
        self.contents = []
        result = db.query("""
                SELECT contents.element_id
                FROM contents JOIN {0} ON contents.container_id = {1} AND contents.element_id = {0}.id
                ORDER BY contents.position
                """.format(table,self.id)).getSingleColumn()
        for id in result:
            self.contents.append(Element(id))
            self.contents[-1].parent = self
            
        if recursive:
            for element in self.contents:
                element.loadContents(recursive,table)

    def ensureContentsAreLoaded(self,recursive=False):
        """Load contents if they are not loaded yet."""
        if self.contents is None:
            self.loadContents()
        if recursive:
            for element in self.contents:
                element.loadContents(recursive=True)

    def loadTags(self,recursive=False,tagList=None):
        """Delete the stored indexed tags and load them from the database. If <recursive> is True, all tags from children of this node (recursively) will be loaded, too. If <tagList> is not None only tags in the given list will be loaded (e.g. only title-tags). Note that this method affects only indexed tags!"""
        self.tags = tags.Storage()
        
        if tagList is not None:
            additionalWhereClause = " AND tag_id IN ({0})".format(",".join(str(tag.id) for tag in tagList))
            otherAdditionalWhereClause = " AND tagname IN ({0})".format(",".join(str(tag.name for tag in tagList)))
        else:
            additionalWhereClause = ''
            otherAdditionalWhereClause = ''
        
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
        
        # load othertags
        result = db.query("""
            SELECT tagname,value
            FROM othertags
            WHERE element_id = {0} {1}
            """.format(self.id,otherAdditionalWhereClause))
        for row in result:
            tag = tags.get(row[0])
            value = row[1]
            self.tags[tag].append(value)
        if recursive:
            for element in self.contents:
                element.loadTags(recursive,tagList)
    
    def ensureTagsAreLoaded(self,recursive=False):
        """Load indexed tags if they are not loaded yet."""
        if self.tags is None:
            self.loadTags()
        if recursive:
            for element in self.contents:
                element.ensureTagsAreLoaded()
                
    def getOtherTags(self,cache=False):
        """Load the tags which are not indexed from the database and return them. The result will be a tags.Storage mapping tag-names to lists of tag-values. If <cache> is True, the tags will be stored in this Element. Warning: Subsequent calls of this method will return the cached tags only if <cache> is again True."""
        if cache and hasattr(self,'otherTags'):
            return self.otherTags
        result = db.query("SELECT tagname,value FROM othertags WHERE element_id = {0}".format(self.id))
        otherTags = tags.Storage()
        for row in result:
            otherTags[tags.OtherTag(row[0])].append(row[1])
        if cache:
            self.otherTags = otherTags
        return otherTags
            
    def getLength(self,refresh=False):
        """Return the length of this element. If it is a file, the length will be cached for subsequent calls. If <refresh> is True the cached value must be recomputed. If the element is a container, return the sum of the lengths of all its contents.  If the length can't be computed, None is returned. This happens for example if the contents have not yet been loaded."""
        if self.contents is None:
            return None
        if len(self.contents) == 0:
            if refresh or not hasattr(self,'lenght'):
                self.length = db.query("SELECT length FROM files WHERE element_id = {0}".format(self.id)).getSingle()
            return self.length
        else:
            try:
                return sum(element.getLength() for element in self.contents)
            except TypeError: # At least one element does not know its length
                return None
    
    def getPosition(self,refresh=False):
        """Return the position of this element in its current parent and cache it for subsequent calls. Note that position is the number from the contents-table, not the index of this element in the parent's list of children. To get the latter, use parent.index(self). If <refresh> is True the cached value must be recomputed. Return None if the element has no parent or the parent is not of type Element."""
        if self.parent is None or not isinstance(self.parent,Element): # Without parent, there can't be a position
            return None
        if refresh or not hasattr(self,'position'):
            self.position = db.query("SELECT position FROM contents WHERE container_id = ? AND element_id = ?", 
                                 self.parent.id,self.id).getSingle()
        return self.position
        
    def getParentIds(self,recursive):
        """Return a list containing the ids of all parents of this element from the database. If <recursive> is True all ancestors will be added recursively."""
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
        """Return the ids of all album-containers of this element."""
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
        """Return whether this container has a cover."""
        return covers.hasCover(self.id)
        
    def getCover(self,size=None,cache=True):
        """Get this container's cover with <size>x<size> pixels or the large version if <size> is None. If <cache> is True, this method will store the cover in this Element-instance. Warning: Subsequent calls of this method will return the stored cover only if <cache> is again True."""
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
        if self.isFile():
            queries.delFile(id = self.id)
        else:
            queries.delContainer(self.id)
            
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
            return "<Element {0}>".format(self.getTitle())
        else: return "<Element {0}>".format(self.id)