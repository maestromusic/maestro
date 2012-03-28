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

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt
import os
from . import mainwindow
from ..utils import relPath, absPath, getIcon
from .. import filesystem, config

"""This module contains a dock widget that displays the music in directory view, i.e. without
considering the container structure in the database. It is meant to help building up the database.
Folders which contain music files that are not yet present in the database are marked with a
special icon."""

translate = QtCore.QCoreApplication.translate

class FileSystemBrowserModel(QtGui.QFileSystemModel):
    
    icons = {
        'unsynced' : getIcon("folder_unsynced.svg"),
        'ok'       : getIcon("folder_ok.svg"),
        'nomusic'  : getIcon("folder.svg"),
        'unknown'  : getIcon("folder_unknown.svg") }
    
    def __init__(self, parent = None):
        QtGui.QFileSystemModel.__init__(self, parent)
        self.setFilter(QtCore.QDir.AllEntries | QtCore.QDir.NoDotAndDotDot)
        if filesystem.syncThread is not None:
            filesystem.syncThread.folderStateChanged.connect(self.handleStateChange)

    def columnCount(self, index):
        return 1
    
    @QtCore.pyqtSlot(str, str)
    def handleStateChange(self, folder, state):
        index = self.index(absPath(folder))
        self.dataChanged.emit(index, index)
        while(index.parent().isValid()):
            index = index.parent()
            self.dataChanged.emit(index, index)    
    
    def data(self, index, role = Qt.DisplayRole):
        if role == Qt.DecorationRole:
            info = self.fileInfo(index)
            if os.path.isdir(info.absoluteFilePath()):
                dir = relPath(info.absoluteFilePath())
                if dir == '..':
                    return super().data(index, role)
                try:
                    status = filesystem.folderStatus(dir)
                except KeyError:
                    status = 'unsynced'
                return self.icons[status]
        return super().data(index, role)
    
class FileSystemBrowser(QtGui.QTreeView):
    
    def __init__(self, rootDirectory = config.options.main.collection, parent = None):
        QtGui.QTreeView.__init__(self, parent)
        self.setAlternatingRowColors(True)
        self.setModel(FileSystemBrowserModel())
        musikindex = self.model().setRootPath(rootDirectory)
        self.setRootIndex(musikindex)
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragDropMode(QtGui.QAbstractItemView.DragOnly)

class FileSystemBrowserDock(QtGui.QDockWidget):
    """A DockWidget wrapper for the FileSystemBrowser."""
    def __init__(self,parent=None,location=None):
        QtGui.QDockWidget.__init__(self, parent)
        self.setWindowTitle(translate("FileSystemBrowser","File System Browser"))
        self.setWidget(FileSystemBrowser())
        
        
# register this widget in the main application
data = mainwindow.WidgetData(id = "filesystembrowser",
                             name = translate("FileSystemBrowser","File System Browser"),
                             theClass = FileSystemBrowserDock,
                             central = False,
                             dock = True,
                             default = True,
                             unique = False,
                             preferredDockArea = QtCore.Qt.RightDockWidgetArea)
mainwindow.addWidgetData(data)
