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

import contextlib
import socket, threading, time
import mpd

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg import player, logging, profiles
from omg.core import tags
from omg.models import playlist
from . import filebackend as mpdfilebackend

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)


def enable():
    player.profileCategory.addType(profiles.ProfileType('mpd',
                                                        translate('MPDPlayerBackend','MPD'),
                                                        MPDPlayerBackend))
    from omg import filebackends
    filebackends.urlTypes["mpd"] = mpdfilebackend.MPDURL


def disable():
    player.profileCategory.removeType('mpd')
    from omg import filebackends
    del filebackends.urlTypes["mpd"]

            
class MPDPlayerBackend(player.PlayerBackend):
    
    className = "MPD"
    
    def __init__(self, name, type, state):
        super().__init__(name, type, state)
        self.playlist = playlist.PlaylistModel(self)
        self.urls = []

        if state is None:
            state = {}
        host = state['host'] if 'host' in state else 'localhost'
        port = state['port'] if 'port' in state else 6600
        password = state['password'] if 'password' in state else ''

        from .thread import MPDThread
        self.mpdthread = MPDThread(self, host, port, password)
        self.mpdthread.changeFromMPD.connect(self._handleMPDChange, Qt.QueuedConnection)
        self._numFrontends = 0
        
        self.commander = mpd.MPDClient()
        self.commanderConnected = False
        
        self.separator = QtGui.QAction("MPD", self)
        self.separator.setSeparator(True)
        
        self.updateDBAction = QtGui.QAction("Update Database", self)
        self.updateDBAction.triggered.connect(self.mpdthread.updateDB)
        
        self.stateChanged.connect(self.checkElapsedTimer)
        self.elapsedTimer = QtCore.QTimer(self)
        self.elapsedTimer.setInterval(100)
        self.elapsedTimer.timeout.connect(self.updateElapsed)
        
        self.seekTimer = QtCore.QTimer(self)
        self.seekTimer.setSingleShot(True)
        self.seekTimer.setInterval(25)
        self.seekTimer.timeout.connect(self._seek)
        
        self.atomicOp = threading.Lock()
        self.mpdthread.atomicOp = self.atomicOp
    
    def setConnectionParameters(self, host, port, password):
        #TODO reconnect
        self.mpdthread.host = host
        self.mpdthread.port = port
        self.mpdthread.password = password
        if self.commanderConnected:
            self.commander.disconnect()
            with self.prepareCommander:
                pass
            self.mpdthread.shouldConnect.clear()
            self.mpdthread.disconnect()
            self.mpdthread.shouldConnect.set()
            
        player.profileCategory.profileChanged.emit(self)
        
    def save(self):
        return {'host': self.mpdthread.host,
                'port': self.mpdthread.port,
                'password': self.mpdthread.password
                }
    
    @contextlib.contextmanager
    def prepareCommander(self):
        if not self.commanderConnected:
            self.commander.connect(self.mpdthread.host, self.mpdthread.port)
            self.commanderConnected = True
        try:
            yield
        except (mpd.ConnectionError, socket.error) as e:
            self.commander.disconnect()
            self.commander.connect(self.mpdthread.host, self.mpdthread.port)
            self.commanderConnected = True
        

    def state(self):
        return self._state
    
    def setState(self, state):
        self.prepareCommander()
        if state is player.PLAY:
            self.commander.play()
        elif state is player.PAUSE:
            self.commander.pause(1)
        elif state is player.STOP:
            self.commander.stop()
    
    def volume(self):
        return self._volume
    
    def setVolume(self, volume):
        with self.prepareCommander():
            self.commander.setvol(volume)
    
    def current(self):
        return self.playlist.current

    def setCurrent(self, index):
        self.prepareCommander()
        self.commander.play(index if index is not None else -1)
    
    def nextSong(self):
        self.prepareCommander()
        self.commander.next()
        
    def previousSong(self):
        self.prepareCommander()
        self.commander.previous()
    
    def currentOffset(self):
        if self._current < 0:
            return None
        else: return self._current
        
    def elapsed(self):
        return time.time() - self._currentStart
    
    def setElapsed(self, elapsed):
        
        self.seekRequest = elapsed
        self.seekTimer.start(20)
    
    def _seek(self):
        if self.seekRequest is not None:
            self.prepareCommander()
            self.commander.seek(self._current, self.seekRequest)
        self.seekRequest = None
    
    def updateElapsed(self):
        self.elapsedChanged.emit(self.elapsed())
    
    def checkElapsedTimer(self, newState):
        if newState is player.PLAY:
            self.elapsedTimer.start()
        else:
            self.elapsedTimer.stop()

    def makeUrl(self, path):
        mpdurl = mpdfilebackend.MPDURL("mpd://" + self.name + "/" + path)
        return mpdurl.getBackendFile().url
    
    @QtCore.pyqtSlot(str, object)
    def _handleMPDChange(self, what, how):
        if what == 'connect':
            paths, self._current, self._currentLength, self._currentStart, self._state = how
            self.urls = [self.makeUrl(path) for path in paths]
            self.playlist.initFromUrls(self.urls)
            self.playlist.setCurrent(self._current)
            self.connectionState = player.CONNECTED
            self.connectionStateChanged.emit(player.CONNECTED)
            if self._state is not player.STOP:
                self.stateChanged.emit(self._state)
        elif what == 'disconnect':
            self.connectionState = player.DISCONNECTED
            self._state = player.STOP
            self.stateChanged.emit(player.STOP)
            self.connectionStateChanged.emit(player.DISCONNECTED)
        elif what == 'elapsed':
            self._currentStart = how
            self.elapsedChanged.emit(self.elapsed())    
        elif what == 'state':
            self._state = how
            self.stateChanged.emit(how)
        elif what == 'current':
            self._current, self._currentLength = how
            self.playlist.setCurrent(self._current)
            self.currentChanged.emit(self._current)
        elif what == 'volume':
            self._volume = how
            self.volumeChanged.emit(how)
        elif what == 'remove':
            print("Change from MPD: remove")
            print(how)
            self.playlist.removeByOffset(how[0][0],len(how),updateBackend=False)
            for pos, url in reversed(how):
                del self.urls[pos]
        elif what == 'insert':
            print("Change from MPD: insert")
            print(how)
            pos = how[0][0]
            urlified = [ (pos,self.makeUrl(path)) for pos,path in how ]
            self.playlist.insertUrlsAtOffset(how[0][0], [tup[1] for tup in urlified], updateBackend=False)
            for pos, url in urlified:
                self.urls[pos:pos] = [ url ]
        elif what == 'playlist':
            print("Change from MPD: playlist")
            print(how)
            self.playlist.resetFromUrls([self.makeUrl(path) for path in how])
        else:
            print('WHAT? {}'.format(what))
                    
    def addTreeActions(self, view):
        view.addAction(self.separator)
        view.addAction(self.updateDBAction)
    
    def registerFrontend(self, obj):
        self._numFrontends += 1
        if self._numFrontends == 1:
            self.mpdthread.shouldConnect.set()
            self.mpdthread.start()
    
    def unregisterFrontend(self, obj):
        self._numFrontends -= 1
        if self._numFrontends == 0:
            self.mpdthread.shouldConnect.clear()
            self.mpdthread.disconnect()
            if self.commanderConnected:
                self.commander.disconnect()
                self.commanderConnected = False
    
    def insertIntoPlaylist(self, pos, urls):
        with self.prepareCommander():
            try:
                with self.atomicOp:
                    for position, url in enumerate(urls, start=pos):
                        self.commander.addid(url.path, position)
                        self.mpdthread.playlistVersion += 1 if position == len(self.mpdthread.mpd_playlist) else 2
                        self.mpdthread.mpd_playlist[position:position] = [url.path]
            except mpd.CommandError as e:
                raise player.BackendError('Some files could not be inserted: {}'.format(e))
    
    def removeFromPlaylist(self, begin, end):
        with self.prepareCommander():
            with self.atomicOp:
                print('atomic op')
                self.mpdthread.playlistVersion += end-begin
                del self.mpdthread.mpd_playlist[begin:end]
                for _ in range(end-begin):
                    self.commander.delete(begin)
                print('done')
        
    def move(self,fromOffset,toOffset):
        
        if fromOffset == toOffset:
            return
        with self.prepareCommander():
            with self.atomicOp:
                path = self.mpdthread.mpd_playlist.pop(fromOffset)
                self.mpdthread.mpd_playlist.insert(toOffset, path)
                self.commander.move(fromOffset, toOffset)
                self.mpdthread.playlistVersion += 1
    
    def configurationWidget(self):
        """Return a config widget, initialized with the data of the given *profile*."""
        return MPDConfigWidget(self)
    
    def getInfo(self, path):
        """Query MPD to get tags & length of the file at *path* (relative to this MPD instance).
        
        Since MPD connection is delegated to a subthread, this method might be slow.
        """
        self.prepareCommander()
        info = self.commander.listallinfo(path)[0]
        storage = tags.Storage()
        length = None
        for key, values in info.items():
            if key in ("file", "last-modified", "track"):
                #  mpd delivers these but they aren't keys
                continue
            if key == "time":
                length = int(values)
                continue
            tag = tags.get(key)
            if not isinstance(values, list):
                values = [ values ]
            storage[tag] = [ tag.convertValue(value, crop=True) for value in values ]
        return storage, length
        
    def __str__(self):
        return "MPDPlayerBackend({})".format(self.name)


