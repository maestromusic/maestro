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
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

import itertools, collections
from . import config, logging
logger = logging.getLogger("omg.player")
STOP, PLAY, PAUSE = range(3)
DISCONNECTED, CONNECTING, CONNECTED = range(3)


configuredBackends = collections.OrderedDict() # map profile name -> backend name
backendClasses = collections.OrderedDict() # map mackend name -> backend class (subclass of PlayerBackend)

def init():
    global configuredBackends
    for name, backend in config.storage.player.configured_players:
        configuredBackends[name] = backend
    updateConfig()
def updateConfig():
    config.storage.player.configured_players = list(configuredBackends.items()) #hack: trick config.storage!
_runningBackends = {}
def instance(name):
    """Returns the instance of the player backend according to the given profile name.
    If the instance does not yet exist, it is created."""
    if name not in _runningBackends:
        _runningBackends[name] = backendClasses[configuredBackends[name]](name)
    return _runningBackends[name]

class ProfileNotifier(QtCore.QObject):
    profileRenamed = QtCore.pyqtSignal(str, str) # old name, new name
    profileAdded = QtCore.pyqtSignal(str, str) # profile name, backend name
    profileRemoved = QtCore.pyqtSignal(str)
    def __init__(self):
        super().__init__()
notifier = ProfileNotifier()

# debug output
notifier.profileRenamed.connect(lambda a, b: logger.debug("renamed profile {} to {}".format(a,b)))
notifier.profileAdded.connect(lambda a, b: logger.debug("added profile {} class {}".format(a,b)))
notifier.profileRemoved.connect(lambda a: logger.debug("removed profiel {}".format(a)))

def addProfile(name, backend):
    configuredBackends[name] = backend
    updateConfig()
    notifier.profileAdded.emit(name, backend)

def renameProfile(old, new):
    global configuredBackends
    configuredBackends = collections.OrderedDict(
        ((new if name==old else name), backend) for name,backend in configuredBackends.items())
    updateConfig()
    notifier.profileRenamed.emit(old, new)

def removeProfile(name):
    del configuredBackends[name]
    updateConfig()
    notifier.profileRemoved.emit(name)

class BackendChooser(QtGui.QComboBox):
    """This class provides a combo box that lets the user choose the a player backend from
    the list of existing backends. In such a case, the signal *backendChanged* is emitted."""
    
    ignoreSignal = False
    
    backendChanged = QtCore.pyqtSignal(str)
    def __init__(self, parent = None):
        super().__init__(parent)
        for name in configuredBackends:
            self.addItem(name)
        
        self.storedIndex = 0
        self.addItem(self.tr("configure..."))
        self.currentIndexChanged[int].connect(self.handleIndexChange)
        notifier.profileRenamed.connect(self.handleProfileRenamed)
        notifier.profileAdded.connect(lambda name: self.insertItem(self.count()-1, name))
        notifier.profileRemoved.connect(self.handleProfileRemoved)
    
    def currentProfile(self):
        """Returns the name of the currently selected profile, or *None* if none is selected.
        
        The latter happens especially in the case that no profile is configured."""
        if self.currentIndex() == self.count()-1:
            return None
        return self.currentText()                         
    def handleIndexChange(self, i):
        if BackendChooser.ignoreSignal:
            return
        if i != self.count() - 1:
            self.backendChanged.emit(self.itemText(i))
            self.storedIndex = i
        else:
            BackendChooser.ignoreSignal = True            
            BackendConfigDialog(self, self.itemText(self.storedIndex)).exec_()
            self.setCurrentIndex(self.storedIndex)
            BackendChooser.ignoreSignal = False
            
    def mousePressEvent(self, event):
        if self.count() == 1 and event.button() == Qt.LeftButton:
            BackendChooser.ignoreSignal = True
            BackendConfigDialog(self, None).exec_()
            BackendChooser.ignoreSignal = False
            event.accept()
        else:
            return super().mousePressEvent(event)
     
    def handleProfileRenamed(self, old, new):
        for i in range(self.count()-1):
            if self.itemText(i) == old:                
                self.setItemText(i, new)
                break
    
    def handleProfileRemoved(self, name):
        for i in range(self.count()-1):
            if self.itemText(i) == name:
                wasIgnore = BackendChooser.ignoreSignal
                BackendChooser.ignoreSignal = True
                self.removeItem(i)
                BackendChooser.ignoreSignal = wasIgnore
                #TODO: handle removal of current profile!
                break
    
