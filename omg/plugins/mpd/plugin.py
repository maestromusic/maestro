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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

import mpd

from omg import player, logging, profiles
from omg.models import playlist
from . import filebackend as mpdfilebackend

logger = logging.getLogger(__name__)


def enable():    
    from omg import filebackends
    player.profileConf.addClass(MPDPlayerBackend)
    filebackends.urlTypes["mpd"] = mpdfilebackend.MPDURL


def disable():
    from omg import filebackends
    player.profileConf.removeClass(MPDPlayerBackend)
    del filebackends.urlTypes["mpd"]

            
class MPDPlayerBackend(player.PlayerBackend):
    
    className = "MPD"
    
    def __init__(self, name, host='localhost', port='6600', password=None):
        super().__init__(name)
        self.playlist = playlist.PlaylistModel(self)
        self.urls = []
        from .thread import MPDThread
        self.mpdthread = MPDThread(self, host, port, password)
        self.mpdthread.changeFromMPD.connect(self._handleMPDChange, Qt.QueuedConnection)
        self._numFrontends = 0
        
        self.commander = mpd.MPDClient()
        self.commanderConnected = False
        
        # create actions
        self.separator = QtGui.QAction("MPD", self)
        self.separator.setSeparator(True)
        
        self.updateDBAction = QtGui.QAction("Update Database", self)
        self.updateDBAction.triggered.connect(self.mpdthread.updateDB)
    
    def config(self):
        return self.mpdthread.host, self.mpdthread.port, self.mpdthread.password
    
    def prepareCommander(self):
        if not self.commanderConnected:
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
        self.prepareCommander()
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
        return self._elapsed
    
    def setElapsed(self, elapsed):
        self.prepareCommander()
        # TODO: seekTimer
        self.commander.seek(self.currentOffset(), elapsed)
    
    def makeUrl(self, path):
        mpdurl = mpdfilebackend.MPDURL("mpd://" + self.name + "/" + path)
        return mpdurl.getBackendFile().url
    
    @QtCore.pyqtSlot(str, object)
    def _handleMPDChange(self, what, how):
        if what == 'connect':
            paths, self._current, self._currentLength, self._elapsed, self._state = how
            self.urls = [self.makeUrl(path) for path in paths]
            self.playlist.initFromUrls(self.urls)
            self.playlist.setCurrent(self._current)
            self.connectionState = player.CONNECTED
            self.connectionStateChanged.emit(player.CONNECTED)
        elif what == 'disconnect':
            self.connectionState = player.DISCONNECTED
            self.connectionStateChanged.emit(player.DISCONNECTED)
        elif what == 'elapsed':
            self._elapsed = how
            self.elapsedChanged.emit(how)    
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
        self._insertIntoPlaylist(list(enumerate(urls, start=pos)))
    
    def removeFromPlaylist(self, begin, end):
        self._removeFromPlaylist([(begin,'') for i in range(end-begin)])
        
    def move(self,fromOffset,toOffset):
        self._move((fromOffset,toOffset))
    
    @classmethod
    def configurationWidget(cls, profile=None):
        """Return a config widget, initialized with the data of the given *profile*."""
        return MPDConfigWidget(profile)
    
    def getInfo(self, path):
        """Query MPD to get tags & length of the file at *path* (relative to this MPD instance).
        
        Since MPD connection is delegated to a subthread, this method might be slow.
        """
        self.mpdthread.syncCallEvent.clear()
        self.changeFromMain.emit("getTags", path)
        self.mpdthread.syncCallEvent.wait()
        
        getPath, getTags, getLength = self.mpdthread.getInfoData
        if getPath != path:
            print(getPath)
            print(path)
            raise Exception()
        return getTags, getLength
        
    def __str__(self):
        return "MPDPlayerBackend({})".format(self.name)

class MPDConfigWidget(profiles.ConfigurationWidget):
    
    def __init__(self, profile = None):
        super().__init__()
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
        if profile is None:
            host, port, password = 'localhost', 6600, ''
        else:
            host, port, password = player.profileConf[profile].config()
        self.hostEdit.setText(host)
        self.portEdit.setText(str(port))
        self.passwordEdit.setText(password)
    
    def currentConfig(self):
        host = self.hostEdit.text()
        port = int(self.portEdit.text())
        password = self.passwordEdit.text()
        return (host, port, password)

