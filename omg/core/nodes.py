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
        """Return the number of contents (that is direct children) of this node. If *recursive* is True,
        return the number of descendants."""
        if not recursive:
            return len(self.getContents())
        else:
            # Add the children themselves: +1
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
        for node in nodes:
            node.parent = self
        if self.contents is None:
            print(self)
        self.contents[index:index] = nodes
    
    def isFile(self):
        """Return whether this node holds a file. Note that this is in general not the opposite of 
        isContainer as e.g. rootnodes are neither."""
        return False
    
    def isContainer(self):
        """Return whether this node holds a container. Note that this is in general not the opposite of
        isFile as e.g. rootnodes are neither."""
        return False
    
    def getParents(self,includeSelf=False):
        """Returns a generator yielding all parents of this node in the current tree structure, from the
        direct parent to the root-node.
        
        If *includeSelf* is True, the node itself is yielded before its ancestors.
        """
        if includeSelf:
            yield self
        parent = self.parent
        while parent is not None:
            yield parent
            parent = parent.parent
    
    def depth(self):
        """Return the depth of this node in the current tree structure. The root node has level 0."""
        if self.parent is None:
            return 0
        else: return 1 + self.parent.depth()

    def maxDepth(self):
        """Return the maximum depth of nodes below this node."""
        if self.hasContents():
            return 1 + max(node.maxDepth() for node in self.getContents())
        else: return 0

    def index(self,node):
        """Return the index of *node* in this node's contents or raise a ValueError if *node* is not found.
         See also find."""
        for i,n in enumerate(self.getContents()):
            if n == node:
                return i
        raise ValueError("Node.index: Node {} is not contained in element {}.".format(node,self))
        
    def find(self,node):
        """Return the index of *node* in this node's contents or -1 if *node* is not found. See also index."""
        for i,n in enumerate(self.contents):
            if n == node:
                return i
        return -1
    
    def getAllNodes(self, skipSelf=False):
        """Generator which will return all nodes contained in this node or in children of it, including the
        node itself if *skipSelf* is not set True.
        
        The send-method of the returned generator may be used to decide whether the generator should descend
        to the contents of the last node:
        
            generator = model.getAllNodes()
            try:
                while True:
                    descend = None # send must be invoked with None first
                    node = generator.send(descend)
                    descend = ... # decide whether the generator should yield the contents of node
                                  # If descend is set to False, the generator will skip the contents and
                                  # continue with the next sibling of node
            except StopIteration: pass
        
        See http://docs.python.org/3/reference/expressions.html#generator.send
        """
        if not skipSelf:
            descend = yield self
            if descend is False: # Remember that yield usually returns None 
                return
        for node in self.getContents():
            generator = node.getAllNodes()
            try:
                descend = None # send must be called with None first
                while True:
                    descend = yield generator.send(descend)
            except StopIteration:
                pass # continue to next node
 
    def getAllFiles(self, reverse=False):
        """Generator which will return all files contained in this node or in children of it
        (possibly including the node itself).
        
        If *reverse* is True, files will be returned in reversed order.
        """
        assert self.getContents() is not None
        if self.isFile():
            yield self
        else:
            for element in self.getContents() if not reverse else reversed(self.getContents()):
                for file in element.getAllFiles(reverse):
                    yield file

    def fileCount(self):
        """Return the number of files contained in this element or in descendants of it. If this node
        is a file, return 1."""
        if self.isFile():
            return 1
        else: return sum(node.fileCount() for node in self.getContents())
        
    def offset(self):
        """Get the offset of this element in the current tree structure. For files the offset is defined as
        the position of the file in the list of files in the whole tree (so e.g. for a playlist tree the 
        offset is the position of the file in the flat playlist). For containers the offset is defined as
        the offset that a file at the container's location in the tree would have (if the container contains
        at least one file, this is the offset of the first file among its descendants)."""
        if self.parent is None:
            return 0 # rootnode has offset 0
        else:
            # start with the parent's offset and add child.fileCount() for each child before this node
            offset = self.parent.offset()
            for child in self.parent.getContents():
                if child == self:
                    return offset
                else: offset += child.fileCount()
            raise ValueError("Node.getOffset: Node {} is not contained in its parent {}."
                                .format(self,self.parent))
    
    def fileAtOffset(self,offset,allowFileCount=False):
        """Return the file at the given *offset*. Note that *offset* is relative to this node, so only the
        tree below this node will be searched.
        
        Usually the inequality 0 <= *offset* < self.fileCount() must be valid. If *allowFileCount* is True,
        *offset* may equal self.fileCount(). In that case None is returned, as the offset points behind all
        files (that position is usually only interesting for insert operations).
        """
        if offset == 0 and self.isFile():
            return self
        else: 
            child,innerOffset = self.childAtOffset(offset)
            if child is None: # offset == self.fileCount()
                if allowFileCount:
                    return None
                else: raise IndexError("Offset {} is out of bounds (equals fileCount)".format(offset))
            if child.isFile():
                return child
            else: return child.fileAtOffset(innerOffset)
        
    def childIndexAtOffset(self,offset):
        """Return a tuple: the index of the child C that contains the file F with the given offset (relative
        to this element) and the offset of F relative to C ("inner offset").
        For example: If this element is the rootnode of a playlist tree containing an album with 13 songs and
        a second one with 12 songs, then getChildIndexAtOffset(17) will return (1,3), since the 18th file in
        the playlist (i.e. with offset 17), is contained in the second child (i.e with index 1) and it is the
        4th song in that child (i.e. it has offset 3 relative to the album).
        
        If *offset* points to the last position inside this node (in other words offset == self.fileCount()),
        then (None,None) is returned.
        """
        if offset < 0:
            raise IndexError("Offset {} is out of bounds".format(offset))
        cOffset = 0
        for i in range(0,self.getContentsCount()):
            fileCount = self.contents[i].fileCount()
            if offset < cOffset + fileCount: # offset points to a file somewhere in self.contents[i]
                return i,offset-cOffset 
            else: cOffset += fileCount
        if offset == cOffset: # offset points to the end of the list of files below self
            return None,None
        raise IndexError("Offset {} is out of bounds".format(offset))
    
    def childAtOffset(self,offset):
        """Return the child containing the file with the given (relative) offset, and the offset of that file
        relative to the child. This is a convenience-method for
        getContents()[getChildIndexAtOffset(offset)[0]]. Confer getChildIndexAtOffset.
        
        If *offset* points to the last position inside this node (in other words offset == self.fileCount()),
        then (None,None) is returned.
        """
        index,innerOffset = self.childIndexAtOffset(offset)
        if index is None:
            return None,None
        else: return self.getContents()[index],innerOffset
    
    def firstLeaf(self,allowSelf=False):
        """Return the first leaf below this node (i.e. the node without children with the lowest offset). If
        this node does not have children, return None or, if *allowSelf* is True, return the node itself.
        """
        if self.hasContents():
            return self.getContents()[0].firstLeaf(allowSelf=True)
        else: return self if allowSelf else None
        
    def lastLeaf(self,allowSelf=False):
        """Return the last leaf below this node (i.e. the node without children with the highest offset). If
        this node does not have children, return None or, if *allowSelf* is True, return the node itself.
        """
        if self.hasContents():
            return self.getContents()[-1].lastLeaf(allowSelf=True)
        else: return self if allowSelf else None
            
    def wrapperString(self,includeSelf=False,strFunc=None):
        """Return a string that stores the tree structure below this node. If this string is submitted to
        Level.createWrappers the same tree will be created again. There are some limitations though:
        
            - the tree below this node must contain only Wrappers,
            - to store Wrappers their id is used. Thus you cannot persistently store trees that contain
              temporary elements (negative ids).
              
        Both limitations can be circumvented specifying a custom *strFunc*: It must take a node and
        return a string and is used to convert the node to a string. Strings returned by *strFunc* must not
        contain the characters ',[]'.
        """
        if includeSelf:
            if strFunc is None and not isinstance(self,Wrapper):
                raise ValueError('wrapperString: Tree must contain only Wrappers if *strFunc* is None')
            selfString = str(self.element.id) if strFunc is None else strFunc(self)
            
        if self.hasContents():
            childrenString = ','.join(c.wrapperString(includeSelf=True,strFunc=strFunc)
                                      for c in self.getContents())
            if includeSelf:
                return selfString+'['+childrenString+']'
            else: return childrenString
        else:
            if includeSelf:
                return selfString
            else: return ''
        
    def printStructure(self, indent = ''):
        """Debug method: print the tree below this node using indentation."""
        print(indent + str(self))
        for child in self.getContents():
            child.printStructure(indent + '  ')


