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
from PyQt4.QtCore import Qt

import itertools
from . import Node, Element, RootNode
from .. import logging
logger = logging.getLogger(name="models")

class RootedTreeModel(QtCore.QAbstractItemModel):
    """The RootedTreeModel subclasses QAbstractItemModel to create a simple model for QTreeViews. It takes one
    root node which is not considered part of the data of this model (and is not displayed by QTreeViews).
    Nodes in a RootedTreeModel may have every type, but must implement the following methods:
    
        - hasChildren(): return if a node has children
        - getChildrenCount(): return the number of children of the node
        - getChildren(): return the list of children of the node
        - getParent(): return the node's parent. The root-node' getParent-method must return None.
        
    The hasChildren-method allows to implement nodes that calculate the number of children not until the node
    is expanded the first time.
    """
    
    # The root node. Use getRoot to retrieve it.
    root = None
    
    def __init__(self,root=None):
        """Initialize a new RootedTreeModel. Optionally you can specify the root of the model."""
        QtCore.QAbstractItemModel.__init__(self)
        self.root = root
    
    def getRoot(self):
        """Return the root node of this model."""
        return self.root
        
    def setRoot(self,root):
        """Set the root of this model to *root* and reset (QTreeViews using this model will be reset, too)."""
        self.root = root
        self.reset()
    
    def clear(self):
        self.beginResetModel()
        self.root.contents = []
        self.endResetModel()
        
    def data(self,index,role=Qt.EditRole):
        if not index.isValid():
            if role == Qt.EditRole:
                return self.root
            else:
                return None
        if role == Qt.DisplayRole:
            return str(index.internalPointer())
        if role == Qt.EditRole:
            return index.internalPointer()
        if role == Qt.ToolTipRole:
            return self.toolTipText(index)
        return None
    
    def toolTipText(self, index):
        if index:
            element = index.internalPointer()
            if hasattr(element, "toolTipText"):
                return element.toolTipText()
            else:
                return str(element)
            
    def hasChildren(self,index):
        if not index.isValid():
            if self.root is None:
                return False
            else: return self.root.hasContents()
        else: return self.data(index).hasContents()
        
    def rowCount(self,parent):
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            if self.root is None:
                return 0
            return self.root.getContentsCount()
        else: return self.data(parent).getContentsCount()

    def columnCount(self,parent):
        return 1
    
    def parent(self,index):
        if not index.isValid():
            return QtCore.QModelIndex()
        child = index.internalPointer()
        parent = child.getParent()
        # This method should never be called on the root-node because it is not displayed in the treeview.
        assert parent is not None
        if parent == self.root:
            return QtCore.QModelIndex()
        else: return self.getIndex(parent)
    
    def index(self,row,column,parent):
        if not self.hasIndex(row,column,parent): # Check if parent has a child at the given row and column
            return QtCore.QModelIndex()
        if not parent.isValid():
            parent = self.root
        else:
            parent = parent.internalPointer()
        child = parent.getContents()[row]
        return self.createIndex(row,column,child)
        
    def flags(self,index):
        if not index.isValid(): 
            # may happen during drag and drop
            # http://doc.trolltech.com/4.4/model-view-dnd.html#enabling-drag-and-drop-for-items
            return Qt.ItemIsEnabled;
        else: return Qt.ItemIsEnabled | Qt.ItemIsSelectable
    
    def createIndex(self,row,column,internalPointer):
        if not isinstance(internalPointer,Node):
            raise TypeError("Internal pointers in a RootedTreeModel must be subclasses of Node, but got {}"
                               .format(type(internalPointer)))
        return QtCore.QAbstractItemModel.createIndex(self,row,column,internalPointer)
        
    def getIndex(self,node):
        """Return the (Qt)-index of the given node. If <node> is the root of this model, return an invalid
        QModelIndex."""
        if node == self.root:
            return QtCore.QModelIndex()
        parent = node.getParent()
        try:
            parent.getContents().index(node)
        except ValueError:
            raise RuntimeError("Cannot create an index for node {} because ".format(node)
                               + "it is not contained in its alleged parent {}.".format(parent))
            
        return self.createIndex(parent.getContents().index(node),0,node)     

    def getAllNodes(self):
        """Generator which will return all nodes contained in the tree in depth-first-manner."""
        return self.root.getAllNodes()
    
    def breadthFirstTraversal(self):
        """Generator which will return all nodes contained in the tree in breadth-first-manner."""
        # Warning: The autoLoad feature of BrowserModel depends on some implementation details of this method.
        # (the problem is that CriterionNodes load their contents during the bfs.)
        queue = [self.root]
        while len(queue) > 0:
            node = queue.pop(0)
            for child in node.getContents():
                if child.hasContents():
                    queue.append(child)
                yield child
    
    def changePositions(self, parent, changes):
        #TODO: finish & use in event handling
        elementParent = isinstance(parent, Element)
        
        
        for before, after in changes:
            for i, elem in parent.contents:
                afterIndex = -1
                current = elem.position if elementParent else i
                if current == before:
                    beforeIndex = i
                    if elementParent:
                        elem.position = after
                if afterIndex == -1 and after <= current:
                    afterIndex = i
            if afterIndex == -1:
                afterIndex = len(parent.contents)
          
    def insert(self,parent,insertions):
        """Insert nodes below *parent*. *insertions* is a list of (int, Element) tuples. The integer is
        either the position (if *parent* is an Element) or the index (otherwise) of the inserted Element.
        This method always copies elements before insertion."""
        insertionIter = iter(sorted(insertions))
        insertPos, insertElem = next(insertionIter)
        logger.debug(insertions)
        lastIndex = len(parent.contents)
        offset = 0
        insertJobs = []
        allSeen = False
        for i, node in itertools.chain(enumerate(parent.contents), [(lastIndex, None)]):
            print(i, node)
            insertHere = []
            current = node.position if node and isinstance(parent, Element) else i
            try:
                while node is None or insertPos < current:
                    insertHere.append( insertElem.copy() )
                    insertPos, insertElem = next(insertionIter)
            except StopIteration:
                allSeen = True
            if len(insertHere) > 0:
                insertJobs.append(( i + offset, insertHere))
                offset += len(insertHere)
            if allSeen:
                break
        for i, nodes in insertJobs:
            self.beginInsertRows(self.getIndex(parent), i, i+len(nodes)-1)
            parent.insertContents(i, nodes)
            self.endInsertRows()
