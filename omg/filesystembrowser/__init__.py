# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtGui, QtCore
from omg import config

class FileSystemBrowserModel(QtGui.QFileSystemModel):
    
    def __init__(self, parent = None):
        QtGui.QFileSystemModel.__init__(self, parent)
        self.setFilter(QtCore.QDir.AllDirs | QtCore.QDir.NoDotAndDotDot)

    def columnCount(self, index):
        return 1
        
class FileSystemBrowser(QtGui.QTreeView):
    
    currentDirectoryChanged = QtCore.pyqtSignal(['QString'])
    searchDirectoryChanged = QtCore.pyqtSignal(['QString'])
    
    def __init__(self, rootDirectory = config.get("music","collection"), parent = None):
        QtGui.QTreeView.__init__(self, parent)
        self.setAlternatingRowColors(True)
        self.model = FileSystemBrowserModel()
        self.setModel(self.model)
        musikindex = self.model.setRootPath(rootDirectory)
        self.setRootIndex(musikindex)
        self.selectionModel().currentChanged.connect(self._handleCurrentChanged)
        self.doubleClicked.connect(self._handleDoubleClick)
        self.setDragDropMode(QtGui.QAbstractItemView.DragOnly)
        
    def _handleCurrentChanged(self, current, previous):
        self.currentDirectoryChanged.emit(self.model.filePath(current))
    
    def _handleDoubleClick(self, index):
        self.searchDirectoryChanged.emit(self.model.filePath(index))