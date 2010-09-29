# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtGui, QtCore
from omg.config import options

class FileSystemBrowserModel(QtGui.QFileSystemModel):
    
    def __init__(self, parent = None):
        QtGui.QFileSystemModel.__init__(self, parent)
        self.setFilter(QtCore.QDir.AllDirs | QtCore.QDir.NoDotAndDotDot)

    def columnCount(self, index):
        return 1
        
class FileSystemBrowser(QtGui.QTreeView):
    
    currentDirectoriesChanged = QtCore.pyqtSignal(list, bool)
    searchDirectoryChanged = QtCore.pyqtSignal(str)
    
    def __init__(self, rootDirectory = options.music.collection, parent = None):
        QtGui.QTreeView.__init__(self, parent)
        self.setAlternatingRowColors(True)
        self.setModel(FileSystemBrowserModel())
        musikindex = self.model().setRootPath(rootDirectory)
        self.setRootIndex(musikindex)
        self.setSelectionMode(self.ExtendedSelection)
        self.doubleClicked.connect(self._handleDoubleClick)
        self.setDragDropMode(QtGui.QAbstractItemView.DragOnly)
        
        self.findAllAlbumsAction = QtGui.QAction("find all albums here now", self)
        self.findAllAlbumsAction.triggered.connect(self._handleFindAllAlbums)
        
    def selectionChanged(self, current, previous):
        self.currentDirectoriesChanged.emit([self.model().filePath(item) for item in self.selectedIndexes()], False)
        QtGui.QTreeView.selectionChanged(self, current, previous)
        
    def _handleFindAllAlbums(self):
        paths = [self.model().filePath(index) for index in self.selectedIndexes()]
        self.currentDirectoriesChanged.emit(paths, True)
        
    def contextMenuEvent(self, event):
        if self.selectionModel().hasSelection():
            menu = QtGui.QMenu(self)
            menu.addAction(self.findAllAlbumsAction)
            menu.popup(event.globalPos())
            event.accept()
        else:
            event.ignore()
    
    def _handleDoubleClick(self, index):
        self.searchDirectoryChanged.emit(self.model().filePath(index))
        

#class FileListView(QtGui.QTableView):