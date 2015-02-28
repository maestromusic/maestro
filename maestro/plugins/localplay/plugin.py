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

from PyQt5 import QtCore, QtMultimedia, QtWidgets

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
        # To increase performance the QMediaPlayer and QMediaPlaylist are not created until it is needed.
        self.playlist = playlist.PlaylistModel(self)
        self.qtPlaylist = self.qtPlayer = None
            
        if state is None:
            state = {}
        self._initState = state
        self._numFrontends = 0
        
    def registerFrontend(self, frontend):
        self._numFrontends += 1
        if self.qtPlayer is None:
            # Initialize
            state = self._initState
            self._initState = None
            self.qtPlaylist = QtMultimedia.QMediaPlaylist()
            self.qtPlayer = QtMultimedia.QMediaPlayer()
            self.qtPlayer.setPlaylist(self.qtPlaylist)
            self.qtPlaylist.currentIndexChanged.connect(self.handleIndexChanged)
            self.qtPlayer.setNotifyInterval(1000)
            self.qtPlayer.error.connect(self.handlePlayerError)
            self.qtPlayer.positionChanged.connect(lambda pos: self.elapsedChanged.emit(pos / 1000))
            if 'playlist' in state:
                if self.playlist.initFromWrapperString(state['playlist']):
                    self.qtPlaylist.addMedia([QtMultimedia.QMediaContent(file.element.url.toQUrl())
                                              for file in self.playlist.root.getAllFiles()])
                    self.setCurrent(state.get('current', None), play=False)
            self.setVolume(state.get('volume', 100))
            self.connectionState = player.ConnectionState.Connected
            self.connectionStateChanged.emit(player.ConnectionState.Connected)

    def unregisterFrontend(self, frontend):
        self._numFrontends -= 1

    def insertIntoPlaylist(self, pos, urls):
        urls = list(urls)
        for i, url in enumerate(urls):
            if url.scheme != 'file':
                raise player.InsertError('URLs of type "{}" not supported by local player'.format(url.scheme))
            elif not os.path.exists(url.path):
                raise player.InsertError(self.tr('Cannot play "{}": File does not exist')
                                         .format(url.path), urls[:i])
            elif not self.qtPlaylist.insertMedia(pos + i, QtMultimedia.QMediaContent(url.toQUrl())):
                raise player.InsertError('Cannot play {}'.format(url.path))

    def removeFromPlaylist(self, begin, end):
        self.qtPlaylist.removeMedia(begin, end - 1)

    def move(self, fromOffset, toOffset):
        if fromOffset == toOffset:
            return
        fromUrl = self.playlist.root.fileAtOffset(fromOffset).element.url
        self.removeFromPlaylist(fromOffset, fromOffset + 1)
        self.insertIntoPlaylist(toOffset, [fromUrl])

    def setPlaylist(self, urls):
        self.stop()
        self.playlist.clearCurrent()
        self.currentChanged.emit(None)
        self.qtPlaylist.clear()
        if len(urls):
            self.qtPlaylist.addMedia([QtMultimedia.QMediaContent(url.toQUrl()) for url in urls])

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
        if state != self.state():
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
        else: return self.playlist.current.offset()
    
    def setCurrent(self, offset, play=True):
        if offset != self.currentOffset():
            self.playlist.setCurrent(offset)
            if offset is not None and offset < self.qtPlaylist.mediaCount():
                self.qtPlaylist.setCurrentIndex(offset)
                if play:
                    self.play()
            else:
                self.setState(player.PlayState.Stop)
            self.currentChanged.emit(offset)
        elif play and self.state() != player.PlayState.Play:
            self.play()
    
    def elapsed(self):
        return self.qtPlayer.position() / 1000
    
    def setElapsed(self, seconds):
        self.qtPlayer.setPosition(int(seconds * 1000))
        self.elapsedChanged.emit(seconds)
    
    def skipForward(self):
        self.qtPlaylist.next()
        self.currentChanged.emit(self.qtPlaylist.currentIndex())
    
    def skipBackward(self):
        self.qtPlaylist.previous()
        self.currentChanged.emit(self.qtPlaylist.currentIndex())
    
    def nextOffset(self):
        """Get the next offset that will be played."""
        if not self.playlist.root.hasContents():
            return None
        if self.currentOffset() is None:
            return 0
        elif self.current().nextLeaf() is not None:
            return self.currentOffset() + 1
        return None

    def handleIndexChanged(self, index):
        self.playlist.setCurrent(index)
        self.currentChanged.emit(index)

    def handlePlayerError(self, error):
        if error == self.qtPlayer.FormatError:
            from maestro.gui.dialogs import warning
            warning(self.tr('Playback Failed'), self.tr('Playback failed: format error'))
            self.stop()
        else:
            print('unknown player error {}'.format(error))

    def save(self):
        if self._initState is not None:
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

    @classmethod
    def configurationWidget(cls, profile, parent):
        return None

    def __str__(self):
        return "LocalPlayerBackend({})".format(self.name)
