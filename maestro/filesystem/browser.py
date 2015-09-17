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
import os.path

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt

from maestro.core import urls
from maestro import application, filesystem, utils, widgets
from maestro.gui import selection, widgets as guiwidgets
from maestro.core import levels
from maestro.filesystem.sources import FilesystemState

translate = QtCore.QCoreApplication.translate

"""This module contains a dock widget that displays the music in directory view, i.e. without
considering the container structure in the database. It is meant to help building up the database.
Folders which contain music files that are not yet present in the database are marked with a
special icon."""


class FilesystemFilterModel(QtCore.QSortFilterProxyModel):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.filterText = ''
        self.showSynced = True
        self.showUnsynced = True

    def filterAcceptsRow(self, row, parent):
        sIndex = self.sourceModel().index(row, 0, parent)
        info = self.sourceModel().fileInfo(sIndex)
        path = info.filePath()
        source = self.sourceModel().source
        filterText = self.filterText.lower()
        if not source.contains(path):
            return True  # avoid filtering parents of the source's root!
        relPath = os.path.relpath(path, source.path).lower()
        if relPath == '.':
            return True
        if '/' not in relPath and filterText not in relPath:
            return False
        status = source.folderState(path) if info.isDir() else source.fileState(path)
        if not self.showSynced and status is FilesystemState.synced:
            return False
        if not self.showUnsynced and status is FilesystemState.unsynced:
            return False
        return True

    def setFilterText(self, text):
        self.filterText = text
        self.invalidateFilter()

    def setShowSynced(self, state):
        self.showSynced = state
        self.invalidateFilter()

    def setShowUnsynced(self, state):
        self.showUnsynced = state
        self.invalidateFilter()


class FilesystemBrowserModel(QtWidgets.QFileSystemModel):
    """Model class for the file system browser.
    
    In contrast to QFileSystemModel, this returns folder and file icons depending on the state
    ("nomusic", "unsynced", etc.) and according tooltips.
    """

    descriptions = {
        FilesystemState.unsynced: translate('FilesystemBrowserModel',
                                            'contains files that are not in Maestro\'s database'),
        FilesystemState.synced  : translate('FilesystemBrowserModel',
                                            'in sync with Maestro\'s database'),
        FilesystemState.empty   : translate('FilesystemBrowserModel',
                                            'empty directory'),
        FilesystemState.unknown : translate('FilesystemBrowserModel', 'unknown status')}
    
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
            
    def columnCount(self, parent=None):
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
                    return status.folderIcon()
                else:
                    return dirpath + '\n' + self.descriptions[status]
            else:
                status = self.source.fileState(info.absoluteFilePath())
                if role == Qt.DecorationRole:
                    return status.fileIcon()
                else:
                    return str(info.absoluteFilePath()) + '\n' + self.descriptions[status]
        return super().data(index, role) 


class FilesystemBrowserTreeView(QtWidgets.QTreeView):
    
    rescanRequested = QtCore.pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.setAlternatingRowColors(True)
        self.setTextElideMode(Qt.ElideMiddle)
        self.setHeaderHidden(True)   
        self.setEnabled(False)
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragOnly)
        application.dispatcher.connect(self._handleDispatcher)
        self.setModel(FilesystemFilterModel())
        self.fsModel = FilesystemBrowserModel()
    
    def setSource(self, source):
        oldSource = self.fsModel.source
        if source is not oldSource:
            if source:
                self.model().setSourceModel(self.fsModel)
                self.fsModel.setSource(source)
                self.setRootIndex(self.model().mapFromSource(self.fsModel.index(source.path)))
                self.setEnabled(True)
            else:
                self.fsModel.setSourceModel(None)
                self.setEnabled(False)
            
    def _handleDispatcher(self, event):
        if isinstance(event, filesystem.SourceChangeEvent) and event.source is self.fsModel.source:
            if event.action == application.ChangeType.deleted:
                self.setSource(None)
            else:
                self.setSource(event.source)
    
    def selectionChanged(self, selected, deselected):
        super().selectionChanged(selected, deselected)
        paths = [self.fsModel.filePath(self.model().mapToSource(index))
                 for index in self.selectedIndexes()
                 if not self.fsModel.isDir(self.model().mapToSource(index))]
        s = FileSystemSelection([urls.URL.fileURL(path) for path in paths])
        if s.hasFiles():
            selection.setGlobalSelection(s) 
    
        
