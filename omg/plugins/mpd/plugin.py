# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

try:
    import mpd
    # Disable the 'Calling <this or that>' messages
    mpd.logger.setLevel('INFO')
except ImportError:
    raise ImportError("python-mpd2 not installed.")

import pkg_resources
mpd_version = [ int(x) for x in pkg_resources.get_distribution("python-mpd2").version.split(".")]
if mpd_version < [0,5,1]:
    raise ImportError("The installed version of python-mpd2 is too old. OMG needs at least "
                      "python-mpd2-0.5.1 to function properly.")

import re, time
import select
import contextlib

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ... import application, database as db, filebackends, player, logging, profiles, stack
from ...core import tags
from ...models import playlist
from . import filebackend as mpdfilebackend

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)


def enable():
    player.profileCategory.addType(profiles.ProfileType(
                'mpd', translate('MPDPlayerBackend','MPD'), MPDPlayerBackend))
    filebackends.urlTypes["mpd"] = mpdfilebackend.MPDURL


def disable():
    player.profileCategory.removeType('mpd')
    del filebackends.urlTypes["mpd"]

MPD_STATES = { 'play': player.PLAY, 'stop': player.STOP, 'pause': player.PAUSE}

            
class MPDPlayerBackend(player.PlayerBackend):
    """Player backend to control an MPD server.
    
    The MPD client is implemented using the "idle" command of MPD, which causes the socket to block
    until some change is reported by MPD. We use the select method to continuously (by a timer with
    short timeout) check if we can read from the socket, i.e. the idle command has something to
    report (see implementation of the checkIdle function).
    
    The playlist, as reported by MPD, is stored in the attribute *mpdPlaylist" by means of a list
    of strings (paths relative to MPD collection folder). The backend keeps this in sync with MPD,
    updating it whenever a change is reported by MPD (via the idle command), or the OMG user issues
    a playlist modification.
    """
    
    def __init__(self, name, type, state):
        """Create the backend object named *name* with the configuration given in *state*.
        
        The backend connects to MPD as soon as at least one frontend is registered, and terminates
        the connection when the last frontend is unregistered. On initalization, no connection is
        made.
        """
        super().__init__(name, type, state)
        self.stack = stack.createSubstack()
        self.playlist = playlist.PlaylistModel(self, stack=self.stack)

        if state is None:
            state = {}
        self.host = state.get('host', 'localhost')
        self.port = state.get('port', 6600)
        self.password = state.get('password', '')

        self._numFrontends = 0
        
        # actions
        self.separator = QtGui.QAction("MPD", self)
        self.separator.setSeparator(True)
        self.updateDBAction = QtGui.QAction(self.tr("Update Database"), self)
        self.updateDBAction.triggered.connect(self.updateDB)
        self.configOutputsAction = QtGui.QAction(self.tr("Audio outputs..."), self)
        self.configOutputsAction.triggered.connect(self.showOutputDialog)
        
        self.stateChanged.connect(self.checkElapsedTimer)
        self.elapsedTimer = QtCore.QTimer(self)
        self.elapsedTimer.setInterval(50)
        self.elapsedTimer.timeout.connect(self.updateElapsed)
        
        self.seekTimer = QtCore.QTimer(self)
        self.seekTimer.setSingleShot(True)
        self.seekTimer.setInterval(25)
        self.seekTimer.timeout.connect(self._seek)
        
        self.idleTimer = QtCore.QTimer(self)
        self.idleTimer.setInterval(50)
        self.idleTimer.timeout.connect(self.checkIdle)
        
        self.idling = False
        self.playlistVersion = None
        self._state = None
        self._currentLength = None
        self._volume = None
        self._flags = player.RANDOM_OFF
        self.seekRequest = None
        self.outputs = None
        self.client = None

    
    def save(self):
        return dict(host=self.host, port=self.port, password=self.password)
    
    
    def setConnectionParameters(self, host, port, password):
        """Change the connection parameters. Issues a reconnect with the new ones."""
        self.host = host
        self.port = port
        self.password = password
        if self.connectionState == player.CONNECTED:
            self.disconnectClient()
        self.connectBackend()
        player.profileCategory.profileChanged.emit(self)
    
    
    def connectBackend(self):
        """Connect to MPD.
        
        Reads the current playlist and state from the server and emits according signals.
        Afterwards, the idling mechanism is started.
        """
        assert self.client is None
        client = mpd.MPDClient()
        client.timeout = 2
        client.idletimeout = None
        try:
            client.connect(self.host, self.port)
        except (ConnectionRefusedError, OSError):
            return
        if self.password:
            client.password(self.password)
        self.mpdStatus = client.status()
        self.client = client
        self.updateMixer()
        self.updatePlaylist()
        self.updatePlayer()
        self.updateOutputs()
        self.updateFlags()
        self.connectionState = player.CONNECTED
        self.connectionStateChanged.emit(player.CONNECTED)
        self.client.send_idle()
        self.idling = True
        self.idleTimer.start()
    
    
    def disconnectClient(self, skipSocket=False):
        """Disconnect from MPD.
        
        If *skipSocket* is True, nothing is done on the socket (useful after connection failures).
        """ 
        logger.debug("calling MPD disconnect host {}".format(self.host))
        if self.idleTimer.isActive():
            self.idleTimer.stop()
        if not skipSocket:
            self.checkIdle(False)
            self.client.close()
            self.client.disconnect()
        self.client = None
        self.connectionState = player.DISCONNECTED
        self.connectionStateChanged.emit(player.DISCONNECTED)
        stack.resetSubstack(self.stack)
       
    
    def checkIdle(self, resumeIdle=True):
        """Check the client socket for responses to the "idle" command.
        
        Uses the "select" method to check whether there is something to read on self.client._sock.
        If so, update the backend's state accordingly.
        
        Otherwise and if *resumeIdle* is False, the "noidle" command is sent to MPD to stop idling.
        On connection errors this method calls self.disconnectClient(True) and returns the error
        object.
        """
        try:
            canRead = select.select([self.client._sock], [], [], 0)[0]
            if len(canRead) > 0:
                self.idling = False
                changed = self.client.fetch_idle()
                self.checkMPDChanges(changed)
                if resumeIdle:
                    self.client.send_idle()
                    self.idling = True
            elif not resumeIdle and self.idling:
                self.idling = False
                changed = self.client.noidle()
                if changed:
                    self.checkMPDChanges(changed)
        except mpd.ConnectionError as e:
            self.idling = False
            self.disconnectClient(True)
            return e
    
    
    def checkMPDChanges(self, changed):
        """Check for changes in the MPD subsystems listed in "changed" (as returned from idle).
        
        All changes will be handled accordingly. If """
        self.mpdStatus = self.client.status()
        if 'error' in self.mpdStatus:
            from omg.gui.dialogs import warning
            warning('MPD error',
                    self.tr('MPD reported an error:\n{}').format(self.mpdStatus['error']))
            self.client.clearerror()
        if 'mixer' in changed:
            self.updateMixer()
            changed.remove('mixer')
        if 'playlist' in changed:
            self.updatePlaylist()
            changed.remove('playlist')
        if 'player' in changed:
            self.updatePlayer()
            changed.remove('player')
        if 'update' in changed:
            changed.remove('update')
        if 'output' in changed:
            self.updateOutputs()
            changed.remove('output')
        if 'options' in changed:
            self.updateFlags()
            changed.remove('options')
        if len(changed) > 0:
            logger.warning('unhandled MPD changes: {}'.format(changed))
    
    
    @contextlib.contextmanager
    def getClient(self):
        """Intermits idling and returns the MPDClient object. Might raise ConnectionErrors."""
        if self.idling:
            self.idleTimer.stop()
            error = self.checkIdle(resumeIdle=False)
            if error:
                raise error 
            yield self.client
            self.client.send_idle()
            self.idling = True
            self.idleTimer.start()
        else:
            yield self.client
    
    
    def updateMixer(self):
        """Check if MPD's volume has changed and set backend's volume accordingly."""
        volume = int(self.mpdStatus['volume'])
        if volume != self._volume:
            self._volume = volume
            self.volumeChanged.emit(self._volume)
    
    
    def updatePlaylist(self):
        """Update the playlist if it has changed on the server.
        
        Currently, two special cases are detected: Insertion of consecutive songs,
        and removal of consecutive songs.
        
        In any other case, a complete playlist change is issued.
        """
        newVersion = int(self.mpdStatus["playlist"])
        if newVersion == self.playlistVersion:
            return
        logger.debug("detected new plVersion: {}-->{}".format(self.playlistVersion, newVersion))
        
        if self.playlistVersion is None:
            # this happens only on initialization.
            self.mpdPlaylist = [x["file"] for x in self.client.playlistinfo()]
            self.playlistVersion = newVersion
            self.playlist.initFromUrls(self.makeUrls(self.mpdPlaylist))
            return
        plChanges = self.client.plchanges(self.playlistVersion)
        changedFiles = [ a["file"] for a in plChanges ]
        self.playlistVersion = newVersion
        newLength = int(self.mpdStatus["playlistlength"])
        # first special case: find out if only consecutive songs were removed 
        if newLength < len(self.mpdPlaylist):
            numRemoved = len(self.mpdPlaylist) - newLength
            oldSongsThere = self.mpdPlaylist[-len(plChanges):] if len(plChanges) > 0 else []
            if changedFiles == oldSongsThere:
                firstRemoved = newLength - len(plChanges)
                del self.mpdPlaylist[firstRemoved:firstRemoved+numRemoved]
                self.playlist.removeByOffset(firstRemoved, numRemoved, updateBackend='onundoredo')
                return
        # second special case: find out if a number of consecutive songs were inserted
        elif newLength > len(self.mpdPlaylist):
            numInserted = newLength - len(self.mpdPlaylist)
            numShifted = len(plChanges) - numInserted
            if numShifted == 0:
                newSongsThere = []
                oldSongsThere = []
            else:
                newSongsThere = plChanges
                oldSongsThere = self.mpdPlaylist[-numShifted:]
            if newSongsThere == oldSongsThere:
                firstInserted = len(self.mpdPlaylist) - numShifted
                paths = changedFiles[:numInserted]
                self.mpdPlaylist[firstInserted:firstInserted] = paths
                urls = self.makeUrls(paths)
                pos = int(plChanges[0]["pos"])
                self.playlist.insertUrlsAtOffset(pos, urls, updateBackend='onundoredo')
                return
        if len(plChanges) == 0:
            logger.warning('no changes???')
            return
        # other cases: update self.mpdPlaylist and perform a general playlist change
        reallyChange = False
        for pos, file in sorted((int(a["pos"]),a["file"]) for a in plChanges):
            if pos < len(self.mpdPlaylist):
                if self.mpdPlaylist[pos] != file:
                    reallyChange = True
                self.mpdPlaylist[pos] = file
            else:
                reallyChange = True
                self.mpdPlaylist.append(file)
        if reallyChange: # this might not happen e.g. when a stream is updated
            self.playlist.resetFromUrls(self.makeUrls(self.mpdPlaylist),
                                        updateBackend='onundoredo')   
        
    
    def updatePlayer(self):
        """Check if player state (current song, elapsed, state) have changed from MPD."""
        if "song" in self.mpdStatus:
            current = int(self.mpdStatus["song"])
        else:
            current = None
        if current != self.playlist.current:
            if current is None:
                self._currentLength = 0 # no current song
            else:
                mpdCurrent = self.client.currentsong()
                if "time" in mpdCurrent:
                    self._currentLength = int(mpdCurrent["time"])
                else:
                    self._currentLength = -1
            self.playlist.setCurrent(current)
            self.currentChanged.emit(current)
        
        if "elapsed" in self.mpdStatus:
            elapsed = float(self.mpdStatus["elapsed"])
            self._currentStart = time.time() - elapsed
            self.elapsedChanged.emit(self.elapsed())
             
        # check for a change of playing state
        state = MPD_STATES[self.mpdStatus["state"]]
        if state != self._state:
            self._state = state
            self.stateChanged.emit(state)
            if state == player.STOP:
                self._currentLength = 0
                self.playlist.setCurrent(None)
                self.currentChanged.emit(None)
        self._state = state


    def updateOutputs(self):
        """Check if the selected audio outputs have been changed by MPD."""
        outputs = self.client.outputs()
        if outputs != self.outputs:
            self.outputs = outputs
    
    
    def updateFlags(self):
        """Check if random flag has been changed by MPD."""
        flags = player.FLAG_REPEATING & (self.mpdStatus['repeat'] == '1')
        if flags != self._flags:
            self._flags = flags
            self.flagsChanged.emit(flags)
    
    
    def state(self):
        return self._state
    
    
    def setState(self, state):
        with self.getClient() as client:
            if state is player.PLAY:
                client.play()
            elif state is player.PAUSE:
                client.pause(1)
            elif state is player.STOP:
                client.stop()
    
    
    def volume(self):
        return self._volume
    
    
    def setVolume(self, volume):
        with self.getClient() as client:
            try:
                client.setvol(volume)
            except mpd.CommandError:
                logger.error("Problems setting volume. Does MPD allow setting the volume?")


    def current(self):
        return self.playlist.current

    
    def setCurrent(self, index):
        with self.getClient() as client:
            client.play(index if index is not None else -1)
    
    
    def skipForward(self):
        with self.getClient() as client:
            client.next()
        
    
    def skipBackward(self):
        with self.getClient() as client:
            client.previous()        
    
    def elapsed(self):
        if self._state == player.STOP:
            return 0
        return time.time() - self._currentStart
    
    
    def setElapsed(self, elapsed):
        self.seekRequest = elapsed
        self.seekTimer.start()
    
    
    def _seek(self):
        if self.seekRequest is not None:
            with self.getClient() as client:
                client.seekcur(self.seekRequest)
        self.seekRequest = None
    
    
    def updateElapsed(self):
        if not self.seekTimer.isActive():
            self.elapsedChanged.emit(self.elapsed())
    
    
    def checkElapsedTimer(self, newState):
        if newState is player.PLAY:
            self.elapsedTimer.start()
        else:
            self.elapsedTimer.stop()
    
    
    def flags(self):
        return self._flags
    
    
    def setFlags(self, flags):
        if flags != self._flags:
            with self.getClient() as client:
                client.repeat(flags & player.FLAG_REPEATING)
            # self._flags will be updated when a change in MPD's status is detected
    
    
    def updateDB(self, path=None):
        """Update MPD's database. An optional *path* can be given to only update that file/dir."""
        with self.getClient() as client:
            if path:
                client.update(path)
            else:
                client.update()
    
    
    def makeUrls(self, paths):
        """Create OMG URLs for the given paths reported by MPD.
        
        If an MPD path has the form of a non-default URL (i.e. proto://path), it is tried to load
        an appropriate URL using BackendURL.fromString().
        Otherwise, if *path* refers to a normal file in MPDs database, an MPDURL is created.
        If the file is also found on the local filesystem, then a normal FileURL is returned.
        """
        urls = []
        for path in paths:
            if re.match("[a-zA-Z]{2,5}://", path) is not None:
                try:
                    urls.append(filebackends.BackendURL.fromString(path))
                except KeyError:
                    logger.warning("Unsupported MPD URL type: {}".format(path))
            else:
                #TODO support multiple sources
                #if len(db.query("SELECT element_id FROM {p}files WHERE url=?", 'file:///' + path)):
                #    urls.append(filebackends.BackendURL.fromString("file:///" + path))
                #else:
                urls.append(mpdfilebackend.MPDURL("mpd://" + self.name + "/" + path))
        return urls
    
                    
    def treeActions(self):
        yield self.separator
        yield self.updateDBAction
        yield self.configOutputsAction
    

    def registerFrontend(self, obj):
        self._numFrontends += 1
        if self._numFrontends == 1:
            self.connectBackend()

    
    def unregisterFrontend(self, obj):
        self._numFrontends -= 1
        if self._numFrontends == 0 and self.connectionState == player.CONNECTED:
            self.disconnectClient()
    
    
    def setPlaylist(self, urls):
        with self.getClient() as client:
            client.clear()
            self.playlistVersion += 1
            self.mpdPlaylist = []
            self.insertIntoPlaylist(0, urls)
    
    
    def insertIntoPlaylist(self, pos, urls):
        """Insert *urls* into the MPD playlist at position *pos*.
        
        This methode raises a player.InsertError if not all of the files could be added to MPDs
        playlist, which happens if the URL is not known to MPD. The list of URls successfully
        inserted is contained in the error object's *successfulURLs* attribute.
        """
        with self.getClient() as client:
            inserted = []
            try:
                isEnd = (pos == len(self.mpdPlaylist))
                for position, url in enumerate(urls, start=pos):
                    if isEnd:
                        client.add(url.path)
                        self.playlistVersion += 1
                    else:
                        client.addid(url.path, position)
                        self.playlistVersion += 2
                    self.mpdPlaylist[position:position] = [url.path]
                    inserted.append(url)
            except mpd.CommandError:
                raise player.InsertError('Could not insert all files', inserted)
    
    
    def removeFromPlaylist(self, begin, end):
        with self.getClient() as client:
            del self.mpdPlaylist[begin:end]
            client.delete((begin,end))
            self.playlistVersion += 1
    
        
    def move(self, fromOffset, toOffset):
        if fromOffset == toOffset:
            return
        with self.getClient() as client:
            path = self.mpdPlaylist.pop(fromOffset)
            self.mpdPlaylist.insert(toOffset, path)
            client.move(fromOffset, toOffset)
            self.playlistVersion += 1
    
    
    def configurationWidget(self, parent):
        """Return a config widget, initialized with the data of the given *profile*."""
        return MPDConfigWidget(self, parent)
    
    
    def getInfo(self, path):
        """Query MPD to get tags & length of the file at *path* (relative to this MPD instance).
        
        Since MPD connection is delegated to a subthread, this method might be slow.
        """
        with self.getClient() as client:
            info = client.listallinfo(path)[0]
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
        """Open a dialog to select the active audio outputs MPD uses."""
        dialog = QtGui.QDialog(application.mainWindow)
        layout = QtGui.QVBoxLayout()
        layout.addWidget(QtGui.QLabel(self.tr("Choose which audio outputs to use:")))
        checkboxes = []
        for output in sorted(self.outputs, key=lambda out:out["outputid"]):
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
            for checkbox, output in zip(checkboxes, self.outputs):
                if output["outputenabled"] == "0" and checkbox.isChecked():
                    with self.getClient() as client:
                        client.enableoutput(output["outputid"])
                elif output["outputenabled"] == "1" and not checkbox.isChecked():
                    with self.getClient() as client:
                        client.disableoutput(output["outputid"])
    
    
    def __str__(self):
        return "MPDPlayerBackend({})".format(self.name)



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
        self.hostEdit.setText(profile.host)
        self.portEdit.setText(str(profile.port))
        self.passwordEdit.setText(profile.password)
        self.passwordVisibleBox.setChecked(len(profile.password) == 0)
    
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
        return [host, port, password] != [self.profile.host, self.profile.port, self.profile.password]
        
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
    