class MPDConfigWidget(QtGui.QWidget):
    """Widget to configure playback profiles of type MPD."""    
    def __init__(self, profile=None):
        super().__init__()
        layout = QtGui.QVBoxLayout(self)
        formLayout = QtGui.QFormLayout()
        layout.addLayout(formLayout,1)
        
        self.hostEdit = QtGui.QLineEdit()
        formLayout.addRow(self.tr("Host:"),self.hostEdit)
        
        self.portEdit = QtGui.QLineEdit()
        self.portEdit.setValidator(QtGui.QIntValidator(0, 65535, self))
        formLayout.addRow(self.tr("Port:"),self.portEdit)
        
        self.passwordEdit = QtGui.QLineEdit()
        formLayout.addRow(self.tr("Password:"),self.passwordEdit)
        
        self.passwordVisibleBox = QtGui.QCheckBox()
        self.passwordVisibleBox.toggled.connect(self._handlePasswordVisibleBox)
        formLayout.addRow(self.tr("Password visible?"),self.passwordVisibleBox)
        
        buttonLayout = QtGui.QHBoxLayout()
        layout.addLayout(buttonLayout)
        saveButton = QtGui.QPushButton(self.tr("Save"))
        saveButton.clicked.connect(self._handleSave)
        buttonLayout.addWidget(saveButton)
        resetButton = QtGui.QPushButton(self.tr("Reset"))
        resetButton.clicked.connect(self._handleReset)
        buttonLayout.addWidget(resetButton)
        buttonLayout.addStretch(1)
        self.setProfile(profile)
    
    def setProfile(self, profile):
        """Change the profile whose data is displayed."""
        assert profile is not None
        self.profile = profile
        self.hostEdit.setText(profile.mpdthread.host)
        self.portEdit.setText(str(profile.mpdthread.port))
        self.passwordEdit.setText(profile.mpdthread.password)
        self.passwordVisibleBox.setChecked(len(profile.mpdthread.password) == 0)
    
    def _handleSave(self):
        """Really change the profile."""
        host = self.hostEdit.text()
        port = int(self.portEdit.text())
        password = self.passwordEdit.text()
        self.profile.setConnectionParameters(host, port, password)
        player.profileCategory.save()
        
    def _handleReset(self):
        """Reset the form to the stored values."""
        self.setProfile(self.profile)
    
    def _handlePasswordVisibleBox(self,checked):
        """Change whether the password is visible in self.passwordEdit."""
        self.passwordEdit.setEchoMode(QtGui.QLineEdit.Normal if checked else QtGui.QLineEdit.Password)
