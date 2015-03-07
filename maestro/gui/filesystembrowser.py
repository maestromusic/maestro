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

import os

from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtCore import Qt
from maestro.core import urls

translate = QtCore.QCoreApplication.translate

from maestro import application, filesystem, utils, widgets
from maestro.gui import selection, widgets as guiwidgets
from maestro.core import levels
from maestro.filesystem.sources import FilesystemState


"""This module contains a dock widget that displays the music in directory view, i.e. without
considering the container structure in the database. It is meant to help building up the database.
Folders which contain music files that are not yet present in the database are marked with a
special icon."""


class FileSystemBrowserModel(QtWidgets.QFileSystemModel):
    """Model class for the file system browser.
    
    In contrast to QFileSystemModel, this returns folder and file icons depending on the state
    ("nomusic", "unsynced", etc.) and according tooltips.
    """
    
    folderIcons = {
        FilesystemState.unsynced : utils.getIcon("folder_unsynced.svg"),
        FilesystemState.synced   : utils.getIcon("folder_ok.svg"),
        FilesystemState.empty    : utils.getIcon("folder.svg"),
        FilesystemState.unknown  : utils.getIcon("folder_unknown.svg")}
    
    fileIcons = {
        FilesystemState.unsynced : utils.getIcon("file_unsynced.svg"),
        FilesystemState.synced   : utils.getIcon("file_ok.svg"),
        FilesystemState.unknown  : utils.getIcon("file_unknown.svg")}
    
    descriptions = {
        FilesystemState.unsynced : translate("FileSystemBrowserModel",
                                             "contains files that are not in Maestro's database"),
        FilesystemState.synced   : translate("FileSystemBrowserModel",
                                             "in sync with Maestro's database"),
        FilesystemState.empty    : translate("FileSystemBrowserModel",
                                             "empty directory"),
        FilesystemState.unknown  : translate("FileSystemBrowserModel", "unknown status")}
    
    def __init__(self, parent=None):
        QtWidgets.QFileSystemModel.__init__(self, parent)
        self.setFilter(QtCore.QDir.AllEntries | QtCore.QDir.NoDotAndDotDot)
        self.source = None
        self.setRootPath(None)
        
    def setSource(self, source):
        if source != self.source:
            if self.source is not None:
                self.source.fileStateChanged.disconnect(self.handleStateChange)
                self.source.folderStateChanged.disconnect(self.handleStateChange)
            self.source = source
            self.setRootPath(source.path)
            source.folderStateChanged.connect(self.handleStateChange)
            source.fileStateChanged.connect(self.handleStateChange)
            
    def columnCount(self, index):
        return 1

    def handleStateChange(self, path):
        index = self.index(path)
        self.dataChanged.emit(index, index)   
    
    def data(self, index, role=Qt.DisplayRole):
        """Overridden for DecorationRole and ToolTipRole."""
        if role == Qt.DecorationRole or role == Qt.ToolTipRole:
            info = self.fileInfo(index)
            if os.path.isdir(info.absoluteFilePath()):
                dirpath = info.absoluteFilePath()
                if dirpath == '..':
                    return super().data(index, role)
                status = self.source.folderState(dirpath)
                if role == Qt.DecorationRole:
                    return self.folderIcons[status]
                else:
                    return dirpath + '\n' + self.descriptions[status]
            else:
                status = self.source.fileState(info.absoluteFilePath())
                if role == Qt.DecorationRole:
                    return self.fileIcons[status]
                else:
                    return str(info.absoluteFilePath()) + '\n' + self.descriptions[status]
        return super().data(index, role) 


