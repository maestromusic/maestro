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

import mpd, functools, threading

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ... import player, config, logging
from ...models import playlist
from ...player import STOP, PLAY, PAUSE


logger = logging.getLogger(__name__)


CONNECTION_TIMEOUT = 10 # time in seconds before an initial connection to MPD is given up
POLLING_INTERVAL = 200 # milliseconds between two MPD polls
MPD_STATES = { 'play': PLAY, 'stop': STOP, 'pause': PAUSE}
default_data = {'host' : 'localhost', 'port': '6600', 'password': ''}

class MPDThread(QtCore.QThread):
    """Helper class for the MPD player backend. An MPDThread communicates with
    the mpd server via the network. This is done in a distinguished thread in order
    to avoid lags in the GUI. Whenever the state of mpd changes in a way that is
    not triggered by OMG, the MPDThread will emit the *changeFromMPD* signal.
    To detect such changes, the server is polled regularly. Changes from OMG
    are handled by the *_handleMainChange* slot."""
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
            self.currentSongLength = self.volume = None
        self.doPolling = threading.Event()
        self.seekRequest = None
        self.connected = False
    
    def _seek(self):
        """Helper function to seek to a specific point of a song. We use a timer,
        self.seekTimer, to limit the number of _seek requests sent in short time
        periods, as it happens if the user pushes the seek slider. By storing the
        last seek command in self.seekRequest we ensure that the last seek is
        performed in any case."""
        if self.seekRequest is not None:
            self.client.seek(self.currentSong, self.seekRequest)
            self.seekRequest = None
        
    def _handleMainChange(self, what, how):
        """This slot is called by the main OMG program when the user requires a change.
        *what* is the name of one of the command methods of PlayerBackend, *how*
        are the corresponding arguments."""
        if what == "_setPlaylist":
            self.client.clear()
            for path in how:
                self.client.add(path)
            self.mpd_playlist = how
            self.playlistVersion += len(how) + 1
            
        elif what == "setElapsed":
            self.seekRequest = how
            self.seekTimer.start(20)
        
        elif what == "setVolume":
            self.client.setvol(how)
            
        elif what == "setState":
            if how == player.PLAY:
                self.client.play()
            elif how == player.PAUSE:
                self.client.pause(1)
            elif how == player.STOP:
                self.client.stop()
        
        elif what == "setCurrentSong":
            self.client.play(how)
        
        elif what == "nextSong":
            self.client.next()
            
        elif what == "previousSong":
            self.client.previous()
            
        elif what == "_insertIntoPlaylist":
            for position,path in how:
                self.client.addid(path, position)
                # mpd's playlist counter increases by two if addid is called somewhere else
                # than at the end
                self.playlistVersion += 1 if position == len(self.mpd_playlist) else 2
                self.mpd_playlist[position:position] = [path]
                
        elif what == "_removeFromPlaylist":
            for position, path in reversed(how):
                self.client.delete(position)
                del self.mpd_playlist[position]
            self.playlistVersion += len(how) 
        
        else:
            logger.error('Unknown command: {}'.format(what, how))
    
    
    def _handleExternalPlaylistChange(self, newVersion):
        """Helper function to handle changes in MPD's playlist from outside OMG.
        Currently, two special cases are detected: Insertion of consecutive songs,
        and removal of consecutive songs. For those cases, the messages "insert" and
        "remove", respectively, are emitted.
        In any other case, a complete playlist change message is emitted."""
        
        oldVersion = self.playlistVersion
        logger.debug("detected new plVersion: {}-->{}".format(oldVersion, newVersion))
        
        if oldVersion is None:
            # this happens only on initialization. Here we don't create an UndoCommand
            self.mpd_playlist = [x["file"] for x in self.client.playlistinfo()]
            self.playlistVersion = newVersion
            return
        
        changes = [(int(a["pos"]),a["file"]) for a in self.client.plchanges(oldVersion)]
        self.playlistVersion = newVersion
        newLength = int(self.mpd_status["playlistlength"])
        # first special case: find out if only consecutive songs were removed 
        if newLength < len(self.mpd_playlist):
            numRemoved = len(self.mpd_playlist) - newLength
            newSongsThere = list(zip(*changes))[1] if len(changes) > 0 else []
            oldSongsThere = self.mpd_playlist[-len(changes):] if len(changes) > 0 else []
            if all( a == b for a,b in zip(newSongsThere, oldSongsThere)):
                firstRemoved = newLength - len(changes)
                removed = list(enumerate(self.mpd_playlist[firstRemoved:firstRemoved+numRemoved],
                                             start = firstRemoved))
                del self.mpd_playlist[firstRemoved:firstRemoved+numRemoved]
                self.changeFromMPD.emit('remove', removed)
                return
        
        # second special case: find out if a number of consecutive songs were inserted
        if newLength > len(self.mpd_playlist):
            numInserted = newLength - len(self.mpd_playlist)
            numShifted = len(changes) - numInserted
            if numShifted == 0:
                newSongsThere = []
                oldSongsThere = []
            else:
                newSongsThere = list(zip(*changes[-numShifted:]))[1]
                oldSongsThere = self.mpd_playlist[-numShifted:]
            if all (a == b for a,b in zip(newSongsThere, oldSongsThere)):
                firstInserted = len(self.mpd_playlist) - numShifted
                insertions = changes[:numInserted]
                self.mpd_playlist[firstInserted:firstInserted] = insertions
                self.changeFromMPD.emit('insert', insertions)
                return
        
        # other cases: update self.mpd_playlist and emit a generic "playlist" change message.
        for pos, file in sorted(changes):
            if pos < len(self.mpd_playlist):
                self.mpd_playlist[pos] = file
            else:
                self.mpd_playlist.append(file)
        self.changeFromMPD.emit('playlist', self.mpd_playlist[:])
        
    def _updateAttributes(self, emit = True):
        """Get current status from MPD, update attributes of this object and emit
        messages if something has changed."""
         
        # fetch information from MPD
        self.mpd_status = self.client.status()
        
        # check for volume change
        volume = int(self.mpd_status['volume'])
        if volume != self.volume:
            self.changeFromMPD.emit('volume', volume)
            self.volume = volume
            
        # check for a playlist change
        playlistVersion = int(self.mpd_status["playlist"])
        if playlistVersion != self.playlistVersion:
            self._handleExternalPlaylistChange(playlistVersion)
            
        # check if current song has changed. If so, update length of current song
        if "song" in self.mpd_status:
            currentSong = int(self.mpd_status["song"])
        else:
            currentSong = -1
        if currentSong != self.currentSong:
            self.currentSong = currentSong
            if currentSong != -1:
                self.mpd_current = self.client.currentsong()
                self.currentSongLength = int(self.mpd_current["time"])
            else:
                self.currentSongLength = 0 # no current song
            if emit:
                self.changeFromMPD.emit('currentSong', (self.currentSong, self.currentSongLength))
             
        # check for a change of playing state
        state = MPD_STATES[self.mpd_status["state"]]
        if state != self.state:
            if emit:
                self.changeFromMPD.emit('state', state)
            if state == STOP:
                self.currentSongLength = 0
                self.currentSong = -1
                if emit:
                    self.changeFromMPD.emit('currentSong', (-1, 0))
        self.state = state
        
        # check if elapsed time has changed
        if state != STOP:
            elapsed = float(self.mpd_status['elapsed'])
            if emit and elapsed != self.elapsed:
                self.changeFromMPD.emit('elapsed', elapsed)
            self.elapsed = elapsed
    
    def connect(self):
        import socket
        try:
            self.client.connect(host = self.connectionData['host'],
                        port = self.connectionData['port'],
                        timeout = CONNECTION_TIMEOUT)
            self._updateAttributes(emit = False)
            self.changeFromMPD.emit('init_done',
                                    (self.mpd_playlist[:],
                                     self.currentSong,
                                     self.currentSongLength,
                                     self.elapsed,
                                     self.state))
            self.connected = True
            self.changeFromMPD.emit('connect', None)
            return True
        except socket.error:
            self.connected = False
            return False       
        
    def run(self):
        # connect to MPD
        self.client = mpd.MPDClient()
        self.timer.start(POLLING_INTERVAL)
        
        self.seekTimer = QtCore.QTimer(self)
        self.seekTimer.setSingleShot(True)
        self.seekTimer.timeout.connect(self._seek)
        self.exec_()
        
    def poll(self):
        self.doPolling.wait() # do nothing as long as no frontends are registered
        while not (self.connected or self.connect()):
            self.sleep(2)
        try:
            self._updateAttributes()
        except mpd.ConnectionError as e:
            logger.warning(e)
            self.client.disconnect()
            self.changeFromMPD.emit('disconnect', None)
            
    def updateDB(self):
        if self.connected:
            self.client.update()
            
