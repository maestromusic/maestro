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

import itertools
from . import config, logging
logger = logging.getLogger("omg.player")
STOP, PLAY, PAUSE = range(3)


configuredBackends = {} # map profile name -> backend name
backendClasses = {} # map mackend name -> backend class (subclass of PlayerBackend)
def init():
    global configuredBackends
    for name, backend in config.storage.player.configured_players:
        configuredBackends[name] = backend

_runningBackends = {}
def instance(name):
    """Returns the instance of the player backend according to the given profile name.
    If the instance does not yet exist, it is created."""
    if name not in _runningBackends:
        _runningBackends[name] = backendClasses[configuredBackends[name]](name)
    return _runningBackends[name]
        

class BackendChooser(QtGui.QComboBox):
    """This class provides a combo box that lets the user choose the a player backend from
    the list of existing backends. In such a case, the signal *backendChanged* is emitted."""
    
    backendChanged = QtCore.pyqtSignal(object)
    def __init__(self, parent = None):
        super().__init__(parent)
        for name, backend in configuredBackends.items():
            self.addItem(name)
        self.currentIndexChanged[int].connect(self.handleIndexChange)
        self.storedIndex = 0
        self.addItem(self.tr("configure..."))
        self.ignoreSignal = False
                             
    def handleIndexChange(self, i):
        if self.ignoreSignal:
            return
        if i != self.count() - 1:
            self.backendChanged.emit(self.itemText(i))
            self.storedIndex = i
        else:
            BackendConfigDialog(self, self.itemText(self.storedIndex)).exec_()
            self.ignoreSignal = True
            self.setCurrentIndex(self.storedIndex)
            self.ignoreSignal = False
        
            
    
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
    
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.state = STOP
        self.volume = 0
        self.currentSong = -1
        self.elapsed = 0
        self.currentSongLength = 0
    
    @staticmethod
    def configWidget(profile = None):
        """Return a config widget, initialized with the data of the given *profile*."""
        raise NotImplementedError()
         
    def setState(self, state):
        """Set the state of the player to one of STOP, PLAY, PAUSE."""
        raise NotImplementedError()
     
    def setVolume(self, volume):
        """Set the volume of the player. *volume* must be an integer between 0 and 100."""
        raise NotImplementedError()
    
    def setCurrentSong(self, index):
        """Set the song at offset *index* as active."""
        raise NotImplementedError()
    
    def setElapsed(self, seconds):
        """Jump within the currently playing song to the position at time *seconds*, which
        is a float."""
        raise NotImplementedError()
        
    def currentPlaylist(self):
        """Returns the current playlist in form of a root node."""
        raise NotImplementedError()
    
    def setPlaylist(self, root):
        """Change the playlist; *root* is an instance of models.RootNode containing the playlist
        elements as children."""
        raise NotImplementedError()
    
    def next(self):
        """Jump to the next song in the playlist. If the playlist is stopped or at the last 
        song, this is ignored."""
        raise NotImplementedError()
    
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
        topLayout = QtGui.QHBoxLayout()
        topLayout.addWidget(self.profileChooser, stretch = 1)
        topLayout.addWidget(self.newButton)
        topLayout.addWidget(self.deleteButton)
        
        self.classChooser = QtGui.QComboBox(self)
        self.classes = {}
        for i, name in enumerate(backendClasses):
            self.classChooser.addItem(name)
            self.classes[name] = i
        self.classChooser.currentIndexChanged[str].connect(self.backendClassChanged)
        self.nameEdit = QtGui.QLineEdit(self)
        self.nameEdit.editingFinished.connect(self.renameCurrentLayout)
        self.nameEdit.setFocus()
        secondLayout = QtGui.QHBoxLayout()
        secondLayout.addWidget(QtGui.QLabel(self.tr("Profile name:")))
        secondLayout.addWidget(self.nameEdit)
        secondLayout.addWidget(QtGui.QLabel(self.tr("Backend:")))
        secondLayout.addWidget(self.classChooser)
        
        
        controlBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Close)

        controlBox.rejected.connect(self.accept)
        
        mainLayout = QtGui.QVBoxLayout(self)
        mainLayout.addLayout(topLayout)
        mainLayout.addLayout(secondLayout)
        mainLayout.addWidget(controlBox)
        self.mainLayout = mainLayout
        self.classConfigWidget = None
        self.setCurrentProfile(currentProfile)
    
    def renameCurrentLayout(self):
        text = self.nameEdit.text()
        if text == '':
            return
        self.profileChooser.setItemText(self.profileChooser.currentIndex(), text)
          
    def setCurrentProfile(self, name):
        self.nameEdit.setEnabled(name is not None)
        self.classChooser.setEnabled(name is not None)
        self.deleteButton.setEnabled(name is not None)
        if name is not None:
            self.classChooser.setCurrentIndex(self.classes[configuredBackends[name]])
            self.backendClassChanged(configuredBackends[name])
            self.nameEdit.setText(name)
    
    def backendClassChanged(self, backend):
        if self.classConfigWidget is not None:
            self.mainLayout.removeWidget(self.classConfigWidget)
        self.classConfigWidget = backendClasses[backend].configWidget(self.profileChooser.currentText())
        self.mainLayout.insertWidget(2, self.classConfigWidget)
        
    def newProfile(self):
        name= self.tr("newProfile")
        if name in self.profiles:
            for i in itertools.count():
                if name + str(i) not in self.profiles:
                    name = name + str(i)
                    break
        cls = next(iter(backendClasses))
        configuredBackends[name] = cls
        self.profiles[name] = len(self.profiles)
        self.profileChooser.addItem(name)
        self.profileChooser.setCurrentIndex(self.profileChooser.count()-1)