class FileSystemBrowserTreeView(QtWidgets.QTreeView):
    
    rescanRequested = QtCore.pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.setAlternatingRowColors(True)
        self.setTextElideMode(Qt.ElideMiddle)
        self.setHeaderHidden(True)   
        self.setEnabled(False)        
        
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragOnly)
        
        self.rescanDirectoryAction = QtWidgets.QAction(self.tr("rescan"), self)
        self.addAction(self.rescanDirectoryAction)
        self.rescanDirectoryAction.triggered.connect(self._handleRescan)
        self.deleteFileAction = QtWidgets.QAction(self.tr('delete'), self)
        self.addAction(self.deleteFileAction)
        self.deleteFileAction.triggered.connect(self._handleDelete)
        application.dispatcher.connect(self._handleDispatcher)
        self.setRootIndex(QtCore.QModelIndex())
    
    def getSource(self):
        return self.model().source if self.model() is not None else None
    
    def setSource(self, source):
        oldSource = self.model().source if self.model() is not None else None 
        if source != oldSource:
            if source is not None:
                if self.model() is None:
                    self.setModel(FileSystemBrowserModel())
                self.model().setSource(source)
                self.setRootIndex(self.model().index(source.path))
                self.setEnabled(True)
            else:
                self.setModel(None)
                self.setEnabled(False)
            
    def _handleDispatcher(self, event):
        if isinstance(event, filesystem.SourceChangeEvent) and event.source == self.getSource():
            if event.action == application.ChangeType.deleted:
                self.setSource(None)
            else: self.setRootIndex(self.model().index(event.source.path))
    
    def contextMenuEvent(self, event):
        index = self.indexAt(event.pos())
        menu = QtWidgets.QMenu(self)
        if self.model().isDir(index):
            menu.addAction(self.rescanDirectoryAction)
        else:
            menu.addAction(self.deleteFileAction)
        menu.popup(event.globalPos())
        event.accept()
            
    def _handleRescan(self):
        path = self.model().filePath(self.currentIndex())
        self.rescanRequested.emit(path)

    def _handleDelete(self):
        path = self.model().filePath(self.currentIndex())
        url = urls.URL.fileURL(path)
        elem = levels.real.collect(url)
        levels.real.deleteElements([elem], fromDisk=True)

    def selectionChanged(self, selected, deselected):
        super().selectionChanged(selected, deselected)
        paths = [self.model().filePath(index)
                 for index in self.selectedIndexes()
                 if not self.model().isDir(index)] # TODO: remove this restriction
        s = FileSystemSelection([urls.URL.fileURL(path) for path in paths])
        if s.hasFiles():
            selection.setGlobalSelection(s) 
    
        
class FileSystemBrowser(widgets.Widget):
    """A DockWidget wrapper for the FileSystemBrowser."""
    def __init__(self, state=None, **args):
        super().__init__(**args)
        self.hasOptionDialog = True
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        application.dispatcher.connect(self._handleDispatcher)
        self.sourceChooser = guiwidgets.SourceBox()
        self.sourceChooser.sourceChanged.connect(self._handleSourceChanged)
        layout.addWidget(self.sourceChooser)
        
        self.treeView = FileSystemBrowserTreeView()
        layout.addWidget(self.treeView, 1)
        
    def initialize(self, state):
        super().initialize(state)
        source = None
        if state is not None and 'source' in state:
            source = filesystem.sourceByName(state['source'])
        if source is None and len(filesystem._sources) > 0:
            source = filesystem._sources[0]
        self._handleSourceChanged(source) # initialize
        
    def saveState(self):
        source = self.treeView.getSource()
        if source is not None:
            return {'source': source.name}
        else: return None
    
    def createOptionDialog(self, button=None):
        from . import preferences
        preferences.show("main/filesystem")
    
    def _handleSourceChanged(self, source):
        self.treeView.setSource(source)
        self._updateTitle()
            
    def _handleDispatcher(self, event):
        if isinstance(event, filesystem.SourceChangeEvent) and event.source == self.treeView.getSource():
            self._updateTitle()
            
    def _updateTitle(self):
        source = self.treeView.getSource()
        title = source.name if source is not None else self.tr("No source")
        self.setWindowTitle(self.tr("Filesystem: {}").format(title))
        

class FileSystemSelection(selection.Selection):
    
    def __init__(self, urls):
        super().__init__(levels.real,[])
        self._files = levels.real.collect(urls)
        
    def elements(self,recursive=False):
        return self._files
    
    def files(self,recursive=False):
        return self._files
        
    def hasFiles(self):
        return len(self._files) > 0
    
    def hasElements(self):
        return len(self._files) > 0
        
        
# register this widget in the main application
widgets.addClass(
    id = "filesystembrowser",
    name = translate("FileSystemBrowser", "File System Browser"),
    icon = utils.images.icon('widgets/filesystembrowser.png'),
    theClass = FileSystemBrowser,
    areas = 'dock',
    preferredDockArea = 'right'
)
