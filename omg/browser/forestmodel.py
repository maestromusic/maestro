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
from omg.models import Element

class ForestModel(QtCore.QAbstractItemModel):
    """ForestModel is a simple model for QTreeViews. It takes a list of root elements which may have child elements. Elements in a ForestModel may have every type Each element in the ForestModel must have the following methods:
    - getElements(): return the list of childrens of the element
    - getElementCount(): return the number of childrens of the element
    - getParent(): return the element's parent or None if the element is a root
    """
    
    # List of the roots of the trees stored in this model
    _roots = []

    def __init__(self,roots):
        """Initialize a new ForestModel with the given list of roots."""
        QtCore.QAbstractItemModel.__init__(self)
        self._roots = roots
    
    def setRoots(self,roots):
        """Set the list of roots of this ForestModel and reset the model so that QTreeViews using this model will be resetted."""
        self._roots = roots
        self.reset()
    
    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        return index.internalPointer()
    
    def rowCount(self,parent):
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            return len(self._roots)
        else: return self.data(parent).getElementsCount()

    def columnCount(self,parent):
        return 1
    
    def parent(self,index):
        if not index.isValid():
            return QtCore.QModelIndex()
        child = index.internalPointer()
        parent = child.getParent()
        if parent is None: # toplevel element
            return QtCore.QModelIndex()
        else: # Now we must find out the list containing the parent to get the parent's position in this list
            if parent.getParent() is None:
                containingList = self._roots
            else: containingList = parent.getParent().getElements()
            return self.createIndex(containingList.index(parent),0,parent)
    
    def index(self,row,column,parent):
        if not self.hasIndex(row,column,parent): # Check if parent has a child at the given row and column
            return QtCore.QModelIndex()
        if parent.isValid():
            child = parent.internalPointer().getElements()[row]
        else: child = self._roots[row] 
        return self.createIndex(row,column,child)
        
    def flags(self,index):
        if not index.isValid():
            return Qt.ItemIsEnabled;
        else: return Qt.ItemIsEnabled | Qt.ItemIsSelectable