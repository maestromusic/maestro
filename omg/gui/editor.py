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

# --------- Qt imports -----------------------
from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
translate = QtCore.QCoreApplication.translate

# --------- OMG imports ----------------------
from ..models import editor, levels, rootedtreemodel
from ..constants import CONTENTS
from . import treeview, mainwindow
from ..modify.treeactions import *
from .delegates import editor as editordelegate, configuration as delegateconfig
from .. import logging, tags, config
logger = logging.getLogger(__name__)

# --------- Python standard lib imports ------
import itertools


_profiles = None

def profiles():
    """Use this method to access a dictionary of album guessing profiles. Returns a dict mapping profile name
    to a list of album guessers, which are either tag objects or the magic string "DIRECTORY"."""
    def parseAlbumGrouper(name):
        if name == "album": # this is the default
            return tags.ALBUM
        elif name[0] == "t":
            return tags.get(name[1:])
        elif name == "DIRECTORY":
            return name
        else:
            raise ValueError("Could not parse album grouper element: {}".format(name))
    global _profiles
    if _profiles is None:
        pr = config.storage.editor.guess_profiles
        _profiles = {}
        for name, lst in pr.items():
            _profiles[name] = list(map(parseAlbumGrouper, lst))
    return _profiles

def storeProfiles():
    """Save the current album guessing profiles into the storage."""
    storage_profiles = {}
    for name, lst in profiles().items():
        storage_profiles[name] = []
        for item in lst:
            if item == "DIRECTORY":
                storage_profiles[name].append(item)
            else:
                storage_profiles[name].append('t' + item.name)
    config.storage.editor.guess_profiles = storage_profiles
        
class ProfileChangeNotifier(QtCore.QObject):
    """This singleton class is used to populate changes in the guessing profiles through multiple editors."""
    profilesChanged = QtCore.pyqtSignal()     
profileNotifier = ProfileChangeNotifier()
profileNotifier.profilesChanged.connect(storeProfiles)
    
class EditorTreeView(treeview.TreeView):
    """This is the main widget of an editor: The tree view showing the current element tree."""

    actionConfig = treeview.TreeActionConfiguration()
     
    sect = translate(__name__, "editor")
    actionConfig.addActionDefinition(((sect, 'remove'),), DeleteAction, mode = CONTENTS)
    actionConfig.addActionDefinition(((sect, 'merge'),), MergeAction)
    actionConfig.addActionDefinition(((sect, 'clearEditor'),), rootedtreemodel.ClearTreeAction)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.level = levels.editor
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.setModel(editor.EditorModel())
        self.setItemDelegate(editordelegate.EditorDelegate(self))
        self.viewport().setMouseTracking(True)
        

    def dragEnterEvent(self, event):
        if event.source() is self:
            event.setDropAction(Qt.MoveAction)
        else:
            event.setDropAction(Qt.CopyAction)
        event.acceptProposedAction()
        super().dragEnterEvent(event)
        
    def dragMoveEvent(self, event):
        if isinstance(event.source(), EditorTreeView):
            if event.keyboardModifiers() & Qt.ShiftModifier:
                event.setDropAction(Qt.MoveAction)
            elif event.keyboardModifiers() & Qt.ControlModifier:
                event.setDropAction(Qt.CopyAction)
        super().dragMoveEvent(event)
        
    def dropEvent(self, event):
        # workaround due to bug #67
        if event.mouseButtons() & Qt.LeftButton:
            event.ignore()
            return
        if isinstance(event.source(), EditorTreeView):
            if event.keyboardModifiers() & Qt.ShiftModifier:
                event.setDropAction(Qt.MoveAction)
            elif event.keyboardModifiers() & Qt.ControlModifier:
                event.setDropAction(Qt.CopyAction)
            elif event.source() is self:
                event.setDropAction(Qt.MoveAction)
            else:
                event.setDropAction(Qt.CopyAction)
        super().dropEvent(event)
        
    
    def _expandInsertedRows(self, parent, start, end):
        for row in range(start, end+1):
            child = self.model().index(row, 0, parent)
            self.expand(child)
    
    def setAutoExpand(self, state):
        if state:
            self.model().rowsInserted.connect(self._expandInsertedRows)
        else:
            try:
                self.model().rowsInserted.disconnect(self._expandInsertedRows)
            except TypeError:
                pass # was not connected
        
