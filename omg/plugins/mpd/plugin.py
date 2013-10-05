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

import re, contextlib, socket, threading, time

try:
    import mpd
    # Disable the 'Calling <this or that>' messages
    mpd.logger.setLevel('INFO')
except ImportError:
    raise ImportError("python-mpd2 not installed.")

import pkg_resources
mpd_version = [ int(x) for x in pkg_resources.get_distribution("python-mpd2").version.split(".")]
if mpd_version < [0,4,4]:
    raise ImportError("The installed version of python-mpd2 is too old. OMG needs at least "
                      "python-mpd2-0.4.4 to function properly.")
    
from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ... import application, filebackends, player, logging, profiles
from ...filebackends.filesystem import FileURL
from ...core import tags
from ...models import playlist
from . import filebackend as mpdfilebackend

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)


def enable():
    player.profileCategory.addType(profiles.ProfileType(
                'mpd', translate('MPDPlayerBackend','MPD'), MPDPlayerBackend))
    from omg import filebackends
    filebackends.urlTypes["mpd"] = mpdfilebackend.MPDURL


def disable():
    player.profileCategory.removeType('mpd')
    from omg import filebackends
    del filebackends.urlTypes["mpd"]

            
class MPDPlayerBackend(player.PlayerBackend):
    """Player backend to control an MPD server.
    
    The MPD backend currently uses two connections: A "commander", running in the event thread,
    sets off commands issued by user interaction (playback control, playlist manipulation, ...).
    The "idler", running in a seperate thread, listens for changes reported by OMG, such as
    state changes, playlist changes done with other programs, etc.
    """
    
    def __init__(self, name, type, state):
        super().__init__(name, type, state)
        self.stack = application.stack.createSubstack()
        self.playlist = playlist.PlaylistModel(self, stack=self.stack)
        self.urls = []

        if state is None:
            state = {}
        host = state.get('host', 'localhost')
        port = state.get('port', 6600)
        password = state.get('password', '')

        from .thread import MPDThread
        self.mpdthread = MPDThread(self, host, port, password)
        self.mpdthread.changeFromMPD.connect(self._handleMPDChange, Qt.QueuedConnection)
        self._numFrontends = 0
        self._flags = 0
        
        self.commander = mpd.MPDClient()
        
        # actions
        self.separator = QtGui.QAction("MPD", self)
        self.separator.setSeparator(True)
        self.updateDBAction = QtGui.QAction(self.tr("Update Database"), self)
        self.updateDBAction.triggered.connect(self.updateDB)
        self.configOutputsAction = QtGui.QAction(self.tr("Audio outputs..."), self)
        self.configOutputsAction.triggered.connect(self.showOutputDialog)
        
        self.stateChanged.connect(self.checkElapsedTimer)
        self.elapsedTimer = QtCore.QTimer(self)
        self.elapsedTimer.setInterval(100)
        self.elapsedTimer.timeout.connect(self.updateElapsed)
        
        self.seekTimer = QtCore.QTimer(self)
        self.seekTimer.setSingleShot(True)
        self.seekTimer.setInterval(25)
        self.seekTimer.timeout.connect(self._seek)
        
        # this lock is used when the main thread changes the playlist information of the idler,
        # which is done when the user manipulates the playlist in order to avoid that the idler
        # reports that same change.
        self.playlistLock = threading.RLock()
        self.mpdthread.playlistLock = self.playlistLock
    
    def save(self):
        return {'host': self.mpdthread.host,
                'port': self.mpdthread.port,
                'password': self.mpdthread.password
                }
    
    def setConnectionParameters(self, host, port, password):
        #TODO reconnect
        self.mpdthread.host = host
        self.mpdthread.port = port
        self.mpdthread.password = password
        if self.commander._sock is not None:
            self.commander.disconnect()
            with self.prepareCommander():
                pass
            self.mpdthread.shouldConnect.clear()
            self.mpdthread.disconnect()
            self.mpdthread.shouldConnect.set()
            
        player.profileCategory.profileChanged.emit(self)
        
    @contextlib.contextmanager
    def prepareCommander(self):
        """Context manager to ensure that the commander is connected."""
        if self.commander._sock is None:
            self.commander.connect(self.mpdthread.host, self.mpdthread.port)
        try:
            yield
        except (mpd.ConnectionError, socket.error):
            self.commander.connect(self.mpdthread.host, self.mpdthread.port)
        
    def state(self):
        return self._state
    
    def setState(self, state):
        with self.prepareCommander():
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
            try:
                self.commander.setvol(volume)
            except mpd.CommandError:
                logger.error("Problems setting volume. Maybe MPD does not allow setting the volume.")
    
    def current(self):
        return self.playlist.current

    def setCurrent(self, index):
        with self.prepareCommander():
            self.commander.play(index if index is not None else -1)
    
    def skipForward(self):
        with self.prepareCommander():
            self.commander.next()
        
    def skipBackward(self):
        with self.prepareCommander():
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
            with self.prepareCommander():
                self.commander.seek(self._current, self.seekRequest)
        self.seekRequest = None
    
    def updateElapsed(self):
        self.elapsedChanged.emit(self.elapsed())
    
    def checkElapsedTimer(self, newState):
        if newState is player.PLAY:
            self.elapsedTimer.start()
        else:
            self.elapsedTimer.stop()

    def updateDB(self, path=None):
        """Update MPD's database. An optional *path* can be given to only update that file/dir."""
        with self.prepareCommander():
            if path:
                self.commander.update(path)
            else:
                self.commander.update()
    
    def makeUrl(self, path):
        """Create an OMG URL for the given path reported by MPD.
        
        If the MPD path has the form of a non-default URL (i.e. proto://path), it is tried to load
        an appropriate URL using BackendURL.fromString().
        Otherwise, if *path* refers to a normal file in MPDs database, an MPDURL is created.
        If the file is also found on the local filesystem, then a normal FileURL is returned.
        """
        if re.match("[a-zA-Z]{2,5}://", path) is not None:
            try:
                return filebackends.BackendURL.fromString(path)
            except KeyError:
                logger.warning("Unsupported MPD URL type: {}".format(path))
        mpdurl = mpdfilebackend.MPDURL("mpd://" + self.name + "/" + path)
        # this will convert the URL to a local file URL if it exists
        return mpdurl.getBackendFile().url
    
    @QtCore.pyqtSlot(str, object)
    def _handleMPDChange(self, what, how):
        """React on changes reported by the idler thread."""
        if what == 'connect':
            paths, self._current, self._currentLength, self._currentStart, \
                self._state, self._volume, self._outputs = how
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
            if self.commander._sock is not None:
                self.commander.disconnect()
            application.stack.resetSubstack(self.stack)
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
            self.playlist.removeByOffset(how[0][0],
                                         len(how),
                                         updateBackend='onundoredo')
            for pos, url in reversed(how):
                del self.urls[pos]
        elif what == 'insert':
            pos = how[0][0]
            urlified = [ (pos,self.makeUrl(path)) for pos,path in how ]
            self.playlist.insertUrlsAtOffset(how[0][0],
                                             [tup[1] for tup in urlified],
                                             updateBackend='onundoredo')
            for pos, url in urlified:
                self.urls[pos:pos] = [ url ]
        elif what == 'playlist':
            self.playlist.resetFromUrls([self.makeUrl(path) for path in how],
                                        updateBackend='onundoredo')
        elif what == 'outputs':
            self._outputs = how
        elif what == 'flags':
            self._flags = how
            self.flagsChanged.emit(how)
        else:
            raise ValueError("Unknown change message from idler thread: {}".format(what))
                    
    def treeActions(self):
        yield self.separator
        yield self.updateDBAction
        yield self.configOutputsAction
    
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
            if self.commander._sock is not None:
                self.commander.disconnect()
            application.stack.resetSubstack(self.stack)
    
    def setPlaylist(self, urls):
        with self.prepareCommander():
            with self.playlistLock:
                self.commander.clear()
                self.mpdthread.playlistVersion += 1
                self.mpdthread.mpd_playlist = []
                self.insertIntoPlaylist(0, urls)
    
    def insertIntoPlaylist(self, pos, urls):
        """Insert *urls* into the MPD playlist at position *pos*.
        
        This methode raises a player.InsertError if not all of the files could be added to MPDs
        playlist, which happens if the URL is not known to MPD. The list of URls successfully
        inserted is contained in the error object's *successfulURLs* attribute.
        """
        with self.prepareCommander():
            inserted = []
            try:
                with self.playlistLock:
                    isEnd = (pos == len(self.mpdthread.mpd_playlist))
                    for position, url in enumerate(urls, start=pos):
                        if isEnd:
                            self.commander.add(url.path)
                            self.mpdthread.playlistVersion += 1
                        else:
                            self.commander.addid(url.path, position)
                            self.mpdthread.playlistVersion += 2
                        self.mpdthread.mpd_playlist[position:position] = [url.path]
                        inserted.append(url)
            except mpd.CommandError:
                raise player.InsertError('Could not insert all files', inserted)
    
    def removeFromPlaylist(self, begin, end):
        with self.prepareCommander():
            with self.playlistLock:
                del self.mpdthread.mpd_playlist[begin:end]
                self.commander.delete("{}:{}".format(begin,end))
                self.mpdthread.playlistVersion += 1
        
    def move(self, fromOffset, toOffset):
        
        if fromOffset == toOffset:
            return
        with self.prepareCommander():
            with self.playlistLock:
                path = self.mpdthread.mpd_playlist.pop(fromOffset)
                self.mpdthread.mpd_playlist.insert(toOffset, path)
                self.commander.move(fromOffset, toOffset)
                self.mpdthread.playlistVersion += 1
    
    def configurationWidget(self, parent):
        """Return a config widget, initialized with the data of the given *profile*."""
        return MPDConfigWidget(self, parent)
    
    def getInfo(self, path):
        """Query MPD to get tags & length of the file at *path* (relative to this MPD instance).
        
        Since MPD connection is delegated to a subthread, this method might be slow.
        """
        with self.prepareCommander():
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
        
    def showOutputDialog(self):
        dialog = QtGui.QDialog(application.mainWindow)
        layout = QtGui.QVBoxLayout()
        layout.addWidget(QtGui.QLabel(self.tr("Choose which audio outputs to use:")))
        checkboxes = []
        for output in sorted(self._outputs, key=lambda out:out["outputid"]):
            checkbox = QtGui.QCheckBox(output["outputname"])
            checkbox.setChecked(output["outputenabled"] == "1")
            checkboxes.append(checkbox)
            layout.addWidget(checkbox)
        dbb = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel | QtGui.QDialogButtonBox.Ok)
        layout.addWidget(dbb)
        dbb.accepted.connect(dialog.accept)
        dbb.rejected.connect(dialog.reject)
        dialog.setLayout(layout)
        if dialog.exec_() == QtGui.QDialog.Accepted:
            for checkbox, output in zip(checkboxes, self._outputs):
                if output["outputenabled"] == "0" and checkbox.isChecked():
                    with self.prepareCommander():
                        self.commander.enableoutput(output["outputid"])
                elif output["outputenabled"] == "1" and not checkbox.isChecked():
                    with self.prepareCommander():
                        self.commander.disableoutput(output["outputid"])
        
    def __str__(self):
        return "MPDPlayerBackend({})".format(self.name)

    def flags(self):
        return self._flags
    
    def setFlags(self, flags):
        if flags != self._flags:
            with self.prepareCommander():
                self.commander.repeat(flags & player.FLAG_REPEATING)
            # self._flags will be updated when a change in MPD's status is detected
    

