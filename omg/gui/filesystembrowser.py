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

import os

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from . import mainwindow, selection
from .. import filebackends, filesystem, config
from ..utils import relPath, getIcon, hasKnownExtension
from ..core import levels


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
        'unknown'  : getIcon("folder_unknown.svg"),
        'problem'  : getIcon("folder_problem.svg") }
    
    descriptions = {
        'unsynced' : translate(__name__, "contains music which is not in OMG's database"),
        'ok'       : translate(__name__, "in sync with OMG's database"),
        'nomusic'  : translate(__name__, "does not contain music"),
        'unknown'  : translate(__name__, "unknown folder status"),
        'problem'  : translate(__name__, "conflict with database") }
    
    def __init__(self, parent = None):
        QtGui.QFileSystemModel.__init__(self, parent)
        self.setFilter(QtCore.QDir.AllEntries | QtCore.QDir.NoDotAndDotDot)

    def columnCount(self, index):
        return 1
    
    @QtCore.pyqtSlot(object)
    def handleStateChange(self, dir):
        index = self.index(dir.absPath)
        self.dataChanged.emit(index, index)    
    
    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DecorationRole or role == Qt.ToolTipRole:
            info = self.fileInfo(index)
            if os.path.isdir(info.absoluteFilePath()):
                dir = relPath(info.absoluteFilePath())
                if dir == '..':
                    return super().data(index, role)
                status = filesystem.getFolderState(dir)
                if role == Qt.DecorationRole:
                    return self.icons[status]
                else:
                    return self.descriptions[status]
        return super().data(index, role) 
    
class FileSystemBrowser(QtGui.QTreeView):
    def __init__(self, rootDirectory=config.options.main.collection, parent=None):
        QtGui.QTreeView.__init__(self, parent)
        self.setAlternatingRowColors(True)
        self.setModel(FileSystemBrowserModel())
        musikindex = self.model().setRootPath(rootDirectory)
        self.setRootIndex(musikindex)
        if filesystem.enabled:
            filesystem.synchronizer.folderStateChanged.connect(self.model().handleStateChange)
            filesystem.synchronizer.initializationComplete.connect(self.model().layoutChanged)
        
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragDropMode(QtGui.QAbstractItemView.DragOnly)
        
    def selectionChanged(self, selected, deselected):
        super().selectionChanged(selected, deselected)
        paths = [relPath(self.model().filePath(index)) for index in self.selectedIndexes()
                        if not self.model().isDir(index)] # TODO: remove this restriction
        s = FileSystemSelection([p for p in paths if hasKnownExtension(p)])
        if s.hasFiles():
            selection.setGlobalSelection(s) 

class FileSystemBrowserDock(QtGui.QDockWidget):
    """A DockWidget wrapper for the FileSystemBrowser."""
    def __init__(self,parent=None,location=None):
        QtGui.QDockWidget.__init__(self, parent)
        self.setWindowTitle(translate(__name__,"Filesystem: {}").format(config.options.main.collection))
        self.setWidget(FileSystemBrowser())
        

class FileSystemSelection(selection.NodeSelection):
    
    def __init__(self, paths):
        super().__init__(levels.real,[])
        urls = [filebackends.BackendURL.fromString("file:///" + path) for path in paths]
        self._files = levels.real.getFromUrls(urls)
        
    def elements(self,recursive=False):
        return self._files
    
    def files(self,recursive=False):
        return self._files
        
    def hasFiles(self):
        return len(self._files) > 0
    
    def hasElements(self):
        return len(self._files) > 0
        
        
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
