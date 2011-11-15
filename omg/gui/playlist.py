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
from .. import logging, player, tags, config
from ..models import playlist
from ..constants import PLAYLIST

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger("gui.playlist")

class PlaylistTreeView(treeview.TreeView):
    """This is the main widget of a playlist: The tree view showing the current element tree."""
    level = PLAYLIST
    
    songSelected = QtCore.pyqtSignal(int)
    
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.viewport().setMouseTracking(True)
    
    def setModel(self, model):
        if self.selectionModel():
            self.selectionModel().selectionChanged.disconnect(self.updateGlobalSelection)
        super().setModel(model)
        self.setItemDelegate(PlaylistDelegate(self))
        self.selectionModel().selectionChanged.connect(self.updateGlobalSelection)
        self.doubleClicked.connect(self._handleDoubleClick)
        
    def _handleDoubleClick(self, idx):
        if idx.isValid():
            offset = idx.internalPointer().offset()
            if self.model().currentIndex is None or offset != self.model().currentIndex:
                self.songSelected.emit(offset)
        

class PlaylistDelegate(delegates.BrowserDelegate):
    """Delegate for the playlist."""
    
    def __init__(self,view):
        super().__init__(view)
        
    def background(self, index):
        if index == self.model.getIndex(self.model.current):
            return QtGui.QBrush(QtGui.QColor(110,149,229))
        
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
        self.treeview.setModel(self.backend.playlist)
        self.treeview.songSelected.connect(self.backend.setCurrentSong)
        
data = mainwindow.WidgetData(id = "playlist",
                             name = translate("Playlist","playlist"),
                             theClass = PlaylistWidget,
                             central = True,
                             dock = True,
                             default = True,
                             unique = False,
                             preferredDockArea = Qt.RightDockWidgetArea)
mainwindow.addWidgetData(data)