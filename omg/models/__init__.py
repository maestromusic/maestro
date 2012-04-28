# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

import copy, os.path, bisect

from .. import tags, logging, config, covers, realfiles, database as db
from ..utils import relPath
tagsModule = tags

logger = logging.getLogger(__name__)

translate = QtCore.QCoreApplication.translate


class Node:
    """(Abstract) base class for elements in a RootedTreeModel...that is almost everything in playlists,
    browser etc.. Node implements the methods required by RootedTreeModel as well as many tree-structure 
    methods."""
    
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

    def setContents(self,contents):
        """Set the list of contents of this container to *contents*. Note that the list won't be copied but
        in fact altered: the parents will be set to this node."""
        assert isinstance(contents,list)
        self.contents = contents
        for element in self.contents:
            element.parent = self
    
    def insertContents(self, index, nodes):
        """Insert *nodes* at position *index* into this node's contents. As with setContents the list won't
        be copied and the parents will be set to this node."""
        for n in nodes:
            n.parent = self
        self.contents[index:index] = nodes
        
    def isFile(self):
        """Return whether this node holds a file. Note that this is in general not the opposite of 
        isContainer as e.g. rootnodes are neither."""
        return False
    
    def isContainer(self):
        """Return whether this node holds a container. Note that this is in general not the opposite of
        isFile as e.g. rootnodes are neither."""
        return False
    
    def getParents(self):
        """Returns a generator yielding all parents of this node in the current tree structure, from the
        direct parent to the root-node."""
        parent = self.parent
        while parent is not None:
            yield parent
            parent = parent.parent
    
    def getDepth(self):
        """Return the depth of this node in the current tree structure. The root node will have level 0."""
        if self.parent is None:
            return 0
        else: return 1 + self.parent.getDepth()

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
        
    def find(self,node, compareById):
        """Return the index of *node* in this node's contents or -1 if *node* is not found. See also index."""
        for i, elem in enumerate(self.contents):
            if elem == node or (compareById and elem.id == node.id):
                return i
        return -1
    
    def getAllNodes(self, skipSelf = False):
        """Generator which will return all nodes contained in this node or in children of it, including the
        node itself if *skipSelf* is not set True."""
        if not skipSelf:
            yield self
        if self.isFile():
            return
        for node in self.contents:
            for subnode in node.getAllNodes():
                yield subnode
 
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
        if self.parent is None:
            return 0
        else:
            offset = self.parent.offset()
            for child in self.parent.getContents():
                if child == self:
                    return offset
                else: offset = offset + child.fileCount()
            raise ValueError("Node.getOffset: Node {0} is not contained in its parent {1}."
                                .format(self,self.parent))
    
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
    
    parent = None
    def __init__(self, model):
        self.contents = []
        self.model = model
    
    def __repr__(self):
        return 'RootNode with {} children'.format(len(self.contents))    


class Wrapper(Node):
    """A node that holds an element."""
    def __init__(self,element,contents = None, position = None):
        self.element = element
        self.position = position
        if element.isContainer():
            if contents is not None:
                self.contents = contents
            else: self.contents = []
        else:
            assert contents is None
        
    def isFile(self):
        return self.element.isFile()
    
    def isContainer(self):
        return self.element.isContainer()
    
    def hasContents(self):
        return self.element.isContainer() and len(self.contents) > 0
    
    def getContentsCount(self):
        return len(self.contents) if self.element.isContainer() else 0
    
    def getContents(self):
        return self.contents if self.element.isContainer() else []
    
    def loadContents(self, recursive):
        if self.element.isContainer():
            self.setContents([Wrapper(self.element.level.get(id),position = pos) for pos,id in self.element.contents.items()])
            if recursive:
                for child in self.contents:
                    child.loadContents(recursive)
    
    def getTitle(self,prependPosition=False,usePath=True,titles=None):
        title = self.element.getTitle(usePath,titles)
        if prependPosition and self.position is not None:
            return "{} - {}".format(self.position,title)
        else: return title
        
    def toolTipText(self):
        parts = []
        if self.element.tags is not None:
            parts.append('\n'.join('{}: {}'.format(tag.title,', '.join(map(str,values)))
                                    for tag,values in self.element.tags.items()))
        if self.element.flags is not None and len(self.element.flags) > 0:
            parts.append('Flags: ' + ', '.join(flag.name for flag in self.element.flags))
        if len(parts) > 0:
            return '\n'.join(parts)
        else: return str(self)


class Element:
    """Abstract base class for elements (files or containers) in playlists, browser, etc.. Contains methods
    to load tags and contents from the database or from files."""   
    def __init__(self):
        raise RuntimeError("Cannot instantiate abstract base class Element. Use Element.fromId.")

    def isInDB(self):
        return self.id > 0
        
    def __str__(self):
        if self.tags is not None:
            ret =  "({}) <{}[{}]> {}".format(self.position if self.position is not None else '',
                                             type(self).__name__,
                                             self.id, 
                                             self.getTitle())
        else: ret =  "<{}[{}]>".format(type(self).__name__,self.id)
        return '*' + ret if self.major else ret
    
    def getTitle(self,usePath=True,titles=None):
        """Return the title of this element or some dummy title, if the element does not have a title tag.
        Additionally the result may contain a position (if *prependPosition* is True) and/or the element's
        id (if ''config.options.misc.show_ids'' is True). If *usePath* is True, the path will be used as
        title for files without title tag. Finally, the optional argument *titles* may be used to overwrite
        the titles stored in ''self.tags'' (this is in particular useful if the element does not store tags).
        """
        result = ''
        
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
    

