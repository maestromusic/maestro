# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from PyQt4 import QtCore

import copy

from .. import tags, logging, config, covers, realfiles, database as db
from ..utils import relPath

logger = logging.getLogger(__name__)

translate = QtCore.QCoreApplication.translate


class Node:
    """(Abstract) base class for elements in a RootedTreeModel...that is almost everything in playlists,
    browser etc.. Node implements the methods required by RootedTreeModel as well as many tree-structure 
    methods. To implement getParent, setParent and getContents, it uses self.parent as parent and
    self.contents as the list of contents, but does not create these variables. Subclasses must either create
    self.contents and self.parent or overwrite the methods."""
    
    def hasContents(self):
        """Return whether this node has at least one child node."""
        return len(self.getContents()) > 0
        
    def getContents(self):
        """Return the list of contents."""
        # This is a default implementation and does not mean that every node has a contents-attribute
        return self.contents
    
    def getContentsCount(self,recursive=False):
        """Return the number of children or None if it is unknown."""
        if not recursive:
            return len(self.getContents())
        else:
            # Add the child itself
            return sum(child.getContentsCount(True)+1 for child in self.getContents())   
    
    def getParent(self):
        """Return the parent of this element."""
        # This is a default implementation and does not mean that every node has a parent-attribute
        return self.parent
    
    def setParent(self,parent):
        """Set the parent of this node."""
        # This is a default implementation and does not mean that every node has a parent-attribute
        self.parent = parent
    
    def setContents(self,contents):
        """Set the list of contents of this container to *contents*. Note that the list won't be copied and in
        fact altered: the parents will be set to this node."""
        assert isinstance(contents,list)
        self.contents = contents
        for element in self.contents:
            element.setParent(self)
    
    def insertContents(self, index, nodes):
        """Insert *nodes* at position *index* into this node's contents. As with setContents the list won't
        be copied and the parents will be set to this node."""
        for n in nodes:
            n.setParent(self)
        self.contents[index:index] = nodes
        
    def isFile(self):
        """Return whether this node holds a file. Note that this is in general not the opposite of isContainer
        as e.g. rootnodes are neither."""
        return False
    
    def isContainer(self):
        """Return whether this node holds a container. Note that this is in general not the opposite of isFile
        as e.g. rootnodes are neither."""
        return False

    def copy(self,contents=None):
        """Return a copy of this node. All attributes will be copied by reference, with the exception of the
        list of contents: If this instance contains a content-attribute, the new node will contain a deep copy
        of it. Note that a shallow copy makes no sense, because the parent-attributes have to be adjusted. If
        you do not want this behavior, you may specify the parameter *contents* and the contents will be set
        to that parameter. The parents of all elements of *contents* will be adjusted in this case, too."""
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
        """Returns a generator yielding all parents of this node in the current tree structure, from the
        direct parent to the root-node."""
        parent = self.getParent()
        while parent is not None:
            yield parent
            parent = parent.getParent()
    
    def getDepth(self):
        """Return the depth of this node in the current tree structure. The root node will have level 0."""
        if self.getParent() is None:
            return 0
        else: return 1 + self.getParent().getDepth()

    def maxDepth(self):
        """Return the maximum depth of nodes below this node."""
        if self.hasContents():
            return 1 + max(node.maxDepth() for node in self.getContents())
        else: return 0

    def index(self,node, compareByID = False):
        """Return the index of *node* in this node's contents or raise a ValueError if *node* is not found.
         See also find."""
        for i,n in enumerate(self.getContents()):
            if compareByID:
                if n.id == node.id and n.position == node.position:
                    return i
                
            else:
                if n == node:
                    return i
        raise ValueError("Node.index: Node {0} is not contained in element {1}.".format(node,self))
        
    def find(self,node):
        """Return the index of *node* in this node's contents or -1 if *node* is not found. See also index."""
        contents = self.getContents()
        for i in range(0,len(contents)):
            if contents[i] == node:
                return i
        return -1

    def getAllNodes(self, skipSelf = False):
        """Generator which will return all nodes contained in this node or in children of it, including the
        node itself if *skipSelf* is not set True."""
        if not skipSelf:
            yield self
        if self.isFile():
            return
        for element in self.contents:
            for node in element.getAllNodes():
                yield node
 
    def getAllFiles(self):
        """Generator which will return all files contained in this node or in children of it
        (possibly including the node itself)."""
        assert self.getContents() is not None
        if self.isFile():
            yield self
        else:
            for element in self.getContents():
                for file in element.getAllFiles():
                    yield file
                        
    def fileCount(self):
        """Return the number of files contained in this element or in child-elements of it."""
        if self.isFile():
            return 1
        else: return sum(element.fileCount() for element in self.getContents())
        
    def offset(self):
        """Get the offset of this element in the current tree structure."""
        if self.getParent() is None:
            return 0
        else:
            offset = self.getParent().offset()
            for child in self.getParent().getContents():
                if child == self:
                    return offset
                else: offset = offset + child.fileCount()
            raise ValueError("Node.getOffset: Node {0} is not contained in its parent {1}."
                                .format(self,self.getParent()))
    
    def childOffset(self,childIndex):
        """Return the offset of the child with index <childIndex> in this node."""
        if childIndex < 0 or childIndex >= self.getContentCount():
            raise IndexError("childIndex {} is out of bounds.".format(childIndex))
        offset = 0
        for node in self.getContents()[:childIndex]:
            offset = offset + node.fileCount()
        return offset
        
    def fileAtOffset(self,offset):
        """Get the file at the given <offset>. Note that <offset> is relative to this element, not to the
        whole playlist (unless the element is the rootnode)."""
        assert self.getContents() is not None
        offset = int(offset)
        if offset == 0 and self.isFile():
            return self
        else: 
            child,innerOffset = self.childAtOffset(offset)
            if child.isFile():
                return child
            else: return child.fileAtOffset(innerOffset)
        
    def childIndexAtOffset(self,offset):
        """Return a tuple: the index of the child C that contains the file F with the given offset (relative
        to this element) and the offset of F relative to C ("inner offset").
        For example: If this element is the rootnode and the playlist contains an album with 13 songs and one
        with 12 songs, then getChildIndexAtOffset(17) will return (1,3), since the 18th file if the playlist
        (i.e. with offset 17), is contained in the second album (i.e with index 1) and it is the 4th song on
        that album (i.e. it has offset 3 relative to the album).
        """
        offset = int(offset)
        if offset < 0:
            raise IndexError("Offset {0} is out of bounds".format(offset))
        cOffset = 0
        for i in range(0,self.getContentsCount()):
            fileCount = self.contents[i].fileCount()
            if offset < cOffset + fileCount:
                return i,offset-cOffset
            else: cOffset = cOffset + fileCount
        if offset == cOffset:
            return None,None
        raise IndexError("Offset {0} is out of bounds".format(offset))
    
    def childAtOffset(self,offset):
        """Return the child containing the file with the given (relative) offset, and the offset of that file
        relative to the child. This is a convenience-method for
        getChildren()[getChildIndexAtOffset(offset)[0]]. Confer getChildIndexAtOffset.
        """
        index,innerOffset = self.childIndexAtOffset(offset)
        if index is None:
            return None,None
        else: return self.getContents()[index],innerOffset
        
    def printStructure(self, indent = ''):
        print(indent + str(self))
        for child in self.getContents():
            child.printStructure(indent + '  ')


