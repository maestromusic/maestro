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

import os.path

from PyQt5 import QtCore, QtMultimedia

from maestro import player, profiles
from maestro.models import playlist
        
translate = QtCore.QCoreApplication.translate


def enable():
    profileType = profiles.ProfileType('localplay',
                                       translate('LocalPlayBackend','Local Playback'),
                                       LocalPlayerBackend)
    player.profileCategory.addType(profileType)
    # addType loads stored profiles of this type from storage
    # If no profile was loaded, create a default one.
    if len(player.profileCategory.profiles(profileType)) == 0:
        name = translate("LocalPlayBackend", 'Local playback')
        if player.profileCategory.get(name) is None:
            player.profileCategory.addProfile(name, profileType)


def disable():
    player.profileCategory.removeType('localplay')
    
    
def defaultStorage():
    return {"localplay": {
            "current": None,
            "playlist": ""
        }}
    

class LocalPlayerBackend(player.PlayerBackend):
    
    def __init__(self, name, type, state):
        super().__init__(name, type, state)
        
        # Phonon backends are created when the application starts (profiles!).
        # To increase performance the mediaObject is not created until it is needed.
        self.player = None
        
        # The list of paths in the playlist and the current song are stored directly in the model's tree
        self.playlist = playlist.PlaylistModel(self)
            
        if state is None:
            state = {}
        self._initState = state
        self._numFrontends = 0
        
    def registerFrontend(self, frontend):
        self._numFrontends += 1
        if self._numFrontends == 1 and hasattr(self, '_initState'):
            # Initialize Phonon
            state = self._initState
            del self._initState
            self.player = QtMultimedia.QMediaPlayer()
            self.player.mediaChanged.connect(self._handleMediaChanged)
            self.player.setNotifyInterval(1000)
            self.player.positionChanged.connect(self._handleTick)
            if 'playlist' in state:
                if self.playlist.initFromWrapperString(state['playlist']):
                    self.setCurrent(state.get('current', None), play=False)
            self.setVolume(state.get('volume', 100))
            self._nextSource = None # used in self._handleMediaChanged
            self.connectionState = player.ConnectionState.Connected
            self.connectionStateChanged.emit(player.ConnectionState.Connected)
    
    def unregisterFrontend(self, frontend):
        self._numFrontends -= 1
    
    # Insert etc. are handled by the PlaylistModel.
    def insertIntoPlaylist(self, pos, urls):
        urls = list(urls)
        for i, url in enumerate(urls):
            if url.scheme != 'file':
                raise player.InsertError("URL type {} not supported".format(type(url)))
            elif not os.path.exists(url.path):
                raise player.InsertError(self.tr("Cannot play '{}': File does not exist.")
                                         .format(url), urls[:i])
    
    def removeFromPlaylist(self, begin, end):
        if self.playlist.current is None:
            self.setState(player.PlayState.Stop)
            
    def setPlaylist(self, urls):
        self.playlist.current = None
        self.setState(player.PlayState.Stop)

    def state(self):
        """Return the current state"""
        state = self.player.state()
        if state == self.player.StoppedState:
            return player.PlayState.Stop
        elif state == self.player.PausedState:
            return player.PlayState.Pause
        else:
            return player.PlayState.Play
        
    def setState(self, state: player.PlayState):
        if state != self.state():
            if state is player.PlayState.Stop:
                self.player.stop()
            elif state == player.PlayState.Play:
                if self.current() is None:
                    offset = self._nextOffset()
                    if offset is not None:
                        self.setCurrent(offset) # this starts playing
                else:
                    self.player.play()
            else:
                self.player.pause()
            self.stateChanged.emit(state)

    def volume(self):
        return self.player.volume()
    
    def setVolume(self, volume):
        self.player.setVolume(volume)
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
                media = QtMultimedia.QMediaContent(QtCore.QUrl(self._getPath(offset)))
                self.player.setMedia(media)
                if play:
                    self.play()
            else:
                self.setState(player.PlayState.Stop)
            self.currentChanged.emit(offset)
        elif offset is not None \
                and self._getPath(offset) != self.player.currentMedia().url().toString():
            media = QtMultimedia.QMediaContent(QtCore.QUrl(self._getPath(offset)))
            self.player.setMedia(media)
            if play:
                self.play()
    
    def elapsed(self):
        return self.player.position() / 1000
    
    def setElapsed(self, seconds):
        self.player.setPosition(int(seconds * 1000))
        self.elapsedChanged.emit(seconds)
    
    def skipForward(self):
        if self.state() is not player.PlayState.Stop:
            # This may be None in which case playback is stopped
            self.setCurrent(self._nextOffset())
    
    def skipBackward(self):
        if self.state() is not player.PlayState.Stop:
            if self.currentOffset() > 0:
                self.setCurrent(self.currentOffset()-1)
    
    def _nextOffset(self):
        """Get the next offset that will be played."""
        if not self.playlist.root.hasContents():
            return None
        
        if self.currentOffset() is None:
            return 0
        elif self.current().nextLeaf() is not None:
            return self.currentOffset()+1
        return None

    def _handleMediaChanged(self, media):
        if media is None:
            self._no = self._nextOffset()
            if self._no is not None:
                self._nextSource = QtMultimedia.QMediaContent(QtCore.QUrl(self._getPath(self._no)))
                self.player.setMedia(self._nextSource)
                self.player.play()
        if media == self._nextSource:
            self.playlist.setCurrent(self._no)
            self.currentChanged.emit(self.currentOffset())
            self._nextSource = None
            self._no = None
        
    def _handleTick(self, pos):
        self.elapsedChanged.emit(pos / 1000)
    
    def _getPath(self, offset):
        """Return the absolute path of the file at the given offset."""
        url = self.playlist.root.fileAtOffset(offset).element.url
        if url.scheme == 'file':
            return url.path
        raise ValueError("Phonon can not play file {} of URL type {}".format(url, type(url)))
    
    def save(self):
        if hasattr(self, "_initState"):
            # localplayback was never activated -> return previous state
            return self._initState
        result = {}
        playlist = self.playlist.wrapperString()
        if len(playlist):
            result['playlist'] = playlist
        if self.playlist.current is not None:
            result['current'] = self.playlist.current.offset()
        if self.volume() != 100:
            result['volume'] = self.volume()
        return result
        
    def __str__(self):
        return "LocalPlayerBackend({})".format(self.name)
