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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import treeview, mainwindow, playerwidgets
from .delegates import playlist as playlistdelegate, configuration as delegateconfig
from .treeactions import *
from .. import player

translate = QtCore.QCoreApplication.translate


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

    songSelected = QtCore.pyqtSignal(int)
    
    def __init__(self, parent = None):
        super().__init__(parent)
        self.backend = None
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.viewport().setMouseTracking(True)
        self.doubleClicked.connect(self._handleDoubleClick)
        self.setItemDelegate(playlistdelegate.PlaylistDelegate(self))

    def setBackend(self, backend):
        if self.backend is not None:
            self.songSelected.disconnect(self.backend.setCurrentSong)
        self.backend = backend
        self.setDisabled(backend is None)
        if backend is not None:
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

#    #TODO: are the next three methods all necessary?
#    def dragEnterEvent(self, event):
#        if event.source() is self:
#            if event.keyboardModifiers() & Qt.ControlModifier:
#                event.setDropAction(Qt.CopyAction)
#            else: event.setDropAction(Qt.MoveAction)
#        treeview.TreeView.dragEnterEvent(self, event)
#        
#    def dragMoveEvent(self, event):
#        if event.source() is self:
#            if event.keyboardModifiers() & Qt.ControlModifier:
#                event.setDropAction(Qt.CopyAction)
#            else: event.setDropAction(Qt.MoveAction)
#        treeview.TreeView.dragMoveEvent(self, event)
#        
        
    def dropEvent(self,event):
        #if event.source() is self:
        #    if event.keyboardModifiers() & Qt.ControlModifier:
        #        event.setDropAction(Qt.CopyAction)
         #   else: event.setDropAction(Qt.MoveAction)
        self.model()._internalMove = event.source() == self and event.dropAction() == Qt.MoveAction
        super().dropEvent(event)
        self.model()._internalMove = None
        
    def removeSelected(self):
        self.model().removeMany(self.selectedRanges())


class PlaylistWidget(QtGui.QDockWidget):
    def __init__(self, parent = None, state = None, location = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('Playlist'))
        
        self.backend = None
        self.treeview = PlaylistTreeView()
 
        widget = QtGui.QWidget()
        layout = QtGui.QVBoxLayout(widget)
        layout.addWidget(self.treeview)   
        
        # TODO Move stuff into a popup.    
        bottomLayout = QtGui.QHBoxLayout()
        layout.addLayout(bottomLayout)
        self.backendChooser = playerwidgets.BackendChooser(self)
        self.backendChooser.backendChanged.connect(self.setBackend)
        
        bottomLayout.addWidget(self.backendChooser)
        
        bottomLayout.addWidget(QtGui.QLabel(self.tr("Item Display:")))
        bottomLayout.addWidget(delegateconfig.ConfigurationCombo(
                                                    playlistdelegate.PlaylistDelegate.configurationType,
                                                    [self.treeview]))
        bottomLayout.addStretch()
        
        self.setWidget(widget)
        if not self.backendChooser.setCurrentProfile(state):
            self.setBackend(self.backendChooser.currentProfile())
    
    def saveState(self):
        return self.backendChooser.currentProfile()
    
    def setBackend(self, name):
        if self.backend is not None:
            self.backend.unregisterFrontend(self)
        backend = player.instance(name)
        backend.registerFrontend(self)
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