class PlayerBackend(QtCore.QObject):
    """This is an abstract class for modules that implement connection to a backend
    providing audio playback and playlist management.
    
    In addition to the setter functions below, the attributes state, volume, currentSong,
    elapsed should be present in each implementing subclass."""
    
    stateChanged = QtCore.pyqtSignal(int)
    volumeChanged = QtCore.pyqtSignal(int)
    currentSongChanged = QtCore.pyqtSignal(int)
    elapsedChanged = QtCore.pyqtSignal(float, float)
    playlistChanged = QtCore.pyqtSignal()
    connectionStateChanged = QtCore.pyqtSignal(int)
    
    def __init__(self, name):
        super().__init__()
        notifier.profileRenamed.connect(self._handleProfileRename)
        self.name = name
        self.state = STOP
        self.volume = 0
        self.currentSong = -1
        self.elapsed = 0
        self.currentSongLength = 0
        self.connected = False
    
    def _handleProfileRename(self, old, new):
        if self.name == old:
            self.name = new
            
    @staticmethod
    def configWidget(profile = None):
        """Return a config widget, initialized with the data of the given *profile*."""
        raise NotImplementedError()
    
    @QtCore.pyqtSlot(int)
    def setState(self, state):
        """Set the state of the player to one of STOP, PLAY, PAUSE."""
        raise NotImplementedError()
     
    @QtCore.pyqtSlot(int)
    def setVolume(self, volume):
        """Set the volume of the player. *volume* must be an integer between 0 and 100."""
        raise NotImplementedError()
    
    @QtCore.pyqtSlot(int)
    def setCurrentSong(self, index):
        """Set the song at offset *index* as active."""
        raise NotImplementedError()
    
    @QtCore.pyqtSlot(float)
    def setElapsed(self, seconds):
        """Jump within the currently playing song to the position at time *seconds*, which
        is a float."""
        raise NotImplementedError()
    
    def currentPlaylist(self):
        """Returns the current playlist in form of a root node."""
        raise NotImplementedError()
    
    @QtCore.pyqtSlot(object)
    def setPlaylist(self, root):
        """Change the playlist; *root* is an instance of models.RootNode containing the playlist
        elements as children."""
        raise NotImplementedError()
    
    @QtCore.pyqtSlot()
    def next(self):
        """Jump to the next song in the playlist. If the playlist is stopped or at the last 
        song, this is ignored."""
        raise NotImplementedError()
    
    @QtCore.pyqtSlot()
    def previous(self):
        """Jump to the previous song in the playlist. If the playlist is stopped or at the
        first song, this is ignored."""
        raise NotImplementedError()
        raise NotImplementedError
    
class BackendConfigDialog(QtGui.QDialog):
    
    def __init__(self, parent = None, currentProfile = None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(self.tr("Configure Player Backends"))
        self.profileChooser = QtGui.QComboBox(self)
        self.profiles = {}
        for i, name in enumerate(configuredBackends):
            self.profileChooser.addItem(name)
            self.profiles[name] = i
        self.profileChooser.currentIndexChanged[str].connect(self.setCurrentProfile)
        self.newButton = QtGui.QPushButton(self.tr("new"))
        self.newButton.clicked.connect(self.newProfile)
        self.deleteButton = QtGui.QPushButton(self.tr("remove"))
        self.deleteButton.clicked.connect(self.removeCurrentProfile)
        topLayout = QtGui.QHBoxLayout()
        topLayout.addWidget(self.profileChooser, stretch = 1)
        topLayout.addWidget(self.newButton)
        topLayout.addWidget(self.deleteButton)
        
        self.classChooser = QtGui.QComboBox(self)
        self.classes = {}
        for i, name in enumerate(backendClasses):
            self.classChooser.addItem(name)
            self.classes[name] = i
        self.classChooser.currentIndexChanged[str].connect(self.changeConfigureWidget)
        self.nameEdit = QtGui.QLineEdit(self)
        self.nameEdit.editingFinished.connect(self.renameCurrentLayout)
        self.nameEdit.setFocus()
        secondLayout = QtGui.QHBoxLayout()
        secondLayout.addWidget(QtGui.QLabel(self.tr("Profile name:")))
        secondLayout.addWidget(self.nameEdit)
        secondLayout.addWidget(QtGui.QLabel(self.tr("Backend:")))
        secondLayout.addWidget(self.classChooser)
        
        
        controlBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Close)

        
        controlBox.rejected.connect(self.ensureConfigIsStored)
        controlBox.rejected.connect(self.accept)
        mainLayout = QtGui.QVBoxLayout(self)
        mainLayout.addLayout(topLayout, stretch = 0)
        mainLayout.addLayout(secondLayout, stretch = 0)
        mainLayout.addWidget(controlBox, stretch = 1)
        self.mainLayout = mainLayout
        self.classConfigWidget = None
        self.setCurrentProfile(currentProfile)
    
    def renameCurrentLayout(self):
        text = self.nameEdit.text()
        if text == '':
            return
        if self.profileChooser.currentText() == text:
            return
        renameProfile(self.profileChooser.currentText(), text)
        self.profileChooser.setItemText(self.profileChooser.currentIndex(), text)
        self.storedProfile = text
    
    def removeCurrentProfile(self):
        name = self.profileChooser.currentText()
        self.profileChooser.removeItem(self.profileChooser.currentIndex())
        removeProfile(name)
        self.profiles = {}
        for i, name in enumerate(configuredBackends):
            self.profiles[name] = i
          
    def setCurrentProfile(self, name):
        self.nameEdit.setEnabled(bool(name))
        self.classChooser.setEnabled(bool(name))
        self.deleteButton.setEnabled(bool(name))
        if self.classConfigWidget is not None:
            self.ensureConfigIsStored()
            self.mainLayout.removeWidget(self.classConfigWidget)
            self.classConfigWidget.setVisible(False)
        if name:
            backend = configuredBackends[name]
            self.classChooser.setCurrentIndex(self.classes[backend])
            self.changeConfigureWidget(backend)            
            self.nameEdit.setText(name)
        self.storedProfile = name
    
    def ensureConfigIsStored(self):
        if self.classConfigWidget is not None:
            self.classConfigWidget.storeProfile(self.storedProfile)
    def changeConfigureWidget(self, backend):
        self.classConfigWidget = backendClasses[backend].configWidget(self.profileChooser.currentText())
        self.mainLayout.insertWidget(2, self.classConfigWidget)
        
    def newProfile(self):
        name= self.tr("newProfile")
        if name in self.profiles:
            for i in itertools.count():
                if name + str(i) not in self.profiles:
                    name = name + str(i)
                    break
        backend = next(iter(backendClasses))
        addProfile(name, backend)
        self.profiles[name] = len(self.profiles)
        self.profileChooser.addItem(name)
        self.profileChooser.setCurrentIndex(self.profileChooser.count()-1)
        