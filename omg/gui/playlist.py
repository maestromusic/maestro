# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import treeview, mainwindow, delegates, playerwidgets
from .. import logging, player, utils

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger("gui.playlist")

class PlaylistTreeView(treeview.TreeView):
    """This is the main widget of a playlist: The tree view showing the current element tree."""
    level = None
    
    songSelected = QtCore.pyqtSignal(int)
    
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.viewport().setMouseTracking(True)
        self.doubleClicked.connect(self._handleDoubleClick)

    def setBackend(self, backend):
        self.backend = backend
        model = backend.playlist
        if self.selectionModel():
            self.selectionModel().selectionChanged.disconnect(self.updateGlobalSelection)
        self.setModel(model)
        self.setItemDelegate(PlaylistDelegate(self))
        self.selectionModel().selectionChanged.connect(self.updateGlobalSelection)
        self.songSelected.connect(backend.setCurrentSong)
        
    def _handleDoubleClick(self, idx):
        if idx.isValid():
            offset = idx.internalPointer().offset()
            self.songSelected.emit(offset)
        

class PlaylistDelegate(delegates.BrowserDelegate):
    """Delegate for the playlist."""
    options = delegates.BrowserDelegate.options
    
    def __init__(self,view):
        super().__init__(view,delegates.defaultBrowserDelegateConfig)
        
    def background(self, index):
        if index == self.model.currentModelIndex:
            return QtGui.QBrush(QtGui.QColor(110,149,229))
        elif index in self.model.currentParentsModelIndices:
            return QtGui.QBrush(QtGui.QColor(140,179,255))


class PlaylistWidget(QtGui.QDockWidget):
    
    def __init__(self, parent = None, state = None, location = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('playlist'))
        self.treeview = PlaylistTreeView()
 
        widget = QtGui.QWidget()
        layout = QtGui.QVBoxLayout(widget)
        layout.addWidget(self.treeview)       
        bottomLayout = QtGui.QHBoxLayout()
        self.backendChooser = playerwidgets.BackendChooser(self)
        self.backendChooser.backendChanged.connect(self.setBackend)
        bottomLayout.addWidget(self.backendChooser)
        self.clearButton = QtGui.QPushButton(self.tr('clear'), self)
        self.shuffleButton = QtGui.QPushButton(self.tr('shuffle'), self)
        self.removeButton = QtGui.QPushButton(self.tr('remove'), self)
        self.removeButton.clicked.connect(self.removeSelected)
        bottomLayout.addWidget(self.clearButton)
        bottomLayout.addWidget(self.shuffleButton)
        bottomLayout.addWidget(self.removeButton)
        bottomLayout.addStretch()
        self.undoButton = QtGui.QToolButton(self)
        self.redoButton = QtGui.QToolButton(self)
        bottomLayout.addWidget(self.undoButton)
        bottomLayout.addWidget(self.redoButton) 
        
        layout.addLayout(bottomLayout)
        self.setWidget(widget)
        if not self.backendChooser.setCurrentProfile(state):
            self.setBackend(self.backendChooser.currentProfile())
    
    def removeSelected(self):
        elements = set(ix.internalPointer() for ix in self.treeview.selectedIndexes())
        redundant = set()
        for element in elements:
            for parent in element.getParents():
                if parent in elements:
                    redundant.add(element)
        elements -= redundant
        removals = []
        for element in elements:
            for file in element.getAllFiles():
                #TODO: super inefficient to calculate all the offsets...we need a better way
                # to do this anyway!
                removals.append((file.offset(), file.path))
        removals.sort()
        self.backend.removeFromPlaylist(removals)
                
    def saveState(self):
        return self.backendChooser.currentProfile()
    
    def setBackend(self, name):
        logger.debug("playlist gui sets backend: {}".format(name))
        if hasattr(self, 'backend'):
            self.backend.unregisterFrontend(self)
            self.treeview.songSelected.disconnect(self.backend.setCurrentSong)
            self.clearButton.clicked.disconnect(self.backend.clearPlaylist)
        if name is None:
            self.treeview.setDisabled(True)
            return
        backend = player.instance(name)
        if backend is None:
            self.treeview.setDisabled(True)
            return
        backend.registerFrontend(self)
        
        self.treeview.setEnabled(True)
        self.backend = backend
        self.undoButton.setDefaultAction(self.backend.stack.createUndoAction(self))
        self.redoButton.setDefaultAction(self.backend.stack.createRedoAction(self))
        self.clearButton.clicked.connect(self.backend.clearPlaylist)
        self.treeview.setBackend(self.backend)
        
        
data = mainwindow.WidgetData(id = "playlist",
                             name = translate("Playlist","playlist"),
                             theClass = PlaylistWidget,
                             central = True,
                             dock = True,
                             default = True,
                             unique = False,
                             preferredDockArea = Qt.RightDockWidgetArea)
mainwindow.addWidgetData(data)