class RootNode(Node):
    """Rootnode at the top of a RootedTreeModel."""
    def __init__(self):
        from .. import modify
        self.contents = []
        self.id = modify.newEditorId()
    
    def getParent(self):
        return None
    
    def setParent(self):
        raise RuntimeError("Cannot set the parent of a RootNode.")
    
    def __repr__(self):
        return 'RootNode[{}] with {} children'.format(self.id, len(self.contents))

    def copyFrom(self, other, copyContents = False):
        if copyContents:
            self.setContents([c.copy() for c in other.contents])
        self.id = other.id
        
        
class Element(Node):
    """Abstract base class for elements (files or containers) in playlists, browser, etc.. Contains methods
    to load tags and contents from the database or from files."""
    tags = None # tags.Storage to store the tags. None until they are loaded
    position = None
    length = None
    id = None
    
    def __init__(self):
        raise RuntimeError(
                "Cannot instantiate abstract base class Element. Use Element.fromId.")
    
    @staticmethod
    def fromId(id, *, position=None, parentId=None, loadData=True):
        if db.isFile(id):
            return File.fromId(id, position=position, parentId=parentId,loadData=loadData)
        else:
            return Container.fromId(id, position=position, parentId=parentId, loadData=loadData)

    def isInDB(self, recursive = False):
        """Return whether this element is contained in the database, that is whether it has an id. If
        *recursive* is True, only return True if this element and all of its recursive children are in the
        database."""
        if not recursive:
            return self.id > 0
        else:
            return self.id is not None and (self.isFile() or all(e.isInDB(True) for e in self.contents))

    def export(self,attributes,copyList=['contents'],replace={}):
        """Return a copy of this element with a specified set of attributes. In contrast to copy this method
        allows to control what attributes the result will have and loads missing attributes from the
        database. Therefore this method is particularly useful when elements are exported from one component
        to another (e.g. drops, events).
        
            - *attributes* is the list of attributes the result will have. It must not include ''id'',
              because this attribute is always copied. Attributes that are missing in the original node will
              be loaded from the database/filesystem.
            - usually attributes will be copied by reference. *copyList* is a list that may contain
              ''contents'',''flags'' and/or ''tags''. When contained in *copyList*, these attributes will be
              really copied. In case of ''contents'' this implies applying this method with the same
              parameters recursively to the children.
              Warning: Usually you will want a real copy of the contents. Elements in a shallow copy will
              have broken parent pointers. Therefore ''['contents']'' is the default value.
            - finally you may give a dict *replace* mapping attribute names to values. These values will
              overwrite corresponding values from the original.
        
        \ """ 
        if isinstance(self,Container):
            result = Container(self.id,None,None,None,None,None)
        else: result = File(self.id,None,None,None,None,None)
        for attr in attributes:
            if attr in replace:
                setattr(result,attr,replace[attr])
            elif not hasattr(self,attr) or getattr(self,attr) is None:
                if attr == 'contents':
                    if isinstance(result,Container):
                        result.loadContents()
                elif attr == 'tags':
                    result.tags = db.tags(result.id)
                elif attr == 'flags':
                    result.flags = db.flags(result.id)
                elif attr == 'path':
                    if isinstance(result,File):
                        path = db.path(result.id)
                elif attr == 'length':
                    if isinstance(result,File):
                        path = db.length(result.id)
                else: setattr(result,attr,None)
            else:
                if attr == 'contents' and 'contents' in copyList:
                    result.setContents([child.export(attributes,copyList,replace) for child in self.contents])
                if attr == 'tags' and 'tags' in copyList:
                    result.tags = self.tags.copy()
                elif attr == 'flags' and 'flags' in copyList:
                    result.flags = self.flags[:]
                else: setattr(result,attr,getattr(self,attr))
        return result
    
    def copy(self,contents=None,copyTags=True):
        """Reimplementation of Node.copy: If *copyTags* is True, the element's copy will contain a copy of
        this node's tags.Storage-instance and its flaglist. Otherwise the tags and flags will be copied by
        reference."""
        newNode = Node.copy(self,contents)
        if copyTags:
            newNode.tags = self.tags.copy() if self.tags is not None else None
            newNode.flags = self.flags[:] if self.flags is not None else None
        return newNode
    
    def copyFrom(self, other, copyContents = False):
        """Set the data of this element to the data of *other*. This includes all data (even the id!) except
        for the contents which are only touched if *copyContents* is True. Contents, tags and flags will be
        copied deeply. This is used by ElementChangeEvent.applyTo.
        """
        if copyContents and not self.isFile():
            self.setContents([c.copy() for c in other.contents])
        if self.tags != other.tags:
            self.tags = other.tags.copy()
        if self.flags != other.flags:
            self.flags = other.flags[:]
        self.position = other.position
        if self.isFile():
            self.path = other.path
        else: self.major = other.major
        self.length = other.length
        self.id = other.id
        
    def loadTags(self,recursive=False,fromFS=False): 
        """Delete the stored tags and load them again. If this element is contained in the DB, tags will be
        loaded from there. Otherwise if this is a file, tags will be loaded from that file or no tags will be
        loaded if this is a container. 
        If *recursive* is True, all tags from children of this node (recursively) will be loaded, too.
        If *fromFS* is True, then tags are read from the file even if this element is in the DB (if it is a
        file).""" 
        if fromFS or not self.isInDB(): 
            if self.isFile(): 
                self.readFromFilesystem(tags=True) 
            else: self.tags = tags.Storage() 
        else: 
            self.tags = db.tags(self.id) 
        
        if recursive: 
            for element in self.getContents(): 
                element.loadTags(recursive, fromFS) 

    def loadFlags(self,recursive=False):
        """Load flags from the database. If the element is not contained in the database, set self.flags to
        an empty list.
        If *recursive* is True, all tags from children of this node (recursively) will be loaded, too.
        """
        if self.isInDB():
            self.flags = db.flags(self.id)
        else: self.flags = []
        if recursive:
            for element in self.getContents():
                element.loadFlags(recursive)
        
    def hasCover(self):
        """Return whether this element has a cover."""
        return self.isInDB() and covers.hasCover(self.id)
        
    def getCover(self,size=None,fromFS=False):
        """Get this elements's cover with *size*x*size* pixels or the large version if *size* is None.
        The cover will be cached and returned from the cache in subsequent calls. Set *fromFS* to True to
        enforce that the cover is read from the filesystem and not from cache.
        """
        if not fromFS:
            try:
                return self._covers[size]
            except AttributeError: pass
            except KeyError: pass
        cover = covers.getCover(self.id,size)
        # Cache the cover
        if not hasattr(self,"_covers"):
            self._covers = {}
        self._covers[size] = cover
        return cover

    def deleteCoverCache(self):
        """Delete all covers from the built-in cover cache."""
        if hasattr(self,"_covers"):
            del self._covers

    # Misc
    #====================================================
    def getTitle(self,prependPosition=False,usePath=True,titles=None):
        """Return the title of this element or some dummy title, if the element does not have a title tag.
        Additionally the result may contain a position (if *prependPosition* is True) and/or the element's
        id (if ''config.options.misc.show_ids'' is True). If *usePath* is True, the path will be used as
        title for files without title tag. Finally, the optional argument *titles* may be used to overwrite
        the titles stored in ''self.tags'' (this is in particular useful if the element does not store tags).
        """
        result = ''
        
        if prependPosition and self.position is not None:
            result += "{} - ".format(self.position)
        
        if hasattr(self,'id') and config.options.misc.show_ids:
            result += "[{0}] ".format(self.id)
            
        if titles is not None:
            result += " - ".join(titles)
        elif self.tags is None:
            result += translate("Element","<No title>")
        elif tags.TITLE in self.tags:
            result += " - ".join(self.tags[tags.TITLE])
        elif usePath and self.isFile() and self.path is not None:
            result += self.path
        else: result += translate("Element","<No title>")

        return result
    
    def toolTipText(self):
        parts = []
        if self.tags is not None:
            parts.append('\n'.join('{}: {}'.format(tag.translated(),', '.join(map(str,values)))
                                    for tag,values in self.tags.items()))
        if self.flags is not None and len(self.flags) > 0:
            parts.append('Flags: ' + ', '.join(flag.name for flag in self.flags))
        if len(parts) > 0:
            return '\n'.join(parts)
        else: return str(self)
    
    def iPosition(self):
        """Return the position of the element, if its parent is itself an element, or the index, if
        the parent is a root node."""
        if isinstance(self.parent, RootNode):
            return self.parent.index(self, True)
        else:
            return self.position
        
    def __str__(self):
        if self.tags is not None:
            ret =  "({}) <{}[{}]> {}".format(self.position if self.position is not None else '',
                                             type(self).__name__,
                                             self.id, 
                                             self.getTitle())
        else: ret =  "<{}[{}]>".format(type(self).__name__,self.id)
        return '*' + ret if self.major else ret
    