class RootNode(Node):
    """Rootnodes are used at the top of RootedTreeModel. They are not displayed within the GUI, but recursive
    tree operations are much simpler if there is a single root node instead of a list of (visible) roots."""
    def __init__(self, model):
        self.contents = []
        self.model = model
        self.parent = None
    
    def __repr__(self):
        return 'RootNode with {} contents'.format(len(self.contents))    


class Wrapper(Node):
    """A node that marks an element's location in a tree. On each level there is only one instance of each
    element and this instance has a fixed list of contents and parents and corresponding positions. To use
    elements in trees they must be wrapped by a wrapper which has only one parent and position and its own
    list of contents. Usually both parent and contents contain wrappers again (and usually the elements of
    those wrappers are an actual parent/contents of the element, but this is not obligatory).
    
    Arguments:
    
        *element*: the element instance wrapped by this wrapper,
        *contents*: the list of contents of this wrapper. Usually these are other wrappers. Note that the
                    list won't be copied but the parents of the list entries will be adjusted.
                    If this wrapper wraps a file, this argument must be None. For containers it may be None,
                    in which case the wrapper will be initialized with an empty list.
        *position*: the position of this wrapper. May be None.
        *parent*: the parent (usually another wrapper or a rootnode)
        
    """
    def __init__(self,element,*,contents=None,position=None,parent=None):
        self.element = element
        self.position = position
        self.parent = parent
        if element.isContainer():
            if contents is not None:
                self.setContents(contents)
            else: self.contents = []
        else:
            if contents is not None:
                raise ValueError("contents must be None for a File-wrapper")
            self.contents = None
        
    def copy(self,contents=None,level=None):
        """Return a copy of this wrapper. Because a flat copy of the contents is not possible (parent
        pointers would be wrong) all contents are copied recursively. Instead of this you can optionally
        specify a list of contents that will be put into the copy regardless of the original's contents.
        
        If *level* is not None, the copy will use elements from the given level instead of the original
        elements (this is for example necessary when dropping elements from level to another).
        """
        element = self.element if level is None else level.collect(self.element.id)
        copy = Wrapper(element, contents=None, position=self.position, parent=self.parent)
        if self.isContainer():
            if contents is None:
                copy.setContents([child.copy(level=level) for child in self.contents])
            else: copy.setContents(contents)
        return copy
    
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
        """Fill this wrapper with exactly the contents of the underlying element. If *recursive* is True,
        load the contents of all children in the same way."""
        if self.element.isContainer():
            self.setContents([Wrapper(self.element.level.collect(id), position = pos)
                                    for pos,id in self.element.contents.items()])
            if recursive:
                for child in self.contents:
                    child.loadContents(recursive)
    
    def getTitle(self,prependPosition=False,usePath=True):
        """Return the title of the wrapped element. If *prependPosition* is True and this wrapper has a
        position, prepend it to the title. See also Element.getTitle.
        """
        title = self.element.getTitle(usePath)
        if prependPosition and self.position is not None:
            return "{} - {}".format(self.position,title)
        else: return title
        
    def toolTipText(self):
        """Return a text to use as tooltip over this wrapper."""
        parts = []
        if self.element.tags is not None:
            parts.append('\n'.join('{}: {}'.format(tag.title,', '.join(map(str,values)))
                                    for tag,values in self.element.tags.items()))
        if self.element.flags is not None and len(self.element.flags) > 0:
            parts.append(translate('Wrapper','Flags: {}').format(
                                                        ', '.join(flag.name for flag in self.element.flags)))
        if self.element.isFile():
            parts.append(translate('Wrapper','URL: {}').format(self.element.url))
        if len(parts) > 0:
            return '\n'.join(parts)
        else: return str(self)
        
    def getLength(self):
        """Return the length of this element, i.e. the sum of the lengths of all contents."""
        if self.isFile():
            return self.element.length
        else: return sum(wrapper.getLength() for wrapper in self.contents)
    
    def getExtension(self):
        """Return the extension of all files in this container. Return None if they have different extension
        or at least one of them does not have an extension."""
        if self.isFile():
            return self.element.getExtension()
        else:
            extension = None
            for wrapper in self.contents:
                ext = wrapper.getExtension()
                if ext is None:
                    return None
                if extension is None:
                    extension = ext
                elif extension != ext:
                    return None
            return extension
    
    def __repr__(self):
        return "<W: {}>".format(self.getTitle()) 

    # Note that no __eq__ method is defined for wrappers. Different wrapper instances really are different.
