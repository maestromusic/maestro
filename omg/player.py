# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
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

from PyQt4 import QtCore

from . import config, logging, profiles

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

STOP, PLAY, PAUSE = range(3)
DISCONNECTED, CONNECTING, CONNECTED = range(3)

FLAG_REPEATING = 1
FLAG_RANDOM = 2
FLAG_RANDOM_WORKS = 4

# Return values for getRandom, setRandom
RANDOM_OFF = 0
RANDOM_ON = FLAG_RANDOM
RANDOM_WORKS = FLAG_RANDOM_WORKS


_runningBackends = {}

profileCategory = profiles.TypedProfileCategory(
    name = 'playback',
    title = translate('PlayerBackend','Playback'),
    storageOption = config.storageObject.player.profiles,
    description = translate("PlayerBackend",
                            "OMG can control more than one audio backend. To easily switch between them, "
                            "their configuration is stored in profiles."),
    iconPath = ':omg/icons/preferences/audiobackends_small.png',
    pixmapPath = ':omg/icons/preferences/audiobackends.png',
    saveImmediately=False)
profiles.manager.addCategory(profileCategory)


class BackendError(Exception):
    pass


class InsertError(BackendError):
    def __init__(self, msg, successfulURLs=[]):
        super().__init__(msg)
        self.successfulURLs = successfulURLs


class PlayerBackend(profiles.Profile):
    """This is the base class for modules that implement connection to a backend
    providing audio playback and playlist management.
    """
    stateChanged = QtCore.pyqtSignal(int) #Emits one of {PLAY, STOP,PAUSE} if the backend's state has changed
    volumeChanged = QtCore.pyqtSignal(int)
    currentChanged = QtCore.pyqtSignal(int)
    elapsedChanged = QtCore.pyqtSignal(float)
    connectionStateChanged = QtCore.pyqtSignal(int)
    flagsChanged = QtCore.pyqtSignal(int)
    
    def __init__(self, name, type, state):
        super().__init__(name, type, state)
        self.connectionState = DISCONNECTED
    
    def state(self):
        """Return the current player state from STOP, PLAY, PAUSE."""
        raise NotImplementedError()
    
    def setState(self, state):
        """Set the state of the player to one of STOP, PLAY, PAUSE."""
        raise NotImplementedError()
     
    def play(self):
        self.setState(PLAY)
    
    def stop(self):
        self.setState(STOP)
    
    def pause(self):
        self.setState(PAUSE)
        
    def volume(self):
        """Return the current volume as integer between 0 and 100."""
        raise NotImplementedError()
     
    def setVolume(self, volume):
        """Set the volume of the player. *volume* must be an integer between 0 and 100."""
        raise NotImplementedError()
    
    def current(self):
        """Return the current song as wrapper."""
        raise NotImplementedError()
    
    def currentOffset(self):
        """Return the offset of the current song."""
        raise NotImplementedError()
    
    def setCurrent(self, offset):
        """Set the song at offset *offset* as active and start playing it."""
        raise NotImplementedError()
    
    def elapsed(self):
        """Return the position of the currently playing song in seconds (as float)."""
        raise NotImplementedError()
    
    def setElapsed(self, seconds):
        """Jump within the currently playing song to the position at time *seconds*, which
        is a float."""
        raise NotImplementedError()
    
    def skipForward(self):
        """Jump to the next song in the playlist. If the playlist is stopped or at the last 
        song, this is ignored."""
        raise NotImplementedError()
    
    def skipBackward(self):
        """Jump to the previous song in the playlist. If the playlist is stopped or at the
        first song, this is ignored."""
        raise NotImplementedError()
    
    def treeActions(self):
        """This method can be used to add custom actions to a treeview which are specific
        to this backend. The actions should be added to *playlist* by calling its
        *addAction* method."""
        return []
    
    def setPlaylist(self, urls):
        """Clear the playlist and set it to the given urls."""
        pass
    
    def insertIntoPlaylist(self, pos, urls):
        """Insert the given urls at *pos* into the playlist."""
        pass
    
    def removeFromPlaylist(self, begin, end):
        """Remove the songs with offsets >= *begin* and < *end* from the playlist."""
        pass
    
    def move(self, fromOffset, toOffset):
        """Move a song within the playlist. If the current song is moved the player should keep playing at
        the same position.
        *fromOffset* is the old position in the playlist, *toOffset* is the new one, after the move. That
        means that for forward moves, *toOffset* is one less than the insertion position.
        """
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
    
    def connectBackend(self):
        pass
    
    def flags(self):
        """Return a bitwise-OR of the currently set flags (see the FLAG_*-constants defined in this module).
        """
        return 0
    
    def setFlags(self, flags):
        """Set flags using a bitwise-OR of the FLAG_*-constants defined in this module."""
        pass
    
    def isRepeating(self):
        """Return whether the player will restart the playlist when it is finished."""
        return FLAG_REPEATING & self.flags()
    
    def setRepeating(self, repeating):
        """Set whether the player should restart the playlist when it is finished."""
        if repeating:
            self.setFlags(self.flags() | FLAG_REPEATING)
        else: self.setFlags(self.flags() & ~FLAG_REPEATING)
        
    def getRandom(self):
        """Return random mode from {RANDOM_OFF, RANDOM_ON, RANDOM_WORKS}."""
        if FLAG_RANDOM_WORKS & self.flags():
            return RANDOM_WORKS
        elif FLAG_RANDOM & self.flags():
            return RANDOM_ON
        else: return RANDOM_OFF
    
    def setRandom(self, random):
        """Set random mode to one of RANDOM_OFF, RANDOM_ON, RANDOM_WORKS."""
        if random == RANDOM_OFF:
            self.setFlags(self.flags() & ~FLAG_RANDOM & ~FLAG_RANDOM_WORKS)
        elif random == RANDOM_ON:
            self.setFlags(self.flags() | FLAG_RANDOM)
        elif random == RANDOM_WORKS:
            self.setFlags(self.flags() | FLAG_RANDOM | FLAG_RANDOM_WORKS)
        else:
            raise ValueError("Invalid value for argument *random*: {}".format(random))
