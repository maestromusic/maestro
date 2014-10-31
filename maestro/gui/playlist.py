# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import treeview, mainwindow, treeactions, delegates
from . import dockwidget
from ..core import levels, nodes
from .delegates import playlist as playlistdelegate
from .preferences import profiles as profilesgui
from .treeactions import *
from .. import player
from ..models import rootedtreemodel

translate = QtCore.QCoreApplication.translate

# the default playlist used for user commands that do not specify a particular playlist
defaultPlaylist = None


def appendToDefaultPlaylist(wrappers, replace=False):
    """Append the given wrappers to the default playlist. Just do nothing if there is no default playlist.
    If *replace* is true, clear the playlist. If the playlist is currently stopped, start it with the new
    wrappers.
    """
    if defaultPlaylist is None:
        return
    model = defaultPlaylist.model()
    if model.backend.connectionState != player.CONNECTED:
        return
    if replace:
        model.stack.beginMacro(translate("PlaylistWidget", "Replace Playlist"))
        model.clear()
    insertOffset = model.root.fileCount()
    model.insert(model.root, len(model.root.contents), wrappers)
    if replace:
        model.backend.play()            
        model.stack.endMacro()
    elif model.backend.state() is player.STOP:
        model.backend.setCurrent(insertOffset)
        model.backend.play()


class PlaylistTreeView(treeview.DraggingTreeView):
    """This is the main widget of a playlist: The tree view showing the current element tree."""
    level = None
    
    actionConfig = treeview.TreeActionConfiguration()
    sect = translate("PlaylistTreeView", "Tags")
    actionConfig.addActionDefinition(((sect, 'edittags'),), treeactions.EditTagsAction)
    sect = translate("PlaylistTreeView", "Playlist")
    actionConfig.addActionDefinition(((sect, 'removeFromPL'),), treeactions.RemoveFromPlaylistAction)
    actionConfig.addActionDefinition(((sect, 'clearPL'),), treeactions.ClearPlaylistAction)
    
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
                self.removeLocalAction(action)
        self.backend = backend
        if backend is not None:
            global defaultPlaylist
            defaultPlaylist = self
            model = backend.playlist
            self.setRootIsDecorated(True)
            for action in backend.treeActions():
                self.addLocalAction(action)
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



class PlaylistWidget(mainwindow.Widget):
    def __init__(self, state=None, **args):
        super().__init__(**args)
        self.hasOptionDialog = True
        
        # Read state
        profileType = playlistdelegate.PlaylistDelegate.profileType
        if state is None:
            if len(player.profileCategory.profiles()) > 0:
                backend = player.profileCategory.profiles()[0]
            else: backend=None
            delegateProfile = profileType.default()
        else:
            backend = player.profileCategory.getFromStorage(state['backend'])
            delegateProfile = delegates.profiles.category.getFromStorage(state.get('delegate'), profileType)
        
        self.treeview = PlaylistTreeView(delegateProfile)
         
        layout = QtGui.QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        
        layout.addWidget(self.treeview)
        self.errorLabel = QtGui.QLabel()
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
        if state is player.CONNECTED:
            self.mainLayout.insertWidget(self.mainWidgetIndex, self.treeview)
            self.treeview.show()
        else:
            self.errorLabel.setText(self.tr('Connection failed. <a href="#connect">Retry?</a>'))
            self.mainLayout.insertWidget(self.mainWidgetIndex, self.errorLabel)
            self.errorLabel.show()
    
    def createOptionDialog(self, parent):
        return OptionDialog(parent, self)
        
        
mainwindow.addWidgetClass(mainwindow.WidgetClass(
        id = "playlist",
        name = translate("Playlist", "Playlist"),
        icon = utils.getIcon('widgets/playlist.png'),
        theClass = PlaylistWidget))


class OptionDialog(dialogs.FancyPopup):
    """Dialog for the option button in the playlist's (dock widget) title bar.""" 
    def __init__(self, parent, playlist):
        super().__init__(parent)
        layout = QtGui.QFormLayout(self)
        backendChooser = profilesgui.ProfileComboBox(player.profileCategory, default=playlist.backend)
        backendChooser.profileChosen.connect(playlist.setBackend)
        layout.addRow(self.tr("Backend:"), backendChooser)
        profileChooser = profilesgui.ProfileComboBox(
                                         delegates.profiles.category,
                                         restrictToType=playlistdelegate.PlaylistDelegate.profileType,
                                         default=playlist.treeview.itemDelegate().profile)
        profileChooser.profileChosen.connect(playlist.treeview.itemDelegate().setProfile)
        layout.addRow(self.tr("Item view:"), profileChooser)