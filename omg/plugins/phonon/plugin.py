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

from PyQt4.phonon import Phonon as phonon
import urllib.parse

from ... import player, config, profiles, utils, strutils
from ...models import playlist
            
            
class PhononPlayerBackend(player.PlayerBackend):
    className = "Phonon"
    
    def __init__(self, name, config=None):
        super().__init__(name)
        
        # The list of paths in the playlist and the current song are stored directly in the model's tree
        self.playlist = playlist.PlaylistModel(self)
        if config is not None:
            if 'playlist' in config:
                self.playlist.initFromWrapperString(config['playlist'])
                if 'current' in config:
                    self.playlist.setCurrent(config['current'])

        self._nextSource = None # used in self._handleSourceChanged

        # Initialize Phonon        
        self.mediaObject = phonon.MediaObject()
        self.mediaObject.aboutToFinish.connect(self._handleAboutToFinish)
        self.mediaObject.currentSourceChanged.connect(self._handleSourceChanged)
        self.audioOutput = phonon.AudioOutput(phonon.MusicCategory)
        phonon.createPath(self.mediaObject,self.audioOutput)
    
    def current(self):
        """Return the offset of the current song or None if there is no current song."""
        if self.playlist.current is None:
            return None
        else: return self.playlist.current.offset()
    
    # Insert etc. are handled by the PlaylistModel
    def insertIntoPlaylist(self,pos,paths): pass
    def move(self,fromOffset,toOffset): pass
    
    def removeFromPlaylist(self,begin,end):
        if self.playlist.current is None:
            self.setState(player.STOP)
        
    def state(self):
        """Return the current state (one of player.STOP, player.PLAY, player.PAUSE)."""
        return {
            phonon.LoadingState: player.STOP,
            phonon.StoppedState: player.STOP,
            phonon.PlayingState: player.PLAY,
            phonon.BufferingState: player.PLAY,
            phonon.PausedState: player.PAUSE,
            phonon.ErrorState: player.STOP
        }[self.mediaObject.state()]
        
    def setState(self, state):
        if state == player.STOP:
            self.setCurrentSong(None)
            self.mediaObject.stop()
        elif state == player.PLAY:
            self.mediaObject.play()
        else: self.mediaObject.pause()
     
    def setVolume(self, volume):
        assert type(volume) == int and 0 <= volume <= 100
        self.audioOutput.setVolume(volume / 100)
    
    def setCurrentSong(self, offset):
        if offset != self.current():
            self.playlist.setCurrent(offset)
            if offset >= 0:
                source = phonon.MediaSource(self._getPath(offset))
                self.mediaObject.setCurrentSource(source)
                self.setState(player.PLAY)
            else:
                self.setState(player.STOP)
    
    def setElapsed(self, seconds):
        self.mediaObject.seek(int(seconds * 1000))
    
    def nextSong(self):
        if self.state() != player.STOP and self.current() < self.playlist.root.fileCount() - 1:
            self.setCurrentSong(self.current()+1)
    
    def previousSong(self):
        if self.state() != player.STOP and self.current() > 0:
            self.setCurrentSong(self.current()-1)
    
    def _handleAboutToFinish(self):
        if self.current() < self.playlist.root.fileCount() - 1:
            self._nextSource = phonon.MediaSource(self._getPath(self.current()+1))
            self.mediaObject.enqueue(self._nextSource)
            
    def _handleSourceChanged(self,newSource):
        if newSource == self._nextSource:
            self.playlist.setCurrent(self.current() + 1)
            self._nextSource = None
    
    def _getPath(self,offset):
        """Return the absolute path of the file at the given offset."""
        return utils.absPath(self.playlist.root.fileAtOffset(offset).element.path)
    
    def config(self):
        return []
    
    @classmethod
    def configurationWidget(cls, profile = None):
        return None
        
    def __str__(self):
        return "PhononAudioBackend({})".format(self.name)

    
def enable():
    player.profileConf.addClass(PhononPlayerBackend)

def disable():
    player.profileConf.removeClass(PhononPlayerBackend)
    
    
def defaultStorage():
    return {"SECTION:phonon": {
            "current": None,
            "playlist": ""
        }}