class FilesystemBrowser(widgets.Widget):
    """A DockWidget wrapper for the FilesystemBrowser."""

    hasOptionDialog = True

    def __init__(self, state=None, **args):
        super().__init__(**args)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        application.dispatcher.connect(self._handleDispatcher)
        self.sourceChooser = guiwidgets.SourceBox()
        self.sourceChooser.sourceChanged.connect(self._handleSourceChanged)

        toolLayout = QtWidgets.QHBoxLayout()
        self.treeview = FilesystemBrowserTreeView()
        self.filterEdit = QtWidgets.QLineEdit()
        self.filterEdit.setPlaceholderText(self.tr('filter first-level'))
        self.filterEdit.textChanged.connect(self.treeview.model().setFilterText)
        self.filterEdit.setClearButtonEnabled(True)
        syncButton = QtWidgets.QToolButton()
        syncButton.setIcon(utils.images.icon('synchronized'))
        syncButton.setIconSize(QtCore.QSize(16, 16))
        syncButton.setToolTip(self.tr('Show synchronized files and folders'))
        syncButton.setCheckable(True)
        syncButton.setChecked(True)
        syncButton.toggled.connect(self.treeview.model().setShowSynced)
        unsyncButton = QtWidgets.QToolButton()
        unsyncButton.setIconSize(QtCore.QSize(16, 16))
        unsyncButton.setIcon(utils.images.icon('unsynchronized'))
        unsyncButton.setToolTip(self.tr('Show unsynchronized fils and folders'))
        unsyncButton.setCheckable(True)
        unsyncButton.setChecked(True)
        unsyncButton.toggled.connect(self.treeview.model().setShowUnsynced)

        toolLayout.addWidget(self.sourceChooser)
        toolLayout.addWidget(self.filterEdit)
        toolLayout.addWidget(syncButton)
        toolLayout.addWidget(unsyncButton)
        layout.addLayout(toolLayout)
        layout.addWidget(self.treeview)
        
    def initialize(self, state=None):
        super().initialize(state)
        source = None
        if state and 'source' in state:
            source = filesystem.sourceByName(state['source'])
        if not source and len(filesystem.allSources) > 0:
            source = filesystem.allSources[0]
        self._handleSourceChanged(source)
        
    def saveState(self):
        source = self.treeview.fsModel.source
        if source:
            return dict(source=source.name)
    
    def createOptionDialog(self, button=None):
        from maestro.gui import preferences
        preferences.show("main/filesystem")
    
    def _handleSourceChanged(self, source):
        self.treeview.setSource(source)
        self._updateTitle()
            
    def _handleDispatcher(self, event):
        if isinstance(event, filesystem.SourceChangeEvent) and event.source == self.treeview.fsModel.source:
            self._updateTitle()
            
    def _updateTitle(self):
        source = self.treeview.fsModel.source
        title = source.name if source is not None else self.tr("No source")
        self.setWindowTitle(self.tr("Filesystem: {}").format(title))
        

class FileSystemSelection(selection.Selection):
    
    def __init__(self, selectedUrls):
        super().__init__(levels.real, [])
        self._files = levels.real.collect(selectedUrls)
        
    def elements(self, recursive=False):
        return self._files
    
    def files(self, recursive=False):
        return self._files
        
    def hasFiles(self):
        return len(self._files) > 0
    
    def hasElements(self):
        return len(self._files) > 0
