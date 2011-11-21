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

from omg import player, config, logging, database as db, models
from omg.utils import relPath, absPath
from omg.models import playlist

import mpd, queue, itertools

logger = logging.getLogger("omg.plugins.mpd")

CONNECTION_TIMEOUT = 5 # time in seconds before an initial connection to MPD is given up
POLLING_INTERVAL = 600 # milliseconds between two MPD polls
MPD_STATES = { 'play': player.PLAY, 'stop': player.STOP, 'pause': player.PAUSE}


default_data = {'host' : 'localhost', 'port': '6600', 'password': ''}
class MPDThread(QtCore.QThread):
    
    changeFromMPD = QtCore.pyqtSignal(str, object)
    
    def __init__(self, backend, connectionData):
        super().__init__(None)
        self.timer = QtCore.QTimer(self)
        self.moveToThread(self)
        self.timer.moveToThread(self)
        self.timer.timeout.connect(self.poll)
        self.backend = backend
        self.connectionData = connectionData
        self.playlistVersion = self.state   = \
            self.currentSong = self.elapsed = \
            self.currentSongLength = None
        self.doPolling = False
        self.seekRequest = None
    
    def _seek(self):
        if self.seekRequest is not None:
            self.client.seek(self.currentSong, self.seekRequest)
            self.seekRequest = None
        
    def _handleMainChange(self, what, how):
        logger.debug("received command {} with args {}".format(what, how))
        if what == "set_playlist":
            self.client.clear()
            for path in how:
                self.client.add(path)
            self.mpd_playlist = how
            self.playlistVersion += len(how) + 1
            
        elif what == "elapsed":
            self.seekRequest = how
            self.seekTimer.start(20)
        
        elif what == "state":
            if how == player.PLAY:
                self.client.play()
            elif how == player.PAUSE:
                self.client.pause(1)
            elif how == player.STOP:
                self.client.stop()
        
        elif what == "currentSong":
            self.client.play(how)
        
        elif what == "nextSong":
            self.client.next()
        elif what == "previousSong":
            self.client.previous()
            
        elif what == "insert":
            for position,path in how:
                self.client.addid(path, position)
                # mpd's playlist counter increases by two if addid is called somewhere else
                # than at the end
                self.playlistVersion += 1 if position == len(self.mpd_playlist) else 2
                self.mpd_playlist[position:position] = [path]
                
        elif what == "remove":
            for position, path in reversed(how):
                self.client.delete(position)
                del self.mpd_playlist[position]
            self.playlistVersion += len(how) 
    
    def _updateAttributes(self, emit = True):
        
        # fetch information from MPD
        self.mpd_status = self.client.status()
        
        # check for a playlist change
        playlistVersion = int(self.mpd_status["playlist"])
        if playlistVersion != self.playlistVersion:
            logger.debug("detected new plVersion: {}-->{}".format(self.playlistVersion, playlistVersion))
            self.playlistVersion = playlistVersion
            self.mpd_playlist = [x["file"] for x in self.client.playlistinfo()]
            if emit:
                self.changeFromMPD.emit('playlist', self.mpd_playlist)

        # check if current song has changed. If so, also update length of current
        # song
        try:
            currentSong = int(self.mpd_status["song"])
        except KeyError:
            currentSong = -1
        if currentSong != self.currentSong:
            self.currentSong = currentSong
            if currentSong != -1:
                self.mpd_current = self.client.currentsong()
                self.currentSongLength = int(self.mpd_current["time"])
            else:
                self.currentSongLength = 0 # no current song
            if emit:
                self.changeFromMPD.emit('currentSong', self.currentSong)
             
        # check for a change of playing state
        state = MPD_STATES[self.mpd_status["state"]]
        if emit and state != self.state:
            self.changeFromMPD.emit('state', state)
        self.state = state
        
        # check if elapsed time has changed
        if state != player.STOP:
            elapsed = float(self.mpd_status['elapsed'])
            if emit and elapsed != self.elapsed:
                self.changeFromMPD.emit('elapsed', elapsed)
            self.elapsed = elapsed
            
        
    def run(self):
        # connect to MPD
        self.client = mpd.MPDClient()
        self.client.connect(host = self.connectionData['host'],
                            port = self.connectionData['port'],
                            timeout = CONNECTION_TIMEOUT)
        # obtain initial playlist / current song status
        
        self._updateAttributes(emit = False)
        self.changeFromMPD.emit('init_done',
            (self.mpd_playlist, self.currentSong, self.currentSongLength, self.elapsed, self.state))

        # start event loop for polling
        self.timer.start(POLLING_INTERVAL)
        self.doPolling = True
        
        self.seekTimer = QtCore.QTimer(self)
        self.seekTimer.setSingleShot(True)
        self.seekTimer.timeout.connect(self._seek)
        self.exec_()
        
    def poll(self):
        if self.doPolling:
            logger.debug("MPD thread is polling")
            self._updateAttributes()

