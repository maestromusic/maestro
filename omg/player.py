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

from . import config
STOP, PLAY, PAUSE = range(3)


players = {}
playerClasses = {}
def init():
    global players #hi hi
    print(config.storage.player.configured_players)
    for name, cls in config.storage.player.configured_players:
        try:
            players[name] = playerClasses[cls](name)
            print('player created!')
        except KeyError:
            pass
        
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
        self.currentSong = 0
        self.elapsed = 0
        self.currentSongLength = 0
        
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