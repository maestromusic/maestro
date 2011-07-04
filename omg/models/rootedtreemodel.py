#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtCore
from PyQt4.QtCore import Qt

from . import Node, Element, RootNode
#from omg.gui import formatter


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
        else: 
            #if not hasattr(self.data(index),'hasContents'):
            #    print(self.data(index))
            return self.data(index).hasContents()
        
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
            print("Cannot create an index for node {} because it is not contained in its alleged parent {}."
                    .format(node,parent))
        return self.createIndex(parent.getContents().index(node),0,node)

    def getAllNodes(self):
        """Generator which will return all nodes contained in the tree in depth-first-manner."""
        for element in self.contents:
            for sub in element.getAllNodes():
                yield sub
    
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


class EditableRootedTreeModel(RootedTreeModel):
    """EditableRootedTreeModel extends RootedTreeModel to include functions that modify the tree structure."""
    def insert(self,parent,pos,node):
        """Insert *node* at position *pos* into *parent*."""
        self.insertMany(parent,pos,[node])

    def insertMany(self,parent,pos,nodes):
        """Insert the given nodes at position *pos* into *parent*."""
        self.beginInsertRows(self.getIndex(parent),pos,pos+len(nodes)-1)
        parent.getContents()[pos:pos] = nodes
        for node in nodes:
            node.setParent(parent)
        self.endInsertRows()
        
    def remove(self,node):
        """Remove *node* and all of its children from the model."""
        parent = node.getParent()
        if parent is None:
            raise ValueError("Cannot remove root node.")
        pos = parent.index(node)
        self.beginRemoveRows(self.getIndex(parent),pos,pos)
        del parent.getContents()[pos]
        self.endRemoveRows()
        
    def removeByIndex(self,index):
        """Remove the node with Qt-index *index*."""
        if not index.isValid():
            raise ValueError("removeByIndex needs a valid index.")
        self.remove(self.data(index))

    def move(self,sourceParent,sourceFirst,sourceLast,destParent,pos):
        """Move the children of *sourceParent* with position *sourceFirst* up to and including *sourceLast*
        into *destParent* and insert them at position *pos*. Make sure that the move is valid or an exception
        is raised:

            - You must not move nodes into one of their children.
            - If *sourceParent* equals *destParent*, *pos* must not be in the range
              *sourceFirst* ... *sourceLast*+1.

        In the latter case confer http://doc.qt.nokia.com/stable/qabstractitemmodel.html#beginMoveRows for
        the correct way to specify the positions (basically this function needs the old positions before
        anything has happened).
        """
        if sourceParent == destParent and pos >= sourceFirst and pos <= sourceLast + 1:
            raise ValueError("Invalid positions in move: pos ∈ [sourceFirst,sourceLast+1]. Exact values"
                            + " were (pos,sourceFirst,sourceLast) = ({},{},{})."""
                            .format(pos,sourceFirst,sourceLast))
        ok = self.beginMoveRows(self.getIndex(sourceParent),sourceFirst,sourceLast,
                                self.getIndex(destParent),pos)
        if not ok:
            raise ValueError("Cannot move nodes.")
            
        movingNodes = sourceParent.getContents()[sourceFirst:sourceLast+1]
        if pos < sourceFirst:
            # First remove, then insert
            del sourceParent.getContents()[sourceFirst:sourceLast+1]
            destParent.getContents()[pos:pos] = movingNodes
        else:
            destParent.getContentn()[pos:pos] = movingNodes
            del sourceParent.getContents()[sourceFirst:sourceLast+1]
        for node in movingNodes:
            node.setParent(destParent)
        self.endMoveRows()
        
    def flatten(self,node):
        """Replace *node* by its children. *node* must have at least one child."""
        if node == self.root:
            raise ValueError("Cannot flatten root node.")
        if not node.hasContents():
            raise ValueError("Cannot flatten empty nodes.")
        parent = node.getParent()
        pos = parent.index(node)
        # Move children behind the node
        self.move(node,0,node.getChildrenCount()-1,parent,pos+1)
        # and remove the node itself
        self.remove(node)

    def split(self,node,pos):
        """Split *node* at position *pos*: Insert a copy of *node* directly after it and insert all children
        of *node* with position *pos* or higher into the copy. If *pos* equals 0 or the number of children of
        node, do nothing and return False (you cannot split at the boundary). Otherwise return True."""
        if node == self.root:
            raise ValueError("Cannot split root node.")
        if pos < 0 or pos > node.getContentsCount():
            raise ValueError("Invalid position: {}".format(pos))
        if pos == 0 or pos == node.getContentsCount():
            return False # nothing to do here
        parent = node.getParent()
        nodePos = parent.index(node)
        # Do not copy the contents
        copy = node.copy(contents=[])
        self.insert(parent,nodePos+1,copy)
        self.move(node,pos,node.getContentsCount()-1,copy,0)
        return True

    def insertParent(self,parent,startPos,endPos,newParent):
        """Add a new node *newParent* between *parent* and some of its children. To be precise: Replace the
        children with positions *startPos* up to and including *endPos* by *newParent* and insert those nodes
        as children into *newParent* (at position 0).""" 
        if startPos < 0 or endPos < startPos or endPos >= parent.getContentsCount():
            raise ValueError("Invalid start or end position in insertParent ({} and {}).".format(startPos,endPos))
        if newParent == parent:
            raise ValueError("parent and newParent must be distinct.")
        self.insert(parent,startPos,newParent)
        self.move(parent,startPos+1,endPos+1,newParent,0)