class MPDPlayerBackend(player.PlayerBackend):
    
    changeFromMain = QtCore.pyqtSignal(str, object)
    
    def __init__(self, name):
        super().__init__(name)
        self.playlist = playlist.Playlist(self)
        try:
            data = config.storage.mpd.profiles[self.name]
        except KeyError:
            logger.warning("no MPD config found for profile {} - using default".format(self.name))
            data = default_data
        self.mpdthread = MPDThread(self, data)
        self.mpdthread.changeFromMPD.connect(self._handleMPDChange, Qt.QueuedConnection)
        self.changeFromMain.connect(self.mpdthread._handleMainChange)
        self.currentSongChanged.connect(self.playlist.setCurrent)
        self.mpdthread.start()
        self._numFrontends = 0
        
    @QtCore.pyqtSlot(str, object)
    def _handleMPDChange(self, what, how):
        if what == 'init_done':
            self.paths, self.currentSong, self.currentSongLength, self.elapsed, self.state = how
            self.playlist.updateFromPathList(self.paths)
            if self.currentSong != -1:
                self.playlist.setCurrent(self.currentSong)
            self.connectionState = player.CONNECTED
            self.connectionStateChanged.emit(player.CONNECTED)
            self.stack.clear()
        
        elif what == 'elapsed':
            self.elapsed = how
            self.elapsedChanged.emit(how, self.currentSongLength)
            
        elif what == 'state':
            self.state = how
            self.stateChanged.emit(how)
            
        elif what == 'currentSong':
            self.currentSong = how
            self.currentSongChanged.emit(how)
        else:
            print('WHAT? {}'.format(what))
                    
    def setElapsed(self, time):
        self.changeFromMain.emit('elapsed', time)
 
    def setState(self, state):
        self.changeFromMain.emit("state", state)
    
    def setCurrentSong(self, index):
        self.changeFromMain.emit("currentSong", index)
    
    def _setPlaylist(self, paths):
        super()._setPlaylist(paths)
        self.changeFromMain.emit('set_playlist', paths)
    
    def _insertIntoPlaylist(self, insertions):
        super()._insertIntoPlaylist(insertions)
        self.changeFromMain.emit('insert', insertions)
    
    def _removeFromPlaylist(self, removals):
        super()._removeFromPlaylist(removals)
        self.changeFromMain.emit('remove', removals)
        
    def nextSong(self):
        self.changeFromMain.emit('nextSong', None)
    
    def previousSong(self):
        self.changeFromMain.emit('previousSong', None)
    
    def registerFrontend(self, obj):
        self._numFrontends += 1
        if self._numFrontends == 1:
            logger.debug('frontend {} registered at {} -- starting poll'.format(obj, self))
            self.mpdthread.doPolling = True
    
    def unregisterFrontend(self, obj):
        self._numFrontends -= 1
        if self._numFrontends == 0:
            logger.debug('frontend {} deregistered at {} -- stopping poll'.format(obj, self))
            self.mpdthread.doPolling = False
    
    @staticmethod
    def configWidget(profile = None):
        """Return a config widget, initialized with the data of the given *profile*."""
        return MPDConfigWidget(None, profile)
        
    def __str__(self):
        return "MPDPlayerBackend({})".format(self.name)

class MPDConfigWidget(QtGui.QWidget):
    def __init__(self, parent = None, profile = None):
        super().__init__(parent)
        layout = QtGui.QGridLayout(self)
        layout.addWidget(QtGui.QLabel(self.tr("Host:"), self), 0, 0, Qt.AlignRight)
        self.hostEdit = QtGui.QLineEdit(self)
        layout.addWidget(self.hostEdit, 0, 1)
        
        layout.addWidget(QtGui.QLabel(self.tr("Port:"), self), 1, 0, Qt.AlignRight)
        self.portEdit = QtGui.QLineEdit(self)
        self.portEdit.setValidator(QtGui.QIntValidator(0, 65535, self))
        layout.addWidget(self.portEdit, 1, 1)
        
        layout.addWidget(QtGui.QLabel(self.tr("Password:"), self), 2, 0, Qt.AlignRight)
        self.passwordEdit = QtGui.QLineEdit(self)
        layout.addWidget(self.passwordEdit, 2, 1)
        
        self.setProfile(profile)
    
    def setProfile(self, profile):
        if profile is not None and profile in config.storage.mpd.profiles:
            data = config.storage.mpd.profiles[profile]
        else:
            data = default_data
        self.hostEdit.setText(data['host'])
        self.portEdit.setText(str(data['port']))
        self.passwordEdit.setText(data['password'])
    
    def storeProfile(self, profile):
        host = self.hostEdit.text()
        port = self.portEdit.text()
        password = self.passwordEdit.text()
        profiles = config.storage.mpd.profiles
        profiles[profile] = {'host': host, 'port': port, 'password': password}
        config.storage.mpd.profiles = profiles
        
        
def defaultStorage():
    return {"mpd":
            {'profiles': ({},) } }

def _handleNewProfile(name):
    if player.configuredBackends[name] == 'mpd':
        logger.debug("adding MPD backend {}".format(name))
        profiles = config.storage.mpd.profiles.copy()
        profiles[name] = default_data.copy()
        config.storage.mpd.profiles = profiles
    else:
        logger.debug("MPD backend ignoring profile add: {}, backend {}".format(name, player.configuredBackends[name]))
def _handleRenameProfile(old, new):
    logger.debug("rename profile request {} {}".format(old, new))
    if player.configuredBackends[new] == 'mpd':
        assert old in config.storage.mpd.profiles
        config.storage.mpd.profiles = {
            (new if name==old else name): conf for name,conf in config.storage.mpd.profiles.items()}
def _handleRemoveProfile(name):
    if name in config.storage.mpd.profiles:
        profiles = config.storage.mpd.profiles 
        del profiles[name]
        config.storage.mpd.profiles = profiles

def enable():
    player.backendClasses['mpd'] = MPDPlayerBackend
    player.notifier.profileAdded.connect(_handleNewProfile)
    player.notifier.profileRenamed.connect(_handleRenameProfile)
    player.notifier.profileRemoved.connect(_handleRemoveProfile)
    logger.debug("mpd plugin enabled -- added 'mpd' playerClass")

def disable():
    del player.backendClasses['mpd']