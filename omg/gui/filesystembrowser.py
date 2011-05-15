# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtGui, QtCore
from omg.config import options
from omg.gui import mainwindow

"""This module contains a dock widget that displays the music in directory view, i.e. without
considering the container structure in the database. It is meant to help building up the database.
Folders which contain music files that are not yet present in the database are marked with a
special icon."""

translate = QtCore.QCoreApplication.translate

class IconProvider(QtGui.QFileIconProvider):
    pass

class FileSystemBrowserModel(QtGui.QFileSystemModel):
    
    def __init__(self, parent = None):
        QtGui.QFileSystemModel.__init__(self, parent)
        self.setFilter(QtCore.QDir.AllEntries | QtCore.QDir.NoDotAndDotDot)
        self.dirtyFolderIcon = QtGui.QIcon("images/icons/folder_unknown.svg")
        self.musicFolderIcon = QtGui.QIcon("images/icons/folder_ok.svg")
        self.defaultFolderIcon = QtGui.QIcon("images/icons/folder.svg")

    def columnCount(self, index):
        return 1
                
        
class FileSystemBrowser(QtGui.QTreeView):
    currentDirectoriesChanged = QtCore.pyqtSignal(list, bool)
    searchDirectoryChanged = QtCore.pyqtSignal(str)
    
    def __init__(self, rootDirectory = options.main.collection, parent = None):
        QtGui.QTreeView.__init__(self, parent)
        self.setAlternatingRowColors(True)
        self.setModel(FileSystemBrowserModel())
        musikindex = self.model().setRootPath(rootDirectory)
        self.setRootIndex(musikindex)
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragDropMode(QtGui.QAbstractItemView.DragOnly)
        
    def selectionChanged(self, current, previous):
        self.currentDirectoriesChanged.emit([self.model().filePath(item) for item in self.selectedIndexes()], False)
        QtGui.QTreeView.selectionChanged(self, current, previous)
        
    def contextMenuEvent(self, event):
        if self.selectionModel().hasSelection():
            menu = QtGui.QMenu(self)
            menu.addAction(self.findAllAlbumsAction)
            menu.popup(event.globalPos())
            event.accept()
        else:
            event.ignore()

class FileSystemBrowserDock(QtGui.QDockWidget):
    """A DockWidget wrapper for the FileSystemBrowser."""
    def __init__(self, parent = None):
        QtGui.QDockWidget.__init__(self, parent)
        self.setWindowTitle(translate("FileSystemBrowser","File System Browser"))
        self.setWidget(FileSystemBrowser())
        
        
# register this widget in the main application
data = mainwindow.WidgetData(id = "filesystembrowser",
                             name = translate("FileSystemBrowser","File System Browser"),
                             theClass = FileSystemBrowserDock,
                             central = False,
                             default = True,
                             unique = False,
                             preferredDockArea = QtCore.Qt.RightDockWidgetArea)
mainwindow.addWidgetData(data)