class MPDConfigWidget(QtGui.QWidget):
    """Widget to configure playback profiles of type MPD."""
    def __init__(self, profile, parent):
        super().__init__(parent)
        
        layout = QtGui.QVBoxLayout(self)
        formLayout = QtGui.QFormLayout()
        layout.addLayout(formLayout)
        
        self.hostEdit = QtGui.QLineEdit()
        formLayout.addRow(self.tr("Host:"), self.hostEdit)
        
        self.portEdit = QtGui.QLineEdit()
        self.portEdit.setValidator(QtGui.QIntValidator(0, 65535, self))
        formLayout.addRow(self.tr("Port:"), self.portEdit)
        
        self.passwordEdit = QtGui.QLineEdit()
        formLayout.addRow(self.tr("Password:"), self.passwordEdit)
        
        self.passwordVisibleBox = QtGui.QCheckBox()
        self.passwordVisibleBox.toggled.connect(self._handlePasswordVisibleBox)
        formLayout.addRow(self.tr("Password visible?"), self.passwordVisibleBox)
        
        self.saveButton = QtGui.QPushButton(self.tr("Save"))
        self.saveButton.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        self.saveButton.setEnabled(False)
        self.saveButton.clicked.connect(self.save)
        layout.addWidget(self.saveButton)
        layout.addStretch(1)
        
        self.setProfile(profile)
        
        self.hostEdit.textChanged.connect(self._handleChange)
        self.portEdit.textChanged.connect(self._handleChange)
        self.passwordEdit.textChanged.connect(self._handleChange)
    
    def setProfile(self, profile):
        """Change the profile whose data is displayed."""
        self.profile = profile
        self.hostEdit.setText(profile.mpdthread.host)
        self.portEdit.setText(str(profile.mpdthread.port))
        self.passwordEdit.setText(profile.mpdthread.password)
        self.passwordVisibleBox.setChecked(len(profile.mpdthread.password) == 0)
    
    def _handleChange(self):
        """(De)activate save button when configuration is modified."""
        self.saveButton.setEnabled(self.isModified())
        
    def isModified(self):
        """Return whether the configuration in the GUI differs from the stored configuration."""
        host = self.hostEdit.text()
        try:
            port = int(self.portEdit.text())
        except ValueError:
            return True # Not an int
        password = self.passwordEdit.text()
        mpdThread = self.profile.mpdthread
        return [host, port, password] != [mpdThread.host, mpdThread.port, mpdThread.password]
        
    def save(self):
        """Really change the profile."""
        host = self.hostEdit.text()
        port = int(self.portEdit.text())
        password = self.passwordEdit.text()
        self.profile.setConnectionParameters(host, port, password)
        player.profileCategory.save()
        self.saveButton.setEnabled(False)
    
    def _handlePasswordVisibleBox(self,checked):
        """Change whether the password is visible in self.passwordEdit."""
        self.passwordEdit.setEchoMode(QtGui.QLineEdit.Normal if checked else QtGui.QLineEdit.Password)
        
    def okToClose(self):
        """In case of unsaved configuration data, ask the user what to do."""
        if self.isModified():
            button = QtGui.QMessageBox.question(
                                    self, self.tr("Unsaved changes"),
                                    self.tr("MPD configuration has been modified. Save changes?"),
                                    QtGui.QMessageBox.Abort | QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
            if button == QtGui.QMessageBox.Abort:
                return False
            elif button == QtGui.QMessageBox.Yes:
                self.save()
            else: self.setProfile(self.profile) # reset
        return True
    