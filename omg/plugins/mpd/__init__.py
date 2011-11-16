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

import mpd, threading, itertools

logger = logging.getLogger("omg.plugins.mpd")

MPD_STATES = { 'play': player.PLAY, 'stop': player.STOP, 'pause': player.PAUSE}

default_data = {'host' : 'localhost', 'port': '6600', 'password': ''}
class MPDThread(QtCore.QThread):
    def __init__(self, parent):
        super().__init__(parent)
        self.start()
    
    def run(self):
        self.exec_()

class MPDPlayerBackend(player.PlayerBackend):
    
    pathlistChanged = QtCore.pyqtSignal(list)
    def __init__(self, name):
        super().__init__(name)

        self.playlistVersion = -1
        self.playlist = playlist.BasicPlaylist()
        
        self.mpdthread = MPDThread(self)
        self.timer = QtCore.QTimer()
        
        self.currentSongChanged.connect(self.playlist.setCurrent)
        self.moveToThread(self.mpdthread)
        self.playlist.filesDropped.connect(self.insertIntoPlaylist, Qt.QueuedConnection)
        self.pathlistChanged.connect(self.playlist.updateFromPathList, Qt.QueuedConnection)
        self.timer.timeout.connect(self.poll)
        
        self.consecutiveConnectionFailures = 0
        self._frontendLock = threading.Lock()
        self._numFrontends = 0
    
    def _setConnectionState(self, state):
        if self.connectionState != state:
            self.connectionStateChanged.emit(state)
        self.connectionState = state
        
    def ensureConnection(self):
        if self.connectionState == player.CONNECTED:
            return True
        if self.connectionState == player.DISCONNECTED and self.consecutiveConnectionFailures > 4:
            return False
        try:
            data = config.storage.mpd.profiles[self.name]
        except KeyError:
            logger.warning("no MPD config found for profile {} - using default".format(self.name))
            data = default_data
        self.client = mpd.MPDClient()
        try:
            self._setConnectionState(player.CONNECTING)
            self.client.connect(data["host"], data["port"], timeout = 3)
            self.consecutiveConnectionFailures = 0
            self._setConnectionState(player.CONNECTED)
            return True
        except Exception as e:
            logger.warning('could not connect profile {}: {}'.format(self.name, e))
            if self.connectionState == player.CONNECTED:
                self._setConnectionState(player.DISCONNECTED)
            self.consecutiveConnectionFailures += 1
            self.delayConnectionAttempt()
            return False
    
    def delayConnectionAttempt(self):
        if self.consecutiveConnectionFailures <= 4:
            self.thread().sleep(2**self.consecutiveConnectionFailures)
        else:
            self._setConnectionState(player.DISCONNECTED)
            
    def poll(self):
        if not self.ensureConnection():
            return
        status = self.client.status()
        state = MPD_STATES[status["state"]]
        if state != self.state:
            self.stateChanged.emit(state)
        self.state = state
        
        playlistVersion = int(status["playlist"])
        if playlistVersion != self.playlistVersion:
            self.updatePlaylist()
        self.playlistVersion = playlistVersion
        
        try:
            currentSong = int(status["song"])
        except KeyError:
            currentSong = -1
        if currentSong != self.currentSong:
            mpd_current = self.client.currentsong()
            if "time" in mpd_current:
                self.currentSongLength = int(mpd_current["time"])
            else:
                self.currentSongLength = 0
            self.currentSongChanged.emit(currentSong)
        self.currentSong = currentSong

        try:
            elapsed = float(status["elapsed"])
        except KeyError:
            elapsed = 0
        if elapsed != self.elapsed:
            self.elapsedChanged.emit(elapsed, self.currentSongLength)
        self.elapsed = elapsed
                
        self.mpd_status = status

    def updatePlaylist(self):
        if not self.ensureConnection():
            return
        self.mpd_playlist = self.client.playlistinfo()
        paths = []
        for file in self.mpd_playlist:
            paths.append(file["file"])
        self.pathlistChanged.emit(paths)
    
    @QtCore.pyqtSlot(float)        
    def setElapsed(self, time):
        if not self.ensureConnection():
            return
        logger.debug("mpd -- set Elapsed called")
        self.client.seek(self.currentSong, time)
 
    @QtCore.pyqtSlot(int)
    def setState(self, state):
        if not self.ensureConnection():
            return
        logger.debug("mpd -- set State {} called".format(state))
        if state == player.PLAY:
            self.client.play()
        elif state == player.PAUSE:
            self.client.pause()
        elif state == player.STOP:
            self.client.stop()       
    
    @QtCore.pyqtSlot(int)
    def setCurrentSong(self, index):
        if not self.ensureConnection():
            return
        self.client.play(index)
    
    @QtCore.pyqtSlot(list)
    def setPlaylist(self, paths):
        if not self.ensureConnection():
            return
    
    @QtCore.pyqtSlot(int, list)
    def insertIntoPlaylist(self, position, paths):
        if not self.ensureConnection():
            return
        firstIndex = len(self.mpd_playlist)
        for path in paths:
            self.client.add(path)
        self.client.move("{}:{}".format(firstIndex, firstIndex + len(paths)), str(position))
    
    @QtCore.pyqtSlot()
    def next(self):
        if not self.ensureConnection():
            return
        self.client.next()
    
    @QtCore.pyqtSlot()
    def previous(self):
        if not self.ensureConnection():
            return
        self.client.previous()
    
    def registerFrontend(self, obj):
        with self._frontendLock:
            self._numFrontends += 1
            if self._numFrontends == 1:
                logger.debug('frontend {} registered at {} -- starting poll'.format(obj, self))
                self.timer.start(500)
            if self.consecutiveConnectionFailures >= 5:
                self.consecutiveConnectionFailures = 0
    
    def unregisterFrontend(self, obj):
        with self._frontendLock:
            self._numFrontends -= 1
            if self._numFrontends == 0:
                logger.debug('frontend {} deregistered at {} -- stopping poll'.format(obj, self))
                self.timer.stop()
    
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