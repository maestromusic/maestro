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

import functools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg import player, logging, profiles
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
    changeFromMain = QtCore.pyqtSignal(str, object)
    
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
        self.changeFromMain.connect(self.mpdthread._handleMainChange)
        self.mpdthread.start()
        self._numFrontends = 0
        
        # create actions
        self.separator = QtGui.QAction("MPD", self)
        self.separator.setSeparator(True)
        
        self.updateDBAction = QtGui.QAction("Update Database", self)
        self.updateDBAction.triggered.connect(self.mpdthread.updateDB)
        
        # initialize functions that emit signals to the MPD thread on being called
        def _emitChange(what, arg, synchronized=False):
            #if what[0]== '_': # those methods call superclass implementation first
            #    getattr(player.PlayerBackend, what)(self, *args)
            self.changeFromMain.emit(what, arg)
            if synchronized:
                self.mpdthread.syncCallEvent.wait()
            
        for what in ("setElapsed", "setState", "setCurrent", "nextSong",
                "previousSong", "setVolume"):
            setattr(self, what, functools.partial(_emitChange, what))
        
        for what in ("setPlaylist", "_insertIntoPlaylist", "_removeFromPlaylist", "_move"):
            setattr(self, what, functools.partial(_emitChange, what, synchronized=True))
    
    def setConnectionParameters(self,host,port,password):
        #TODO reconnect
        self.category.profileChanged.emit(self)
        
    def save(self):
        return {'host': self.mpdthread.host,
                'port': self.mpdthread.port,
                'password': self.mpdthread.password
                }
    
    def state(self):
        return self._state
    
    def volume(self):
        return self._volume
    
    def current(self):
        return self.playlist.current

    def currentOffset(self):
        if self._current < 0:
            return None
        else: return self._current
        
    def elapsed(self):
        return self._elapsed
    
    def makeUrl(self, path):
        mpdurl = mpdfilebackend.MPDURL("mpd://" + self.name + "/" + path)
        return mpdurl.getBackendFile().url
    
    @QtCore.pyqtSlot(str, object)
    def _handleMPDChange(self, what, how):
        if what == 'init_done':
            paths, self._current, self._currentLength, self._elapsed, self._state = how
            self.urls = [self.makeUrl(path) for path in paths]
            self.playlist.initFromUrls(self.urls)
            self.playlist.setCurrent(self._current)
            self.connectionState = player.CONNECTED
            self.connectionStateChanged.emit(player.CONNECTED)
        
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
            
        elif what == 'disconnect':
            self.connectionState = player.DISCONNECTED
            self.connectionStateChanged.emit(player.DISCONNECTED)
        elif what == 'connect':
            self.connectionState = player.CONNECTED
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
    
    def insertIntoPlaylist(self, pos, urls):
        self._insertIntoPlaylist(list(enumerate(urls, start=pos)))
    
    def removeFromPlaylist(self, begin, end):
        self._removeFromPlaylist([(begin,'') for i in range(end-begin)])
        
    def move(self,fromOffset,toOffset):
        self._move((fromOffset,toOffset))
    
    def configurationWidget(self):
        """Return a config widget, initialized with the data of the given *profile*."""
        return MPDConfigWidget(self)
    
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
        self.profile.setConnectionParameters(host,port,password)
        
    def _handleReset(self):
        """Reset the form to the stored values."""
        self.setProfile(self.profile)
    
    def _handlePasswordVisibleBox(self,checked):
        """Change whether the password is visible in self.passwordEdit."""
        self.passwordEdit.setEchoMode(QtGui.QLineEdit.Normal if checked else QtGui.QLineEdit.Password)