class EditorWidget(QtGui.QDockWidget):
    """The editor is a dock widget for editing elements and their structure. It provides methods to "guess"
    the album structure of new files that are dropped from the filesystem."""
    
    def __init__(self, parent = None, state = None, location = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('editor'))
        widget = QtGui.QWidget()
        self.setWidget(widget)
        vb = QtGui.QVBoxLayout(widget)
        try:
            expand,profile  = state
        except:
            expand = True
            profile = "dontguess"
        self.editor = EditorTreeView()
        self.editor.setAutoExpand(expand)
        vb.addWidget(self.editor)
        hb = QtGui.QHBoxLayout()
        vb.addLayout(hb)
        
        self.autoExpandCheckbox = QtGui.QCheckBox(self.tr('auto expand'))
        self.autoExpandCheckbox.setChecked(expand)
        self.autoExpandCheckbox.stateChanged.connect(self.editor.setAutoExpand)
        self.autoExpandCheckbox.setToolTip(self.tr('auto expand dropped containers'))
        hb.addWidget(self.autoExpandCheckbox)
                
        self.guessProfileCombo = QtGui.QComboBox()
        self.guessProfileCombo.addItem(self.tr("no guessing"))
        self.guessProfileCombo.addItems(list(profiles().keys()))
        self.guessProfileCombo.addItem(self.tr("configure..."))
        self.guessProfileCombo.setToolTip(self.tr("select album guessing profile"))
        self.guessProfileCombo.currentIndexChanged[int].connect(self._handleProfileCombo)
        self.guessIndex = 0
        if profile == "dontguess":
            self.guessProfileCombo.setCurrentIndex(0)
        elif profile in profiles():
            for i in range(1, self.guessProfileCombo.count()-1):
                if self.guessProfileCombo.itemText(i) == profile:
                    self.guessProfileCombo.setCurrentIndex(i)
                    self.guessIndex = i
                    break
        hb.addWidget(self.guessProfileCombo)
        
        hb.addWidget(QtGui.QLabel(self.tr("Item Display:")))
        hb.addWidget(delegateconfig.ConfigurationCombo(editordelegate.EditorDelegate.configurationType,
                                                       [self.editor]))
        hb.addStretch()
        self.toolbar = QtGui.QToolBar(self)
        self.toolbar.addAction(self.editor.treeActions['clearEditor'])
        commitAction = rootedtreemodel.CommitTreeAction(self.editor)
        self.addAction(commitAction)
        self.toolbar.addAction(commitAction)
        hb.addWidget(self.toolbar)
        profileNotifier.profilesChanged.connect(self._handleProfilesChanged)

    def _handleProfilesChanged(self):
        """This slot is called when the list of guess profiles changes. We have to update the 
        profile-combobox and check whether the currently selected profile is still available."""
        newProfiles = list(profiles().keys())
        myProfiles = []
        self.guessProfileCombo.currentIndexChanged[int].disconnect(self._handleProfileCombo)
        for i in range(1, self.guessProfileCombo.count()-1):
            myProfiles.append(self.guessProfileCombo.itemText(i))
        currentProfile = self.guessProfileCombo.currentText()
        if self.guessProfileCombo.currentIndex() == 0:
            currentProfile = 0
        for i, profile in reversed(list(enumerate(myProfiles, start=1))):
            if profile not in newProfiles:
                self.guessProfileCombo.removeItem(i)
        for p in newProfiles:
            if p not in myProfiles:
                self.guessProfileCombo.insertItem(self.guessProfileCombo.count()-1, p)
        self.guessProfileCombo.currentIndexChanged[int].connect(self._handleProfileCombo)
        if currentProfile != 0:
            if currentProfile in newProfiles:
                for i in range(1, self.guessProfileCombo.count()-1):
                    if self.guessProfileCombo.itemText(i) == currentProfile:
                        self.guessProfileCombo.setCurrentIndex(i)
                        break
            else:
                self.guessProfileCombo.setCurrentIndex(0)
            
    def _handleProfileCombo(self, index):
        """Handles changes of the current index of the guess profile combobox. If the last item is chosen,
        a profile configuration dialog is opened."""
        if index == self.guessIndex:
            return
        if index == 0:
            self.editor.model().albumGroupers = []
            self.guessIndex = 0
        elif index == self.guessProfileCombo.count() - 1:
            if self.guessIndex != 0:
                profile = self.guessProfileCombo.itemText(self.guessIndex)
            else:
                profile = ''
            dialog = ConfigureGuessProfilesDialog(self, profile)
            self.guessProfileCombo.setCurrentIndex(self.guessIndex)
            dialog.exec_()
            profileNotifier.profilesChanged.emit()
            
        else:
            self.editor.model().albumGroupers = profiles()[self.guessProfileCombo.itemText(index)]
            self.guessIndex = index
    
    def saveState(self):
        if self.guessProfileCombo.currentIndex() == 0:
            profile = "dontguess"
        else:
            profile = self.guessProfileCombo.currentText()
        return (self.autoExpandCheckbox.isChecked(),profile)
