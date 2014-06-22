# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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
translate = QtCore.QCoreApplication.translate

from .. import application, filebackends, filesystem, config, utils, constants
from . import mainwindow, selection, dockwidget, widgets
from ..core import levels, domains


"""This module contains a dock widget that displays the music in directory view, i.e. without
considering the container structure in the database. It is meant to help building up the database.
Folders which contain music files that are not yet present in the database are marked with a
special icon."""


class FileSystemBrowserModel(QtGui.QFileSystemModel):
    """Model class for the file system browser.
    
    In contrast to QFileSystemModel, this returns folder and file icons depending on the state
    ("nomusic", "unsynced", etc.) and according tooltips.
    """
    
    folderIcons = {
        'unsynced' : utils.getIcon("folder_unsynced.svg"),
        'ok'       : utils.getIcon("folder_ok.svg"),
        'nomusic'  : utils.getIcon("folder.svg"),
        'unknown'  : utils.getIcon("folder_unknown.svg"),
        'problem'  : utils.getIcon("folder_problem.svg") }
    
    fileIcons = {
        'unsynced' : utils.getIcon("file_unsynced.svg"),
        'ok'       : utils.getIcon("file_ok.svg"),
        'unknown'  : utils.getIcon("file_unknown.svg"),
        'problem'  : utils.getIcon("file_problem.svg") }
    
    descriptions = {
        'unsynced' : translate("FileSystemBrowserModel", "contains music which is not in OMG's database"),
        'ok'       : translate("FileSystemBrowserModel", "in sync with OMG's database"),
        'nomusic'  : translate("FileSystemBrowserModel", "does not contain music"),
        'unknown'  : translate("FileSystemBrowserModel", "unknown status"),
        'problem'  : translate("FileSystemBrowserModel", "in conflict with database") }
    
    def __init__(self, parent=None):
        QtGui.QFileSystemModel.__init__(self, parent)
        self.setFilter(QtCore.QDir.AllEntries | QtCore.QDir.NoDotAndDotDot)
        self.source = None
        #filesystem.synchronizer.folderStateChanged.connect(self.handleStateChange)
        #filesystem.synchronizer.fileStateChanged.connect(self.handleStateChange)
        #self.rescanRequested.connect(filesystem.synchronizer.recheck)
        self.setRootPath(None)
        
    def setSource(self, source):
        if source != self.source:
            self.source = source
            self.setRootPath(source.path)
            
    def columnCount(self, index):
        return 1
    
    @QtCore.pyqtSlot(object)
    def handleStateChange(self, url):
        index = self.index(url.path)
        self.dataChanged.emit(index, index)   
    
    def data(self, index, role=Qt.DisplayRole):
        """Overridden for DecorationRole and ToolTipRole."""
        if role == Qt.DecorationRole or role == Qt.ToolTipRole:
            info = self.fileInfo(index)
            if os.path.isdir(info.absoluteFilePath()):
                dir = info.absoluteFilePath()
                if dir == '..':
                    return super().data(index, role)
                status = filesystem.folderState(dir)
                if role == Qt.DecorationRole:
                    return self.folderIcons[status]
                else:
                    return dir + '\n' + self.descriptions[status]
            else:
                url = filebackends.filesystem.FileURL(info.absoluteFilePath())
                status = filesystem.fileState(url)
                if role == Qt.DecorationRole:
                    return self.fileIcons[status]
                else:
                    return str(url) + '\n' + self.descriptions[status]
        return super().data(index, role) 


class FileSystemBrowserTreeView(QtGui.QTreeView):
    
    rescanRequested = QtCore.pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.setAlternatingRowColors(True)
        self.setTextElideMode(Qt.ElideMiddle)
        self.setHeaderHidden(True)   
        self.setEnabled(False)        
        
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragDropMode(QtGui.QAbstractItemView.DragOnly)
        
        self.rescanDirectoryAction = QtGui.QAction(self.tr("rescan"), self)
        self.addAction(self.rescanDirectoryAction)
        self.rescanDirectoryAction.triggered.connect(self._handleRescan)
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
            if event.action == constants.DELETED:
                self.setSource(None)
            else: self.setRootIndex(self.model().index(event.source.path))
    
    def contextMenuEvent(self, event):
        index = self.indexAt(event.pos())
        if self.model().isDir(index):
            menu = QtGui.QMenu(self)
            menu.addAction(self.rescanDirectoryAction)
            menu.popup(event.globalPos())
            event.accept()
        else:
            event.ignore()
            
    def _handleRescan(self):
        path = self.model().filePath(self.currentIndex())
        self.rescanRequested.emit(path)
        
    def selectionChanged(self, selected, deselected):
        super().selectionChanged(selected, deselected)
        paths = [self.model().filePath(index)
                 for index in self.selectedIndexes()
                 if not self.model().isDir(index)] # TODO: remove this restriction
        s = FileSystemSelection([filebackends.filesystem.FileURL(path) for path in paths])
        if s.hasFiles():
            selection.setGlobalSelection(s) 
    
        
class FileSystemBrowser(dockwidget.DockWidget):
    """A DockWidget wrapper for the FileSystemBrowser."""
    def __init__(self, parent=None, state=None, **args):
        super().__init__(parent, **args)
        widget = QtGui.QWidget()
        layout = QtGui.QVBoxLayout(widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        source = None
        if state is not None and 'source' in state:
            source = filesystem.sourceByName(state['source'])
        if source is None and len(filesystem.sources) > 0:
            source = filesystem.sources[0]
        self.sourceChooser = widgets.SourceBox()
        self.sourceChooser.sourceChanged.connect(self._handleSourceChanged)
        layout.addWidget(self.sourceChooser)
        
        self.treeView = FileSystemBrowserTreeView()
        layout.addWidget(self.treeView, 1)
        self.setWidget(widget)
        self._handleSourceChanged(source) # initialize
        
    def saveState(self):
        source = self.treeView.getSource()
        if source is not None:
            return {'source': source.name}
        else: return None
        
    def createOptionDialog(self, parent):
        from . import preferences
        preferences.show("main/filesystem")
    
    def _handleSourceChanged(self, source):
        title = source.name if source is not None else self.tr("No source")
        self.setWindowTitle(self.tr("Filesystem: {}").format(title))
        self.treeView.setSource(source)
        

class FileSystemSelection(selection.Selection):
    
    def __init__(self, urls):
        super().__init__(levels.real,[])
        self._files = levels.real.collectMany(urls)
        
    def elements(self,recursive=False):
        return self._files
    
    def files(self,recursive=False):
        return self._files
        
    def hasFiles(self):
        return len(self._files) > 0
    
    def hasElements(self):
        return len(self._files) > 0
        
        
# register this widget in the main application
widgetData = mainwindow.WidgetData(id = "filesystembrowser",
                                   name = translate("FileSystemBrowser", "File System Browser"),
                                   icon = utils.images.icon('widgets/filesystembrowser.png'),
                                   theClass = FileSystemBrowser,
                                   central = False,
                                   preferredDockArea = QtCore.Qt.RightDockWidgetArea)
mainwindow.addWidgetData(widgetData)
