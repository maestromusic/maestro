# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

import urllib.parse
import os.path

from PyQt4 import QtCore
try:
    from PyQt4.phonon import Phonon as phonon
except ImportError as e:
    raise ImportError("PyQt4-phonon is not installed.")

from ... import player, profiles, utils
from ...filebackends.filesystem import FileURL
from ...filebackends.stream import HTTPStreamURL
from ...models import playlist
        
translate = QtCore.QCoreApplication.translate


def enable():
    profileType = profiles.ProfileType('phonon',
                                       translate("PhononPlayerBackend","Phonon"),
                                       PhononPlayerBackend)
    player.profileCategory.addType(profileType)
    # addType loads stored profiles of this type from storage
    # If no profile was loaded, create a default one.
    return
    if len(player.profileCategory.profiles(profileType)) == 0:
        name = translate("PhononPlayerBackend", "Local playback (Phonon)")
        if player.profileCategory.get(name) is None:
            player.profileCategory.addProfile(name, profileType)

def disable():
    player.profileCategory.removeType('phonon')
    
def defaultStorage():
    return {"SECTION:phonon": {
            "current": None,
            "playlist": ""
        }}
    

class PhononPlayerBackend(player.PlayerBackend):
    def __init__(self, name, type, state):
        super().__init__(name, type, state)
        self._flags = 0
        
        # The list of paths in the playlist and the current song are stored directly in the model's tree
        self.playlist = playlist.PlaylistModel(self)
        
        # Initialize Phonon        
        self.mediaObject = phonon.MediaObject()
        self.mediaObject.aboutToFinish.connect(self._handleAboutToFinish)
        self.mediaObject.currentSourceChanged.connect(self._handleSourceChanged)
        self.mediaObject.setTickInterval(200)
        self.mediaObject.tick.connect(self._handleTick)
        self.audioOutput = phonon.AudioOutput(phonon.MusicCategory)
        phonon.createPath(self.mediaObject,self.audioOutput)
        
        if state is None:
            state = {}
        if 'playlist' in state:
            if self.playlist.initFromWrapperString(state['playlist']):
                self.setCurrent(state.get('current', None), play=False)
        self._flags = state.get('flags', 0)

        self._nextSource = None # used in self._handleSourceChanged
        self.connectionState = player.CONNECTED
    
    # Insert etc. are handled by the PlaylistModel. We only have to change the state if necessary.
    def insertIntoPlaylist(self, pos, urls):
        urls = list(urls)
        for i, url in enumerate(urls):
            if not (isinstance(url, FileURL) or isinstance(url, HTTPStreamURL)):
                raise player.InsertError("URL type {} not supported".format(type(url)))
            if isinstance(url, FileURL) and not os.path.exists(url.absPath):
                raise player.InsertError(self.tr("Can not play '{}': File does not exist.")
                                         .format(url), urls[:i])
             
    def move(self,fromOffset,toOffset): pass
    
    def removeFromPlaylist(self,begin,end):
        if self.playlist.current is None:
            self.setState(player.STOP)
            
    def setPlaylist(self, urls):
        if self.playlist.current is None:
            self.setState(player.STOP)
    
    phononToStateMap = { phonon.LoadingState: player.STOP,
                         phonon.StoppedState: player.STOP,
                         phonon.PlayingState: player.PLAY,
                         phonon.BufferingState: player.PLAY,
                         phonon.PausedState: player.PAUSE,
                         phonon.ErrorState: player.STOP }
    def state(self):
        """Return the current state (one of player.STOP, player.PLAY, player.PAUSE)."""
        return self.phononToStateMap[self.mediaObject.state()]
        
    def setState(self, state):
        if state != self.state():
            if state == player.STOP:
                self.mediaObject.stop()
            elif state == player.PLAY:
                if self.current() is None:
                    self.setCurrent(0) # this starts playing
                else: self.mediaObject.play()
                QtCore.QTimer.singleShot(2000, self.checkPlaying)
            else: self.mediaObject.pause()
            self.stateChanged.emit(state)
    
    def checkPlaying(self):
        if self.state() != player.PLAY:
            from omg.gui.dialogs import warning
            warning(self.tr("Error Playing Song"),
                    self.tr("Phonon could not play back the selected file."))
            self.stateChanged.emit(self.state())
    
    def volume(self):
        return int(self.audioOutput.volume() * 100)
    
    def setVolume(self, volume):
        assert type(volume) == int and 0 <= volume <= 100
        self.audioOutput.setVolume(volume / 100)
        self.volumeChanged.emit(volume)
    
    def current(self):
        return self.playlist.current
    
    def currentOffset(self):
        if self.playlist.current is None:
            return None
        else: return self.playlist.current.offset()
    
    def setCurrent(self, offset, play=True):
        if offset != self.currentOffset():
            self.playlist.setCurrent(offset)
            if offset is not None:
                source = phonon.MediaSource(self._getPath(offset))
                self.mediaObject.setCurrentSource(source)
                if play:
                    self.setState(player.PLAY)
            else:
                self.setState(player.STOP)
            self.currentChanged.emit(offset)
        elif offset is not None \
                and self._getPath(offset) != self.mediaObject.currentSource().url().toString():
            source = phonon.MediaSource(self._getPath(offset))
            self.mediaObject.setCurrentSource(source)
            if play:
                self.mediaObject.play()
    
    def elapsed(self):
        return self.mediaObject.currentTime() / 1000
    
    def setElapsed(self, seconds):
        self.mediaObject.seek(int(seconds * 1000))
        self.elapsedChanged.emit(seconds)
    
    def skipForward(self):
        if self.state() != player.STOP and self.currentOffset() < self.playlist.root.fileCount() - 1:
            self.setCurrent(self.currentOffset()+1)
    
    def skipBackward(self):
        if self.state() != player.STOP and self.currentOffset() > 0:
            self.setCurrent(self.currentOffset()-1)
    
    def _handleAboutToFinish(self):
        fileCount = self.playlist.root.fileCount()
        if self.currentOffset() < fileCount - 1:
            self._nextSource = phonon.MediaSource(self._getPath(self.currentOffset()+1))
            self._nextOffset = self.currentOffset()+1
            self.mediaObject.enqueue(self._nextSource)
        elif self.isRepeating() and fileCount > 0: 
            self._nextSource = phonon.MediaSource(self._getPath(0))
            self._nextOffset = 0
            self.mediaObject.enqueue(self._nextSource)
            
    def _handleSourceChanged(self, newSource):
        if newSource == self._nextSource:
            self.playlist.setCurrent(self._nextOffset)
            self.currentChanged.emit(self.currentOffset())
            self._nextSource = None
            self._nextOffset = None
        
    def _handleTick(self,pos):
        self.elapsedChanged.emit(pos / 1000)
    
    def _getPath(self, offset):
        """Return the absolute path of the file at the given offset."""
        url = self.playlist.root.fileAtOffset(offset).element.url
        if isinstance(url, FileURL):
            return utils.absPath(url.path)
        if isinstance(url, HTTPStreamURL):
            return url.toQUrl()
        raise ValueError("Phonon can not play file {} of URL type {}".format(url, type(url)))
    
    def save(self):
        result = {}
        playlist = self.playlist.wrapperString()
        if len(playlist):
            result['playlist'] = playlist
        if self.playlist.current is not None:
            result['current'] = self.playlist.current.offset()
        if self._flags != 0:
            result['flags'] = self._flags
        return result
        
    def __str__(self):
        return "PhononAudioBackend({})".format(self.name)
    
    def flags(self):
        return self._flags
    
    def setFlags(self, flags):
        if flags != self._flags:
            self._flags = flags
            self.flagsChanged.emit(flags)