class MPDPlayerBackend(player.PlayerBackend):
    
    changeFromMain = QtCore.pyqtSignal(str, object)
    
    def __init__(self, name):
        super().__init__(name)
        self.playlist = playlist.PlaylistModel(self)
        self.paths = []
        try:
            data = config.storage.mpd.profiles[self.name]
        except KeyError:
            logger.warning("no MPD config found for profile {} - using default".format(self.name))
            data = default_data
        self.mpdthread = MPDThread(self, data)
        self.mpdthread.changeFromMPD.connect(self._handleMPDChange, Qt.QueuedConnection)
        self.changeFromMain.connect(self.mpdthread._handleMainChange)
        self.mpdthread.start()
        self._numFrontends = 0
        
        # create actions
        self.separator = QtGui.QAction("MPD", self)
        self.separator.setSeparator(True)
        
        self.updateDBAction = QtGui.QAction("Update Database", self)
        self.updateDBAction.triggered.connect(self.mpdthread.updateDB)
        
        # initialize functions that emit signals to the MPD thread on being called
        def _emitChange(what, *args):
            #if what[0]== '_': # those methods call superclass implementation first
            #    getattr(player.PlayerBackend, what)(self, *args)
            self.changeFromMain.emit(what, *args)
            
        for what in ("setElapsed", "setState", "setCurrentSong", "_setPlaylist",
                "_insertIntoPlaylist", "_removeFromPlaylist", "nextSong",
                "previousSong", "setVolume"):
            setattr(self, what, functools.partial(_emitChange, what))
    
    @QtCore.pyqtSlot(str, object)
    def _handleMPDChange(self, what, how):
        if what == 'init_done':
            self.paths, self.currentSong, self.currentSongLength, self.elapsed, self.state = how
            self.playlist.initFromPaths(self.paths) 
            if self.currentSong != -1:
                self.playlist.setCurrent(self.currentSong)
            self.connectionState = player.CONNECTED
            self.connectionStateChanged.emit(player.CONNECTED)
        
        elif what == 'elapsed':
            self.elapsed = how
            self.elapsedChanged.emit(how, self.currentSongLength)
            
        elif what == 'state':
            self.state = how
            self.stateChanged.emit(how)
            
        elif what == 'currentSong':
            self.currentSong, self.currentSongLength = how
            self.playlist.setCurrent(self.currentSong)
            self.currentSongChanged.emit(self.currentSong)
        
        elif what == 'volume':
            self.volume = how
            self.volumeChanged.emit(how)
            
        elif what == 'remove':
            print("Change from MPD: remove")
            print(how)
            self.playlist.removeByOffset(how[0][0],len(how),fromOutside=True)
            for pos,path in reversed(how):
                del self.paths[pos]
        
        elif what == 'insert':
            print("Change from MPD: insert")
            print(how)
            self.playlist.insertPathsAtOffset(how[0][0],[entry[1] for entry in how],fromOutside=True)
            for pos, path in how:
                self.paths[pos:pos] = path
            
        elif what == 'playlist':
            print("Change from MPD: playlist")
            print(how)
            self.playlist.resetFromPaths(how)
            
        elif what == 'disconnect':
            self.connectionStateChanged.emit(player.DISCONNECTED)
        elif what == 'connect':
            self.connectionStateChanged.emit(player.CONNECTED)
        else:
            print('WHAT? {}'.format(what))
                    
    def addTreeActions(self, view):
        view.addAction(self.separator)
        view.addAction(self.updateDBAction)
        
    
    def registerFrontend(self, obj):
        self._numFrontends += 1
        if self._numFrontends == 1:
            self.mpdthread.doPolling.set()
    
    def unregisterFrontend(self, obj):
        self._numFrontends -= 1
        if self._numFrontends == 0:
            self.mpdthread.doPolling.clear()
    
    def insertIntoPlaylist(self,pos,paths):
        self._insertIntoPlaylist(list(enumerate(paths,start=pos)))
    
    def removeFromPlaylist(self,begin,end):
        self._removeFromPlaylist([(begin,'') for i in range(end-begin)])
        
    def setPlaylist(self,paths):
        self._setPlaylist(paths)
    
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
    return {"SECTION:mpd":
            {'profiles': {} } }

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

def disable():
    del player.backendClasses['mpd']