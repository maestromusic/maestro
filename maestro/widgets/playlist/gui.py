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

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from maestro import player, widgets, profiles
from maestro.core import levels, nodes
from maestro.models import rootedtreemodel
from maestro.gui import actions, dialogs, treeview, delegates
from maestro.gui.delegates import playlist as playlistdelegate
from maestro.gui.preferences import profiles as profilesgui
from maestro.widgets import WidgetClass

translate = QtCore.QCoreApplication.translate


def appendToDefaultPlaylist(wrappers, replace=False):
    """Append the given wrappers to the default playlist. Just do nothing if there is no default playlist.
    If *replace* is true, clear the playlist. If the playlist is currently stopped, start it with the new
    wrappers.
    """
    currentPlaylist = WidgetClass.currentWidget('playlist')
    if currentPlaylist is None:
        return
    model = currentPlaylist.treeview.model()
    if model.backend.connectionState != player.ConnectionState.Connected:
        return
    if replace:
        model.stack.beginMacro(translate("PlaylistWidget", "Replace Playlist"))
        model.clear()
    insertOffset = model.root.fileCount()
    model.insert(model.root, len(model.root.contents), wrappers)
    if replace:
        model.backend.play()            
        model.stack.endMacro()
    elif model.backend.state() is player.PlayState.Stop:
        model.backend.setCurrent(insertOffset)
        model.backend.play()


class RemoveFromPlaylistAction(actions.TreeAction):
    """This action removes selected elements from a playlist."""

    label = translate('RemoveFromPlaylistAction', 'Remove from playlist')

    def initialize(self, selection):
        self.setDisabled(selection.empty())

    def doAction(self):
        self.parent().removeSelected()


class ClearPlaylistAction(actions.TreeAction):
    """This action clears a playlist."""

    label = translate('ClearPlaylistAction', 'Clear playlist')

    def initialize(self, selection):
        self.setEnabled(self.parent().model().root.hasContents())

    def doAction(self):
        self.parent().model().clear()


class PlaylistTreeView(treeview.DraggingTreeView):
    """This is the main widget of a playlist: The tree view showing the current element tree."""
    level = None

    def __init__(self, delegateProfile):
        super().__init__(levels.real)
        self.backend = None
        self.doubleClicked.connect(self._handleDoubleClick)
        self.setItemDelegate(playlistdelegate.PlaylistDelegate(self,delegateProfile))
        self.emptyModel = rootedtreemodel.RootedTreeModel()
        self.emptyModel.root.setContents([nodes.TextNode(
                                        self.tr("Please configure and choose a backend to play music."),
                                        wordWrap=True)])
        
# EXPERIMENTAL: These lines can be used to set a background image 
#        self.setStyleSheet("""
#                QTreeView {
#                background-color: #EBEBEB;
#                background-image: url('');
#                background-position: bottom right; 
#                background-repeat: no-repeat;} 
#            """)
#        
#    def drawRow(self, painter, option, index):
#        option.palette.setColor(QtGui.QPalette.Background, QtGui.QColor(255, 255, 255, 100))
#        option.palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(230, 230, 230, 100))
#        super().drawRow(painter, option, index)
        
    @property
    def stack(self):
        return self.model().stack
    
    def setBackend(self, backend):
        if self.backend is not None:
            self.model().modelReset.disconnect(self.expandAll)
            for action in self.backend.treeActions():
                self.removeAction(action)
        self.backend = backend
        if backend is not None:
            model = backend.playlist
            self.setRootIsDecorated(True)
            for action in backend.treeActions():
                self.addAction(action)
        else:
            model = self.emptyModel
            self.setRootIsDecorated(False)
        self.setModel(model)
        self.updateSelection()
        self.model().modelReset.connect(self.expandAll) 

    def _handleDoubleClick(self, idx):
        if idx.isValid():
            offset = idx.internalPointer().offset()
            self.backend.setCurrent(offset)
        
    def removeSelected(self):
        self.model().removeMany(self.selectedRanges())


class PlaylistWidget(widgets.Widget):

    hasOptionDialog = True

    def __init__(self, state=None, **args):
        super().__init__(**args)
        # Read state
        profileType = playlistdelegate.PlaylistDelegate.profileType
        playerProfileCategory = profiles.category('playback')
        if state is None:
            if len(playerProfileCategory.profiles()) > 0:
                backend = playerProfileCategory.profiles()[0]
            else:
                backend = None
            delegateProfile = profileType.default()
        else:
            backend = playerProfileCategory.getFromStorage(state['backend'])
            delegateProfile = delegates.profiles.category.getFromStorage(state.get('delegate'),
                                                                         profileType)
        
        self.treeview = PlaylistTreeView(delegateProfile)
         
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(self.treeview)
        self.errorLabel = QtWidgets.QLabel()
        self.errorLabel.setAlignment(Qt.AlignVCenter | Qt.AlignHCenter)
        self.errorLabel.linkActivated.connect(lambda: self.backend.connectBackend())
        self.mainLayout = layout
        self.mainWidgetIndex = layout.indexOf(self.treeview)
        
        self.backend = None
        self.setBackend(backend)
    
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
            self.errorLabel.setText(self.tr("No backend selected"))

        self.backend = backend
        self.treeview.setBackend(self.backend)

    def setActiveWidgetByState(self, state):
        current = self.mainLayout.itemAt(self.mainWidgetIndex).widget()
        self.mainLayout.removeWidget(current)
        current.hide()
        if state is player.ConnectionState.Connected:
            self.mainLayout.insertWidget(self.mainWidgetIndex, self.treeview)
            self.treeview.show()
        else:
            self.errorLabel.setText(self.tr('Connection failed. <a href="#connect">Retry?</a>'))
            self.mainLayout.insertWidget(self.mainWidgetIndex, self.errorLabel)
            self.errorLabel.show()
    
    def createOptionDialog(self, button=None):
        return OptionDialog(button, self)


class OptionDialog(dialogs.FancyPopup):
    """Dialog for the option button in the playlist's (dock widget) title bar.""" 
    def __init__(self, parent, playlist):
        super().__init__(parent)
        layout = QtWidgets.QFormLayout(self)
        backendChooser = profilesgui.ProfileComboBox(profiles.category('playback'),
                                                     default=playlist.backend)
        backendChooser.profileChosen.connect(playlist.setBackend)
        layout.addRow(self.tr("Backend:"), backendChooser)
        profileChooser = profilesgui.ProfileComboBox(
            delegates.profiles.category,
            restrictToType=playlistdelegate.PlaylistDelegate.profileType,
            default=playlist.treeview.itemDelegate().profile
        )
        profileChooser.profileChosen.connect(playlist.treeview.itemDelegate().setProfile)
        layout.addRow(self.tr("Item view:"), profileChooser)