# register this widget in the main application
eData = mainwindow.WidgetData(id = "editor",
                             name = translate("Editor","editor"),
                             theClass = EditorWidget,
                             central = True,
                             dock = True,
                             default = True,
                             unique = False,
                             preferredDockArea = Qt.RightDockWidgetArea)
mainwindow.addWidgetData(eData)

def activeEditorModels():
    """Returns a list containing the models of all open editor models."""
    return [dock.editor.model() for dock in mainwindow.mainWindow.getWidgets('editor')]

class ConfigureGuessProfilesDialog(QtGui.QDialog):
    """A dialog to configure the profiles used for "guessing" album structures. 
    
    Each profile is determined by its name, and contains a list of tags by which albums are grouped. One
    tag is the "main" grouper tag; this one is used to determine the TITLE-tag of the new album as well as
    for automatic meta-container guessing. Additionally, each profile sets the "directory mode" flag. If 
    that is enabled, only albums within the same directory on the filesystem will be grouped together."""
    def __init__(self, parent, profile = ''):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(self.tr("Configure Album Guessing Profiles"))
        mainLayout = QtGui.QVBoxLayout(self)
        descriptionLabel = QtGui.QLabel(self.tr(
"""Configuration of the "album guessing" profiles. These profiles determine how the editor tries to \
guess the album structure of files which are dropped into the editor.

Album guessing is done by means of a list of tags; all files whose tags coincide for this list will then be \
considered an album. The "main" grouper tag determines the TITLE tag of the new album. If "directory mode" \
is on, files will only be grouped together if they are in the same directory."""))
        descriptionLabel.setWordWrap(True)
        mainLayout.addWidget(descriptionLabel)
        self.profileChooser = QtGui.QComboBox(self)
        prfs = list(profiles().keys())
        self.profileChooser.addItems(prfs)
        self.profileChooser.setCurrentIndex(prfs.index(profile) if profile != '' else 0)
        self.profileChooser.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Preferred)
        self.profileChooser.currentIndexChanged[str].connect(self.setCurrentProfile)
        self.newProfileButton = QtGui.QPushButton(self.tr("new"))
        self.newProfileButton.clicked.connect(self.newProfile)
        self.deleteProfileButton = QtGui.QPushButton(self.tr("remove"))
        self.deleteProfileButton.clicked.connect(self.removeProfile)
        chooserLayout = QtGui.QHBoxLayout()
        chooserLayout.addWidget(self.profileChooser)
        #chooserLayout.addStretch()
        chooserLayout.addWidget(self.newProfileButton)
        chooserLayout.addWidget(self.deleteProfileButton)
        
        mainLayout.addLayout(chooserLayout)
        
        currentNameLayout = QtGui.QHBoxLayout()
        currentNameLayout.addWidget(QtGui.QLabel(self.tr("profile name:")))
        self.nameEdit = QtGui.QLineEdit()
        self.nameEdit.textEdited.connect(self.renameCurrent)
        self.nameEdit.setFocus()
        currentNameLayout.addWidget(self.nameEdit)
        mainLayout.addLayout(currentNameLayout)
        
        configLayout = QtGui.QHBoxLayout()
        self.preview = QtGui.QListWidget()
        configSideLayout = QtGui.QVBoxLayout()
        self.addTagButton = QtGui.QPushButton(self.tr("add tag..."))
        self.tagMenu = QtGui.QMenu()
        self.tagActions = []
        actionGroup = QtGui.QActionGroup(self)
        for tag in tags.tagList:
            tagAction = QtGui.QAction(self)
            tagAction.setText(str(tag))
            tagAction.setData(tag)
            actionGroup.addAction(tagAction)
            self.tagMenu.addAction(tagAction)
            self.tagActions.append(tagAction)
        self.addTagButton.setMenu(self.tagMenu)
        actionGroup.triggered.connect(self.addTag)
        self.removeTagButton = QtGui.QPushButton(self.tr("remove tag"))
        self.removeTagButton.clicked.connect(self.removeTag)
        self.directoryModeButton = QtGui.QPushButton(self.tr("directory mode"))
        self.directoryModeButton.setCheckable(True)
        self.directoryModeButton.setToolTip(
"""If this is checked, only files within the same directory will be considered for automatic album
guessing. This is useful in most cases, unless you have albums that are split across several folders.""")
        self.directoryModeButton.clicked[bool].connect(self.setDirectoryMode)
        configSideLayout.addWidget(self.addTagButton)
        configSideLayout.addWidget(self.removeTagButton)
        configSideLayout.addWidget(self.directoryModeButton)
        self.setMainGrouperButton = QtGui.QPushButton(self.tr("set to main"))
        self.setMainGrouperButton.clicked.connect(self.setMain)
        configSideLayout.addWidget(self.setMainGrouperButton)
        configSideLayout.addStretch()
        configLayout.addWidget(self.preview)
        configLayout.addLayout(configSideLayout)
        mainLayout.addLayout(configLayout)
        
        controlBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Close)
        #dialogControlLayout = QtGui.QHBoxLayout()
        #closeButton = QtGui.QPushButton(self.tr("close"))
        controlBox.rejected.connect(self.accept)
        mainLayout.addWidget(controlBox)
        if profile == '' and len(profiles()) > 0:
            profile = list(profiles().keys())[0]
        self.setCurrentProfile(profile)
        
    def removeProfile(self):
        i = self.profileChooser.currentIndex()
        name = self.profileChooser.currentText()
        del profiles()[name]
        self.profileChooser.removeItem(i)
        
    def newProfile(self):
        name= self.tr("newProfile")
        if name in profiles():
            for i in itertools.count():
                if name + str(i) not in profiles():
                    name = name + str(i)
                    break
        profiles()[name] = ["DIRECTORY"]
        self.setCurrentProfile(name)
        self.profileChooser.addItem(name)
        self.profileChooser.setCurrentIndex(self.profileChooser.count()-1)
        
    def setCurrentProfile(self, name):
        self.profile = name
        self.nameEdit.setText(name)
        self.nameEdit.setEnabled(name != '')
        self.preview.setEnabled(name != '')
        self.preview.clear()
        if name != '':
            profile = profiles()[name]
            self.directoryModeButton.setChecked("DIRECTORY" in profile)
            for thing in profile:
                if thing != "DIRECTORY":
                    self.preview.addItem(str(thing))
            if self.preview.count() > 0:
                mainItem = self.preview.item(0)
                f = mainItem.font()
                f.setBold(True)
                mainItem.setFont(f)
                self.preview.setCurrentRow(0)
            for action in self.tagActions:
                action.setDisabled(action.data() in profile)
    
    def renameCurrent(self, newName):
        profile = profiles()[self.profile]
        profiles()[newName] = profile
        del profiles()[self.profile]
        self.profile = newName
        self.profileChooser.setItemText(self.profileChooser.currentIndex(), newName)
    
    def addTag(self, action):
        self.preview.addItem(action.text())
        profiles()[self.profile].append(action.data())
        action.setDisabled(True)
        if self.preview.count() == 1:
            self.preview.setCurrentRow(0)
            self.setMain()
        
    def removeTag(self):
        tagName = self.preview.currentItem().text()
        tag = tags.get(tagName)
        for action in self.tagActions:
            if action.data() == tag:
                action.setEnabled(True)
        self.preview.takeItem(self.preview.currentRow())
        profiles()[self.profile].remove(tag)
    
    def setMain(self):
        item = self.preview.currentItem()
        tag = tags.get(item.text())
        profiles()[self.profile].remove(tag)
        profiles()[self.profile].insert(0, tag)
        for i in range(self.preview.count()):
            item = self.preview.item(i)
            font = item.font()
            font.setBold(i == self.preview.currentRow())
            item.setFont(font)
            
    def setDirectoryMode(self, mode):
        if mode:
            profiles()[self.profile].append("DIRECTORY")
        else:
            profiles()[self.profile].remove("DIRECTORY")
