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

from . import treeview, mainwindow, treeactions, playerwidgets, profiles as profilesgui, delegates
from ..core import levels
from .delegates import playlist as playlistdelegate
from .treeactions import *
from .. import player

translate = QtCore.QCoreApplication.translate


class PlaylistTreeView(treeview.TreeView):
    """This is the main widget of a playlist: The tree view showing the current element tree."""
    level = None
    
    actionConfig = treeview.TreeActionConfiguration()
    sect = translate(__name__, "tags")
    actionConfig.addActionDefinition(((sect, 'edittagsS'),), treeactions.EditTagsAction, recursive=False)
    actionConfig.addActionDefinition(((sect, 'edittagsR'),), treeactions.EditTagsAction, recursive=True)
    
    sect = translate(__name__, "playlist")
    actionConfig.addActionDefinition(((sect, 'removeFromPL'),), treeactions.RemoveFromPlaylistAction)
    actionConfig.addActionDefinition(((sect, 'clearPL'),), treeactions.ClearPlaylistAction)
    
    def __init__(self, delegateProfile):
        super().__init__(levels.real)
        self.backend = None
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.viewport().setMouseTracking(True)
        self.doubleClicked.connect(self._handleDoubleClick)
        self.setItemDelegate(playlistdelegate.PlaylistDelegate(self,delegateProfile))

    def setBackend(self, backend):
        if self.backend is not None:
            self.model().modelReset.disconnect(self.expandAll)
        self.backend = backend
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
    def __init__(self, parent=None, state=None, location=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('Playlist'))
        
        # Read state
        if 'backend' in state:
            backend = player.profileCategory.get(state['backend']) # may be None
        else: backend = None
        profileType = playlistdelegate.PlaylistDelegate.profileType
        delegateProfile = None
        if 'delegate' in state:
            delegateProfile = delegates.profiles.category.get(state['delegate'])
        if delegateProfile is None or delegateProfile.type != profileType:
            delegateProfile = profileType.default()
        
        self.backend = None
        self.treeview = PlaylistTreeView(delegateProfile)
 
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
        self.backendChooser = profilesgui.ProfileComboBox(player.profileCategory, default=backend)
        self.backendChooser.profileChosen.connect(self.setBackend)
        buttonLayout.addWidget(self.backendChooser)
        
        buttonLayout.addWidget(QtGui.QLabel(self.tr("Item Display:")))
        profileChooser = profilesgui.ProfileComboBox(delegates.profiles.category,
                                                     restrictToType=profileType,
                                                     default=delegateProfile)
        profileChooser.profileChosen.connect(self.treeview.itemDelegate().setProfile)
        buttonLayout.addWidget(profileChooser)
        buttonLayout.addStretch()

        layout.addWidget(self.treeview)
        self.errorLabel = QtGui.QLabel()
        self.errorLabel.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.mainLayout = layout
        self.mainWidgetIndex = layout.indexOf(self.treeview)
        self.setBackend(self.backendChooser.currentProfile())
    
    def saveState(self):
        return {'backend': self.backend.name if self.backend is not None else None,
                'delegate': self.treeview.itemDelegate().profile.name
                }
    
    def setBackend(self, backend):
        if self.backend is not None:
            self.backend.unregisterFrontend(self)
            self.backend.connectionStateChanged.disconnect(self.setActiveWidgetByState)
            
        if backend is not None:
            backend.registerFrontend(self)
            self.setActiveWidgetByState(backend.connectionState)
            backend.connectionStateChanged.connect(self.setActiveWidgetByState)
        else:
            self.errorLabel.setText(self.tr("no backend selected"))

        self.backend = backend
        self.treeview.setBackend(self.backend)
    
    def setActiveWidgetByState(self, state):
        current = self.mainLayout.itemAt(self.mainWidgetIndex).widget()
        self.mainLayout.removeWidget(current)
        current.hide()
        if state is player.CONNECTED:
            self.mainLayout.insertWidget(self.mainWidgetIndex, self.treeview)
            self.treeview.show()
        else:
            self.mainLayout.insertWidget(self.mainWidgetIndex, self.errorLabel)
            self.errorLabel.show()
        
        
mainwindow.addWidgetData(mainwindow.WidgetData(
                    id="playlist", name=translate("Playlist", "playlist"),
                    theClass=PlaylistWidget,
                    central=True, dock=True, default=True, unique=False,
                    preferredDockArea=Qt.RightDockWidgetArea))