class Container(Element):
    """Element-subclass for containers."""
    
    contents = None

    def __init__(self, level, id, major,*, contents=None, parents=None, tags=None, flags=None):
        """Initialize this container, optionally with a contents list."""
        self.level = level
        self.id = id
        self.level = level
        self.major = major
        if contents is not None:
            assert type(contents) is ContentList
            self.contents = contents
        else: self.contents = ContentList()
        if parents is not None:
            self.parents = parents
        else: self.parents = []
        if tags is not None:
            self.tags = tags
        else: self.tags = tagsModule.Storage()
        if flags is not None:
            self.flags = flags
        else: self.flags = []
    
    def copy(self):
        return Container(level = self.level,
                         id = self.id,
                         major = self.major,
                         contents = self.contents.copy(),
                         parents = self.parents[:],
                         tags = self.tags.copy(),
                         flags = self.flags[:])
        
    def isContainer(self):
        return True
    
    def isFile(self):
        return False
    
    def getContents(self):
        return (self.level.get(id) for id in self.contents)
    
    def getLength(self):
        """Return the length of this element, i.e. the sum of the lengths of all contents."""
        lengths = (c.getLength() for c in self.getContents())
        # Skip elements of length None
        return sum(l for l in lengths if l is not None)
    
    def getExtension(self):
        """Return the extension of all files in this container. Return None if they have different extension
        or at least one of them does not have an extension."""
        extension = None
        for element in self.getContents():
            ext = element.getExtension()
            if ext is None:
                return None
            if extension is None:
                extension = ext
            elif extension != ext:
                return None
        return extension
    
    def __repr__(self):
        return "Container[{}] with {} elements".format(self.id, len(self.contents))


class File(Element):
    
    
    def __init__(self, level, id, path, length,*, parents=None, tags=None, flags=None):
        """Initialize this element with the given id, which must be an integer or None (for external files).
        Optionally you may specify a tags.Storage object holding the tags of this element and/or a file path.
        """
        if not isinstance(id,int) or not isinstance(path,str) or not isinstance(length,int):
            raise TypeError("Invalid type (id,path,length): ({},{},{}) of types ({},{},{})"
                            .format(id,path,length,type(id),type(path),type(length)))
        self.level = level
        self.id = id
        self.level = level
        self.path = path
        self.length = length
        if parents is not None:
            self.parents = parents
        else: self.parents = []
        if tags is not None:
            self.tags = tags
        else: self.tags = tagsModule.Storage()
        if flags is not None:
            self.flags = flags
        else: self.flags = []
        
    def copy(self):
        return File( level = self.level,
                     id = self.id,
                     path = self.path,
                     length = self.length,
                     parents = self.parents[:],
                     tags = self.tags.copy(),
                     flags = self.flags[:])
    
    def isFile(self):
        return True
    
    def isContainer(self):
        return False
    
    @property
    def major(self):
        return False
    
    def getLength(self):
        """Return the length of this file."""
        return self.length
    
    def getExtension(self):
        """Return the filename extension of this file."""
        ext = os.path.splitext(self.path)[1]
        if len(ext) > 0:
            return ext[1:].lower() # remove the dot
        else: return None
        
    def __repr__(self):
        return "File[{}] {}".format(self.id, self.path)

class ContentList:
    def __init__(self, existing = None):
        if existing is not None:
            self.positions = existing.positions[:]
            self.ids = existing.ids[:]
        else:
            self.positions = []
            self.ids = []
    
    def copy(self):
        return ContentList(existing = self)
        
    def __len__(self):
        return len(self.ids)
    
    def __getitem__(self, i):
        return self.ids[i], self.positions[i]
    
    def __delitem__(self, i):
        del self.ids[i]
        del self.positions[i]
        
    def __setitem__(self, i, pos, id):
        self.positions[i] = id
        self.ids[i] = id
        
    def insert(self, pos, id):
        if pos in self.positions:
            raise ValueError("position {} for id {} already in contents ({}, {})".format(pos, id, self.positions, self.ids))
        index = bisect.bisect(self.positions, pos)
        self.positions.insert(index, pos)
        self.ids.insert(index, id)
    
    def remove(self, *args, pos = None, i = None):
        if pos is not None:
            i = self.positions.index(pos)
        elif i is None:
                raise ValueError("Either of 'pos' or 'i' must be given to ContentList.remove()")
        del self.ids[i]
        del self.positions[i]
    
    def items(self):
        return zip(self.positions, self.ids)
    
    def shift(self, delta):
        """Shift all positions by *delta*"""
        if len(self) == 0:
            return
        # ensure position doesn't drop below 1 after the shift
        assert self.positions[0] + delta  > 0
        self.positions[:] = map(lambda x: x + delta, self.positions)
    
    def __eq__(self, other):
        return self.ids == other.ids and self.positions == other.positions
    
    def __ne__(self, other):
        return not self == other