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
from maestro.widgets.playlist import model

translate = QtCore.QCoreApplication.translate


# noinspection PyTypeChecker,PyArgumentList
def enable():
    playerProfileCategory = profiles.category('playback')
    profileType = profiles.ProfileType(
        category=playerProfileCategory,
        name='localplay',
        title=translate('LocalPlayBackend', 'Local Playback'),
        profileClass=LocalPlayerBackend
    )
    playerProfileCategory.addType(profileType)
    # addType loads stored profiles of this type from storage
    # If no profile was loaded, create a default one.
    if len(playerProfileCategory.profiles(profileType)) == 0:
        name = translate('LocalPlayBackend', 'Local playback')
        if playerProfileCategory.get(name) is None:
            playerProfileCategory.addProfile(name, profileType)


def disable():
    profiles.category('playback').removeType('localplay')
    
    
def defaultStorage():
    return {"localplay": {
            "current": None,
            "playlist": ""
        }}
    

class LocalPlayerBackend(player.PlayerBackend):
    """Player backend implementation using a QtMultimedia.QMediaPlayer for local playback.
    """
    def __init__(self, name, category, type, state):
        super().__init__(name, category, type, state)
        self.playlist = model.PlaylistModel(self)
        self.qtPlayer = None
        if state is None:
            state = {}
        self._initState = state
        
    def registerFrontend(self, frontend):
        super().registerFrontend(frontend)
        if self.qtPlayer is None:
            # Initialize on first frontend registering
            state = self._initState
            self._initState = None
            self.qtPlayer = QtMultimedia.QMediaPlayer()
            self.qtPlayer.setNotifyInterval(250)
            self.qtPlayer.error.connect(self.handlePlayerError)
            self.qtPlayer.mediaStatusChanged.connect(self.handleMediaStatusChanged)
            self.qtPlayer.positionChanged.connect(lambda pos: self.elapsedChanged.emit(pos / 1000))
            if 'playlist' in state:
                if self.playlist.initFromWrapperString(state['playlist']):
                    self.setCurrent(state.get('current', None), play=False)
            self.setVolume(state.get('volume', 100))
            self.connectionState = player.ConnectionState.Connected
            self.connectionStateChanged.emit(player.ConnectionState.Connected)

    def insertIntoPlaylist(self, pos, urls):
        urls = list(urls)
        for i, url in enumerate(urls):
            if url.scheme != 'file':
                raise player.InsertError('URLs of type "{}" not supported by local player'.format(url.scheme))
            elif not os.path.exists(url.path):
                raise player.InsertError(self.tr('Cannot play "{}": File does not exist')
                                         .format(url.path), urls[:i])

    def removeFromPlaylist(self, begin, end):
        self.currentChanged.emit(self.playlist.current)
        if self.playlist.current is None:
            self.stop()

    def setPlaylist(self, urls):
        self.setCurrent(None, play=False)

    def state(self):
        """Return the current state"""
        state = self.qtPlayer.state()
        if state == self.qtPlayer.StoppedState:
            return player.PlayState.Stop
        elif state == self.qtPlayer.PausedState:
            return player.PlayState.Pause
        else:
            return player.PlayState.Play
        
    def setState(self, state: player.PlayState):
        if state is player.PlayState.Stop:
            self.qtPlayer.stop()
        elif state == player.PlayState.Play:
            if self.current() is None:
                try:
                    self.setCurrent(0, play=True)
                except IndexError:
                    pass
            else:
                self.qtPlayer.play()
        else:
            self.qtPlayer.pause()
        self.stateChanged.emit(state)

    def volume(self):
        return self.qtPlayer.volume()
    
    def setVolume(self, volume):
        self.qtPlayer.setVolume(volume)
        self.volumeChanged.emit(volume)
    
    def currentOffset(self):
        if self.playlist.current is None:
            return None
        else:
            return self.playlist.current.offset()
    
    def setCurrent(self, offset, play=True):
        success = self.playlist.setCurrent(offset)
        if not success or offset is None:
            self.stop()
        else:
            self.qtPlayer.setMedia(QtMultimedia.QMediaContent(self.playlist.current.element.url.toQUrl()))
            if play and self.state() != player.PlayState.Play:
                self.play()
        self.currentChanged.emit(offset)

    def elapsed(self):
        return self.qtPlayer.position() / 1000
    
    def setElapsed(self, seconds):
        self.qtPlayer.setPosition(int(seconds * 1000))
        self.elapsedChanged.emit(seconds)
    
    def skipForward(self):
        self.setCurrent(self.nextOffset())
    
    def skipBackward(self):
        cur = self.currentOffset()
        if cur is not None and cur > 0:
            self.setCurrent(cur - 1)
    
    def nextOffset(self):
        """Get the next offset that will be played."""
        if not self.playlist.root.hasContents():
            return None
        if self.currentOffset() is None:
            return 0
        elif self.current().nextLeaf():
            return self.currentOffset() + 1

    def handlePlayerError(self, error):
        if error == self.qtPlayer.FormatError:
            from maestro.gui.dialogs import warning
            warning(self.tr('Playback Failed'), self.tr('Playback failed: format error'))
            self.stop()
        else:
            print('unknown player error {}'.format(error))

    def handleMediaStatusChanged(self, status):
        if status == QtMultimedia.QMediaPlayer.EndOfMedia:
            self.skipForward()

    def save(self):
        if self._initState is not None:
            # localplayback was never activated -> return previous state
            return self._initState
        result = {}
        playlistStr = self.playlist.wrapperString()
        if len(playlistStr):
            result['playlist'] = playlistStr
        if self.playlist.current is not None:
            result['current'] = self.playlist.current.offset()
        if self.volume() != 100:
            result['volume'] = self.volume()
        return result

    def __str__(self):
        return 'LocalPlayerBackend({})'.format(self.name)