class Container(Element):
    """Element-subclass for containers."""
    
    contents = None
    
    def __init__(self, id, contents, tags, flags, position, major):
        """Initialize this container, optionally with a contents list.
        Note that the list won't be copied but the parents will be changed to this container."""
        self.id = id
        if contents is None:
            self.contents = []
        else: self.setContents(contents)
        self.tags = tags
        self.flags = flags
        self.position = position
        self.major = major
    
    @staticmethod
    def fromId(id, *, contents=None, tags=None, flags=None, position=None,
               parentId=None, major = None, loadData=True):
        if loadData:
            if tags is None:
                tags = db.tags(id)
            if flags is None:
                flags = db.flags(id)
            if position is None and parentId is not None:
                position = db.position(parentId,id)
            if major is None:
                major = db.isMajor(id)
        return Container(id,contents,tags,flags,position, major)

    def isContainer(self):
        return True
    
    def loadContents(self,recursive=False,table=None,loadData=True):
        """Delete the stored contents-list and fetch the contents from the database. You may use the
        *table*-parameter to restrict the child elements to a specific table: The table with name *table*
        must contain a column 'id' and this method will only fetch elements which appear in that column.
        If *recursive* is true loadContents will be called recursively for all child elements.
        If this container is not contained in the DB, this method won't do anything (except the recursive
        call if *recursive* is True)."""
        if self.isInDB():
            if table is None:
                table = db.prefix + "elements"
                
            result = db.query("""
                    SELECT c.element_id,c.position,res.file
                    FROM {0}contents AS c JOIN {1} AS res ON c.container_id = {2} AND c.element_id = res.id
                    ORDER BY c.position
                    """.format(db.prefix,table,self.id))
                    
            contents = [(File if file else Container).fromId(id,position=pos,loadData=loadData) 
                            for id,pos,file in result]
            self.setContents(contents)
        else: raise RuntimeError("Called loadContents on a container that is not in the db.")
        
        if recursive:
            for element in self.contents:
                if element.isContainer():
                    element.loadContents(recursive,table,loadData)

    def getLength(self):
        """Return the length of this element, i.e. the sum of the lengths of all contents."""
        # Skip elements of length None
        return sum(element.getLength(False) for element in self.contents if element.getLength() is not None)
    
    def sortContents(self):
        """Sorts the contents according to their positions."""
        self.contents.sort(key = lambda el: el.position)
    
    def __repr__(self):
        return "Container[{}] with {} elements".format(self.id, len(self.contents))


