# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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

from PyQt5 import QtCore
from PyQt5.QtCore import Qt


class SimpleListModel(QtCore.QAbstractListModel):
    """SimpleListModel wraps a list model around a simple Python list. It's data-function will return the
    elements in the list for the edit-role and a string-representation of them for the DisplayRole. Thus this
    class provides an easy way to get a list of arbitrary Python-objects into a QListView.
    """
    def __init__(self,items=None,strFunction=str):
        """Initialize the model. You may specify a list of *items* to start and a function *strFunction* to
        get the string representation from items (by default the built-in function str is used)."""
        QtCore.QAbstractListModel.__init__(self)
        self.items = items if items is not None else []
        self.strFunction = strFunction
        self.editable = False
        
    def getItems(self):
        """Return the list of items within this model."""
        return self.items
    
    def setItems(self,items):
        """Set the list of this model's items. The model will emit a reset-signal."""
        self.beginResetModel()
        self.items = items
        self.endResetModel()
    
    def isEditable(self):
        """Return whether the model is editable, that is whether the model's flags-function sets the
        Qt.ItemIsEditable-flag."""
        return self.editable
    
    def setEditable(self,editable):
        """Make the model's flags-function set the Qt.ItemIsEditable flag for all items - or not."""
        self.editable = editable
        
    def rowCount(self,parent=None):
        if parent is not None and parent.isValid():
            return 0
        return len(self.items)
    
    def data(self,index,role=Qt.EditRole):
        if 0 <= index.row() < len(self.items):
            if role == Qt.EditRole:
                return self.items[index.row()]
            elif role == Qt.DisplayRole:
                return self.strFunction(self.items[index.row()])
            else: return None
        else: return None
        
    def setData(self,index,value,role=Qt.EditRole):
        if 0 <= index.row() < len(self.items):
            if role == Qt.EditRole:
                self.items[index.row()].value = value
            else: return False
            self.dataChanged.emit(index,index)
            return True
        else: return False
    
    def flags(self,index):
        if self.editable:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
        else: return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        