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
from .. import player, profiles

translate = QtCore.QCoreApplication.translate


class PlaylistTreeView(treeview.TreeView):
    """This is the main widget of a playlist: The tree view showing the current element tree."""
    level = None
    
    actionConfig = treeview.TreeActionConfiguration()
    sect = translate(__name__, "tags")
    actionConfig.addActionDefinition(((sect, 'edittagsS'),), EditTagsAction, recursive=False)
    actionConfig.addActionDefinition(((sect, 'edittagsR'),), EditTagsAction, recursive=True)
    
    sect = translate(__name__, "playlist")
    actionConfig.addActionDefinition(((sect, 'removeFromPL'),), RemoveFromPlaylistAction)
    actionConfig.addActionDefinition(((sect, 'clearPL'),), ClearPlaylistAction)
    
    def __init__(self, parent = None):
        super().__init__(levels.real,parent)
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
            self.model().modelReset.disconnect(self.expandAll)
        self.backend = backend
        self.setDisabled(backend is None)
        if backend is not None:
            model = backend.playlist
            self.setModel(model)
            self.itemDelegate().model = model
            self.updateNodeSelection()
            self.model().modelReset.connect(self.expandAll)
        
    def _handleDoubleClick(self, idx):
        if idx.isValid():
            offset = idx.internalPointer().offset()
            self.backend.setCurrent(offset)
        
    def dropEvent(self,event):
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
        self.setWidget(widget)
        
        layout = QtGui.QVBoxLayout(widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        
        # TODO Move stuff into a popup.    
        buttonLayout = QtGui.QHBoxLayout()
        # Spacings and margins are inherited. Reset the spacing
        style = QtGui.QApplication.style()
        buttonLayout.setSpacing(style.pixelMetric(style.PM_LayoutHorizontalSpacing))
        layout.addLayout(buttonLayout)
        self.backendChooser = profiles.ProfileComboBox(player.profileConf, default = state)
        self.backendChooser.profileChosen.connect(self.setBackend)
        buttonLayout.addWidget(self.backendChooser)
        
        buttonLayout.addWidget(QtGui.QLabel(self.tr("Item Display:")))
        buttonLayout.addWidget(delegateconfig.ConfigurationCombo(
                                                    playlistdelegate.PlaylistDelegate.configurationType,
                                                    [self.treeview]))
        buttonLayout.addStretch()
        
        layout.addWidget(self.treeview)  
        
        self.setBackend(self.backendChooser.currentProfileName())
    
    def saveState(self):
        return self.backendChooser.currentProfileName()
    
    def setBackend(self, name):
        if self.backend is not None:
            self.backend.unregisterFrontend(self)
        if name is not None:
            backend = player.profileConf[name]
            backend.registerFrontend(self)
        else:
            backend = None
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
