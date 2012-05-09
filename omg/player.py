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

import collections

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import config, logging

logger = logging.getLogger(__name__)

STOP, PLAY, PAUSE = range(3)
DISCONNECTED, CONNECTING, CONNECTED = range(3)


configuredBackends = collections.OrderedDict() # map profile name -> backend name
backendClasses = collections.OrderedDict() # map mackend name -> backend class (subclass of PlayerBackend)

_runningBackends = {}


def init():
    """Initialize the module. Reads profiles in the storage. Call this once at application startup."""
    global configuredBackends
    for name, backend in config.storage.player.configured_players:
        configuredBackends[name] = backend
    updateConfig()
    
    
def updateConfig():
    """Update information about configured player backends in the storage.""" 
    config.storage.player.configured_players = list(configuredBackends.items()) #hack: trick config.storage! #TODO: what trick?


def instance(name):
    """Returns the instance of the player backend according to the given profile name.
    If the instance does not yet exist, it is created."""
    if name not in _runningBackends:
        if configuredBackends[name] not in backendClasses:
            logger.warning('Could not load playback profile {} because backend {} is not available. '
                           'Did you forget to load the plugin?'.format(
                  name, configuredBackends[name]))
            return None
        _runningBackends[name] = backendClasses[configuredBackends[name]](name)
    return _runningBackends[name]


class ProfileNotifier(QtCore.QObject):
    """A notifier class which emits signals when profiles are renamed, added, or removed."""
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
    """Add a profile name *name* for backend *backend*. Creates the profile in configuredBackends,
    updates the storage, and lets the ProfileNotifier emit an appropriate signal."""
    configuredBackends[name] = backend
    updateConfig()
    notifier.profileAdded.emit(name, backend)


def renameProfile(old, new):
    """Rename profile *old* to *new*. Updates configuredBackends and the storage
    and lets the ProfileNotifier emit an appropriate signal."""
    global configuredBackends
    configuredBackends = collections.OrderedDict(
        ((new if name==old else name), backend) for name,backend in configuredBackends.items())
    updateConfig()
    notifier.profileRenamed.emit(old, new)


def removeProfile(name):
    """Remove the profile named *name*. Updates configuredBackends,
    updates the storage, and lets the ProfileNotifier emit an appropriate signal."""
    del configuredBackends[name]
    updateConfig()
    notifier.profileRemoved.emit(name)


class PlayerBackend(QtCore.QObject):
    """This is an abstract class for modules that implement connection to a backend
    providing audio playback and playlist management.
    
    In addition to the setter functions below, the attributes state, volume, currentSong,
    elapsed should be present in each implementing subclass.
    
    For many backends it may be appropriate to run this in its own thread. See the mpd
    backend plugin for an example of how to do this. Because it is likely that a PlayerBackend
    lives in a different thread and that (some of) the slots defined here may block for
    a nontrivial amount of time, every module that uses a PlayerBackend must ensure to
    _always_ call these slots via a (inter-thread) signal-slot-connection and _not_ directly.
    Use QMetaObject.ivokeMethod() if you need to directly call a slot method."""
    #TODO: is the stuff above still valid? Seems to me that even MPDBackend runs in the main thread and uses a different thread internally
    
    stateChanged = QtCore.pyqtSignal(int)
    """Emits on of player.{PLAY, STOP,PAUSE} if the backend's state has changed."""
    volumeChanged = QtCore.pyqtSignal(int)
    currentSongChanged = QtCore.pyqtSignal(int)
    elapsedChanged = QtCore.pyqtSignal(float, float)
    connectionStateChanged = QtCore.pyqtSignal(int)
    
    def __init__(self, name):
        super().__init__()
        notifier.profileRenamed.connect(self._handleProfileRename)
        self.name = name
        self.state = STOP
        self.connectionState = DISCONNECTED
        self.volume = 0
        self.currentSong = -1
        self.elapsed = 0
        self.currentSongLength = 0
        self.playlist = None
    
    def _handleProfileRename(self, old, new):
        if self.name == old:
            self.name = new
            
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
    
    def nextSong(self):
        """Jump to the next song in the playlist. If the playlist is stopped or at the last 
        song, this is ignored."""
        raise NotImplementedError()
    
    def previousSong(self):
        """Jump to the previous song in the playlist. If the playlist is stopped or at the
        first song, this is ignored."""
        raise NotImplementedError()
    
    def addTreeActions(self, playlist):
        """This method can be used to add custom actions to a treeview which are specific
        to this backend. The actions should be added to *playlist* by calling its
        *addAction* method."""
        pass
    
    def setPlaylist(self,paths):
        pass
    
    def insertIntoPlaylist(self,pos,paths):
        pass
    
    def removeFromPlaylist(self,begin,end):
        pass
     
    def registerFrontend(self, obj):
        """Tell this player class that a frontend object *obj* started to use it. The backend
        can use this information e.g. to make a connection retry or to start polling."""
        pass
    
    def unregisterFrontend(self, obj):
        """Tell this player class that a frontend object *obj* thas stopped using the backend.
        This may be used to stop time-consuming backend operations as soon as nobody is using
        it anymore."""
        pass
    