class File(Element):
    def __init__(self, id, tags, flags, path, length, position, major = False):
        """Initialize this element with the given id, which must be an integer or None (for external files).
        Optionally you may specify a tags.Storage object holding the tags of this element and/or a file path.
        """
        self.id = id
        self.tags = tags
        self.flags = flags
        self.length = length
        self.position = position
        self.major = major
        if path is not None and not isinstance(path,str):
            raise ValueError("path must be either None or a string. I got {}".format(id))
        self.path = path
    
    @staticmethod
    def fromId(id,*,tags=None,flags=None,path=None,length=None,position=None,
               parentId=None,loadData=True):
        if loadData and id > 0:
            if tags is None:
                tags = db.tags(id)
            if flags is None:
                flags = db.flags(id)
            if path is None:
                path = db.path(id)
            if length is None:
                length = db.length(id)
            if position is None and parentId is not None:
                position = db.position(parentId,id)
                #TODO: db.position now is db.positions() ... what to do if the 
                #element appears more than once below the same parent? (e.g. in a playlist)
        return File(id,tags,flags,path,length,position)
        
    @staticmethod
    def fromFilesystem(path):
        try:
            real = realfiles.get(path)
            real.read()
            fileTags = real.tags
            length = real.length
            position = real.position
        except OSError:
            fileTags = tags.Storage()
            fileTags[tags.TITLE] = ['<could not open file>']
            length = 0
            position = 0
        rpath = relPath(path)
        id = db.idFromPath(rpath)
        if id is None:
            from .. import modify
            id = modify.editorIdForPath(rpath)
            flags = []
        else:
            flags = db.flags(id)
            # TODO: Load private tags!
        return File(tags=fileTags,flags=flags,path=rpath,length=length,position=position,id = id)

    def hasContents(self):
        return False
    
    def getContents(self):
        return []
    
    def setContents(self):
        raise RuntimeError("Cannot assign contents to a file!")

    def getContentsCount(self,recursive=False):
        return 0
        
    def isFile(self):
        return True
    
    def getLength(self):
        """Return the length of this file."""
        return self.length
     
    def __repr__(self):
        return "File[{}] {}".format(self.id, self.path)
