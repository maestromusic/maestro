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

from . import treeview, mainwindow, playerwidgets
from .delegates import playlist as playlistdelegate, configuration as delegateconfig
from .. import logging, player, utils
from ..modify.treeactions import *
translate = QtCore.QCoreApplication.translate
logger = logging.getLogger("gui.playlist")

class PlaylistTreeView(treeview.TreeView):
    """This is the main widget of a playlist: The tree view showing the current element tree."""
    level = None
    
    actionConfig = treeview.TreeActionConfiguration()
    sect = translate(__name__, "tags")
    actionConfig.addActionDefinition(((sect, 'edittagsS'),), EditTagsAction, recursive = False)
    actionConfig.addActionDefinition(((sect, 'edittagsR'),), EditTagsAction, recursive = True)
    
    sect = translate(__name__, "playlist")
    actionConfig.addActionDefinition(((sect, 'removeFromPL'),), RemoveFromPlaylistAction)
    actionConfig.addActionDefinition(((sect, 'clearPL'),), ClearPlaylistAction)
    actionConfig.addActionDefinition(((sect, 'pl_undo'),), None) # special action
    actionConfig.addActionDefinition(((sect, 'pl_redo'),), None)

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
        self.setItemDelegate(playlistdelegate.PlaylistDelegate(self))

    def setBackend(self, backend):
        self.backend = backend
        if 'pl_undo' in self.treeActions:
            self.removeAction(self.treeActions['pl_undo'])
            self.removeAction(self.treeActions['pl_redo'])
        self.treeActions['pl_undo'] = self.backend.stack.createUndoAction(self, self.tr('Undo(playlist)'))
        self.treeActions['pl_redo'] = self.backend.stack.createRedoAction(self, self.tr('Redo(playlist)'))
        model = backend.playlist
        if self.selectionModel():
            self.selectionModel().selectionChanged.disconnect(self.updateGlobalSelection)
        self.setModel(model)
        self.itemDelegate().model = model
        self.selectionModel().selectionChanged.connect(self.updateGlobalSelection)
        self.songSelected.connect(backend.setCurrentSong)
        self.updateNodeSelection()
        
    
    def _handleDoubleClick(self, idx):
        if idx.isValid():
            offset = idx.internalPointer().offset()
            self.songSelected.emit(offset)

    def dragEnterEvent(self, event):
        if event.source() is self:
            event.setDropAction(Qt.MoveAction)
        else:
            event.setDropAction(Qt.CopyAction)
        treeview.TreeView.dragEnterEvent(self, event)
        
    def dragMoveEvent(self, event):
        if event.source() is self:
            if event.keyboardModifiers() & Qt.ControlModifier:
                event.setDropAction(Qt.CopyAction)
            else:
                event.setDropAction(Qt.MoveAction)
        treeview.TreeView.dragMoveEvent(self, event)
        
    def dropEvent(self, event):
        if event.source() is self:
            if event.keyboardModifiers() & Qt.ShiftModifier:
                event.setDropAction(Qt.MoveAction)
            elif event.keyboardModifiers() & Qt.ControlModifier:
                event.setDropAction(Qt.CopyAction)
            elif event.source() is self:
                event.setDropAction(Qt.MoveAction)
            else:
                event.setDropAction(Qt.CopyAction)
        treeview.TreeView.dropEvent(self, event)
        
    def removeSelected(self):
        elements = set(ix.internalPointer() for ix in self.selectedIndexes())
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
        
        bottomLayout.addWidget(QtGui.QLabel(self.tr("Item Display:")))
        bottomLayout.addWidget(delegateconfig.ConfigurationCombo(
                                                    playlistdelegate.PlaylistDelegate.configurationType,
                                                    [self.treeview]))
        bottomLayout.addStretch()
        
        layout.addLayout(bottomLayout)
        self.setWidget(widget)
        if not self.backendChooser.setCurrentProfile(state):
            self.setBackend(self.backendChooser.currentProfile())
    
    def saveState(self):
        return self.backendChooser.currentProfile()
    
    def setBackend(self, name):
        if hasattr(self, 'backend'):
            self.backend.unregisterFrontend(self)
            self.treeview.songSelected.disconnect(self.backend.setCurrentSong)
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
