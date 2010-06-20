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

from . import Node

class RootedTreeModel(QtCore.QAbstractItemModel):
    """The RootedTreeModel subclasses QAbstractItemModel to create a simple model for QTreeViews. It takes one root node which is not considered part of the data of this model (and is not displayed by QTreeViews). Nodes in a RootedTreeModel may have every type, but must implement the following methods:
    - hasChildren(): return if a node has children
    - getChildrenCount(): return the number of children of the node
    - getChildren(): return the list of children of the node
    - getParent(): return the node's parent. The root-node' getParent-method must return None.
    The hasChildren-method allows to implement nodes that calculate the number of children not until the node is expanded the first time.
    """
    
    # The root node. Use getRoot to retrieve it.
    root = None
    
    def __init__(self,root=None):
        """Initialize a new RootedTreeModel. Optionally you can specify the root of the model."""
        QtCore.QAbstractItemModel.__init__(self)
        self.root = root
    
    def setRoot(self,root):
        """Set the root of this model to <root> and reset (QTreeViews using this model will be resetted, too)."""
        self.root = root
        self.reset()
        
    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        else: return index.internalPointer()
    
    def hasChildren(self,index):
        if not index.isValid():
            return self.root.hasChildren()
        return self.data(index).hasChildren()
        
    def rowCount(self,parent):
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            return self.root.getChildrenCount()
        else: return self.data(parent).getChildrenCount()

    def columnCount(self,parent):
        return 1
    
    def parent(self,index):
        if not index.isValid():
            return QtCore.QModelIndex()
        child = index.internalPointer()
        parent = child.getParent()
        assert parent is not None # This method should never be called on the root-node because it is not displayed in the treeview.
        if parent == self.root:
            return QtCore.QModelIndex()
        else: return self.getIndex(parent)
    
    def index(self,row,column,parent):
        if not self.hasIndex(row,column,parent): # Check if parent has a child at the given row and column
            return QtCore.QModelIndex()
        if not parent.isValid():
            parent = self.root
        else: parent = parent.internalPointer()
        child = parent.getChildren()[row]
        return self.createIndex(row,column,child)
        
    def flags(self,index):
        if not index.isValid(): # should not happen
            return Qt.ItemIsEnabled;
        else: return Qt.ItemIsEnabled | Qt.ItemIsSelectable
    
    def createIndex(self,row,column,internalPointer):
        if not isinstance(internalPointer,Node):
            raise TypeError("Internal pointers in a RootedTreeModel must be subclasses of node")
        return QtCore.QAbstractItemModel.createIndex(self,row,column,internalPointer)
        
    def getIndex(self,node):
        """Return the (Qt)-index of the given node. <node> mustn't be the rootnode, as it has no index (otherwise a ValueError is raised."""
        if node == self.root:
            raise ValueError("RootedTreeModel.getIndex: Rootnode has no Index")
        parent = node.getParent()
        return self.createIndex(parent.getChildren().index(node),0,node)