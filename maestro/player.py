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

import enum

from PyQt5 import QtCore
translate = QtCore.QCoreApplication.translate

from maestro import config, profiles


class PlayState(enum.Enum):
    Stop = 0
    Play = 1
    Pause = 2


class ConnectionState(enum.Enum):
    Disconnected = 0
    Connecting = 1
    Connected = 2


profileCategory = profiles.TypedProfileCategory(
    name = 'playback',
    title = translate('PlayerBackend','Playback'),
    storageOption = config.getOption(config.storage, 'player.profiles'),
    description = translate("PlayerBackend",
                    "Maestro can control more than one audio backend. To easily switch between them, "
                    "their configuration is stored in profiles."),
    iconPath = ':maestro/icons/preferences/audiobackends_small.png',
    pixmapPath = ':maestro/icons/preferences/audiobackends.png')
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
    stateChanged = QtCore.pyqtSignal(PlayState)
    volumeChanged = QtCore.pyqtSignal(int)
    currentChanged = QtCore.pyqtSignal(object)
    elapsedChanged = QtCore.pyqtSignal(float)
    connectionStateChanged = QtCore.pyqtSignal(ConnectionState)
    
    def __init__(self, name, type, state):
        super().__init__(name, type, state)
        self.connectionState = ConnectionState.Disconnected
        self.playlist = None
        self.numFrontends = 0
    
    def state(self) -> PlayState:
        """Return the current player state."""
        raise NotImplementedError()
    
    def setState(self, state: PlayState):
        """Set the state of the player."""
        raise NotImplementedError()
     
    def play(self):
        self.setState(PlayState.Play)
    
    def stop(self):
        self.setState(PlayState.Stop)
    
    def pause(self):
        self.setState(PlayState.Pause)
        
    def volume(self):
        """Return the current volume as integer between 0 and 100."""
        raise NotImplementedError()
     
    def setVolume(self, volume):
        """Set the volume of the player. *volume* must be an integer between 0 and 100."""
        raise NotImplementedError()
    
    def current(self):
        """Return the current song as wrapper."""
        return self.playlist.current
    
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
        raise NotImplementedError()
    
    def insertIntoPlaylist(self, pos, urls):
        """Insert the given urls at *pos* into the playlist."""
        raise NotImplementedError()
    
    def removeFromPlaylist(self, begin, end):
        """Remove the songs with offsets >= *begin* and < *end* from the playlist."""
        raise NotImplementedError()
    
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
        self.numFrontends += 1
    
    def unregisterFrontend(self, obj):
        """Tell this player class that a frontend object *obj* thas stopped using the backend.
        This may be used to stop time-consuming backend operations as soon as nobody is using
        it anymore."""
        self.numFrontends -= 1
    
    def connectBackend(self):
        pass
