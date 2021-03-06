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

import re
import time
import select
import contextlib
import os.path

try:
    import mpd
    # Disable the 'Calling <this or that>' messages
    mpd.logger.setLevel('INFO')
except ImportError:
    raise ImportError("python-mpd2 not installed.")

import pkg_resources
mpd_version = [int(x) for x in pkg_resources.get_distribution("python-mpd2").version.split(".")]
if mpd_version < [0, 5, 1]:
    raise ImportError("The installed version of python-mpd2 is too old. Maestro needs at least "
                      "python-mpd2-0.5.1 to function properly.")

from PyQt5 import QtCore, QtGui, QtWidgets

from maestro import application, player, logging, profiles, stack
from maestro.gui.misc import lineedits
from maestro.core import tags, urls
from maestro.widgets.playlist import model

translate = QtCore.QCoreApplication.translate


def enable():
    profiles.category('playback').addType(profiles.ProfileType(
        name='mpd', title=translate('MPDPlayerBackend', 'MPD'),
        profileClass=MPDPlayerBackend,
    ))
    urls.fileBackends.append(MPDFile)


def disable():
    profiles.category('playback').removeType('mpd')
    urls.fileBackends.remove(MPDFile)


class MPDFile(urls.BackendFile):

    scheme = 'mpd'

    def readTags(self):
        mpdProfile = profiles.category('playback').get(self.url.netloc)
        self.tags, self.length = mpdProfile.getInfo(self.url.path[1:])


MPDState = {item.name.lower(): item for item in player.PlayState}

            
class MPDPlayerBackend(player.PlayerBackend):
    """Player backend to control an MPD server.
    
    The MPD client is implemented using the "idle" command of MPD, which causes the socket to block
    until some change is reported by MPD. We use the select method to continuously (by a timer with
    short timeout) check if we can read from the socket, i.e. the idle command has something to
    report (see implementation of the checkIdle function).
    
    The playlist, as reported by MPD, is stored in the attribute *mpdPlaylist" by means of a list
    of strings (paths relative to MPD collection folder). The backend keeps this in sync with MPD,
    updating it whenever a change is reported by MPD (via the idle command), or the Maestro user issues
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
        self.playlist = model.PlaylistModel(self, stack=self.stack)

        if state is None:
            state = {}
        self.host = state.get('host', 'localhost')
        self.port = state.get('port', 6600)
        self.password = state.get('password', '')
        self.path = state.get('path', '')
        
        # actions
        self.separator = QtWidgets.QAction("MPD", self)
        self.separator.setSeparator(True)
        self.updateDBAction = QtWidgets.QAction(self.tr("Update Database"), self)
        self.updateDBAction.triggered.connect(self.updateDB)
        self.configOutputsAction = QtWidgets.QAction(self.tr("Audio outputs..."), self)
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
        self._state = player.PlayState.Stop
        self._currentStart = 0
        self._volume = 0
        self.seekRequest = None
        self.outputs = None
        self.client = None

    def save(self):
        return {'host': self.host, 'port': self.port, 'password': self.password, 'path': self.path}
    
    def setConnectionParameters(self, host, port, password):
        """Change the connection parameters. Issues a reconnect with the new ones."""
        self.host = host
        self.port = port
        self.password = password
        if self.connectionState == player.ConnectionState.Connected:
            self.disconnectClient()
        self.connectBackend()
        self.emitChange()
        
    def setPath(self, path):
        """Change the path where Maestro believes the MPD music folder to be."""
        if path != self.path:
            self.path = path
            self.emitChange()
            # Changing the path probably means that mpd:// urls become file:// urls
            if self.playlist.root.hasContents():
                self.playlist.resetFromUrls(self.makeUrls(self.mpdPlaylist),
                                            updateBackend='never') 
                self.stack.reset()  # avoid trouble
    
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
        self.connectionState = player.ConnectionState.Connected
        self.connectionStateChanged.emit(player.ConnectionState.Connected)
        self.client.send_idle()
        self.idling = True
        self.idleTimer.start()
    
    def disconnectClient(self, skipSocket=False):
        """Disconnect from MPD.
        
        If *skipSocket* is True, nothing is done on the socket (useful after connection failures).
        """ 
        logging.debug(__name__, "calling MPD disconnect host {}".format(self.host))
        if self.idleTimer.isActive():
            self.idleTimer.stop()
        if not skipSocket:
            self.checkIdle(False)
            self.client.close()
            self.client.disconnect()
        self.client = None
        self.connectionState = player.ConnectionState.Connected
        self.connectionStateChanged.emit(player.ConnectionState.Disconnected)
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
            from ...gui.dialogs import warning
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
        if len(changed) > 0:
            logging.warning(__name__, 'unhandled MPD changes: {}'.format(changed))
    
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
        logging.debug(__name__, "detected new plVersion: {}-->{}".format(self.playlistVersion, newVersion))
        
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
            logging.warning(__name__, 'no changes???')
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
            self.playlist.setCurrent(current)
            self.currentChanged.emit(current)
        
        if "elapsed" in self.mpdStatus:
            elapsed = float(self.mpdStatus["elapsed"])
            self._currentStart = time.time() - elapsed
            self.elapsedChanged.emit(self.elapsed())
             
        # check for a change of playing state
        state = MPDState[self.mpdStatus["state"]]
        if state != self._state:
            self._state = state
            self.stateChanged.emit(state)
            # if state == player.PlayState.Stop:
            #     self.playlist.setCurrent(None)
            #     self.currentChanged.emit(None)
        self._state = state

    def updateOutputs(self):
        """Check if the selected audio outputs have been changed by MPD."""
        outputs = self.client.outputs()
        if outputs != self.outputs:
            self.outputs = outputs
    
    def state(self):
        return self._state
    
    def setState(self, state):
        with self.getClient() as client:
            if state is player.PlayState.Play:
                client.play()
            elif state is player.PlayState.Pause:
                client.pause(1)
            elif state is player.PlayState.Stop:
                client.stop()
    
    def volume(self):
        return self._volume
    
    def setVolume(self, volume):
        with self.getClient() as client:
            try:
                client.setvol(volume)
            except mpd.CommandError:
                logging.error(__name__, "Problems setting volume. Does MPD allow setting the volume?")

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
        if self._state is player.PlayState.Stop:
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
        if newState is player.PlayState.Play:
            self.elapsedTimer.start()
        else:
            self.elapsedTimer.stop()
    
    def updateDB(self, path=None):
        """Update MPD's database. An optional *path* can be given to only update that file/dir."""
        with self.getClient() as client:
            if path:
                client.update(path)
            else:
                client.update()
    
    def makeUrls(self, paths):
        """Create Maestro URLs for the given paths reported by MPD.
        
        MPD paths of non-default form (i.e. proto://path) are mapped to URLs with scheme 'proto'.
        If *path* refers to a normal file in MPDs database, a URL with scheme 'MPD' is created.  If the file
        is also found on the local filesystem, then a normal 'file' URL is returned.
        """
        returned = []
        for path in paths:
            if re.match("[a-zA-Z]{2,5}://", path) is not None:
                returned.append(urls.URL(path))
            else:
                if os.path.exists(os.path.join(self.path, path)):
                    returned.append(urls.URL.fileURL(os.path.join(self.path, path)))
                else:
                    returned.append(urls.URL('mpd://{}/{}'.format(self.name, path)))
        return returned
        
    def treeActions(self):
        yield self.separator
        yield self.updateDBAction
        yield self.configOutputsAction

    def registerFrontend(self, obj):
        super().registerFrontend(obj)
        if self.numFrontends == 1:
            self.connectBackend()
    
    def unregisterFrontend(self, obj):
        super().unregisterFrontend(obj)
        if self.numFrontends == 0 and self.connectionState is player.ConnectionState.Connected:
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
                urls = list(urls)
                isEnd = (pos == len(self.mpdPlaylist))
                for position, url in enumerate(urls, start=pos):
                    if url.path.startswith(self.path):
                        path = os.path.relpath(url.path, self.path)
                    else: path = url.path
                    if isEnd:
                        client.add(path)
                        self.playlistVersion += 1
                    else:
                        client.addid(path, position)
                        self.playlistVersion += 2
                    self.mpdPlaylist[position:position] = [path]
                    inserted.append(url)
            except mpd.CommandError as e:
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

    @classmethod
    def configurationWidget(cls, profile, parent):
        """Return a config widget, initialized with the data of the given *profile*."""
        return MPDConfigWidget(profile, parent)
    
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
        dialog = QtWidgets.QDialog(application.mainWindow)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(QtWidgets.QLabel(self.tr("Choose which audio outputs to use:")))
        checkboxes = []
        for output in sorted(self.outputs, key=lambda out:out["outputid"]):
            checkbox = QtWidgets.QCheckBox(output["outputname"])
            checkbox.setChecked(output["outputenabled"] == "1")
            checkboxes.append(checkbox)
            layout.addWidget(checkbox)
        dbb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Ok)
        layout.addWidget(dbb)
        dbb.accepted.connect(dialog.accept)
        dbb.rejected.connect(dialog.reject)
        dialog.setLayout(layout)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            for checkbox, output in zip(checkboxes, self.outputs):
                if output["outputenabled"] == "0" and checkbox.isChecked():
                    with self.getClient() as client:
                        client.enableoutput(output["outputid"])
                elif output["outputenabled"] == "1" and not checkbox.isChecked():
                    with self.getClient() as client:
                        client.disableoutput(output["outputid"])
    
    def __str__(self):
        return "MPDPlayerBackend({})".format(self.name)


class MPDConfigWidget(QtWidgets.QWidget):
    """Widget to configure playback profiles of type MPD."""
    def __init__(self, profile, parent):
        super().__init__(parent)
        
        layout = QtWidgets.QVBoxLayout(self)
        formLayout = QtWidgets.QFormLayout()
        layout.addLayout(formLayout)
        
        self.hostEdit = QtWidgets.QLineEdit()
        formLayout.addRow(self.tr("Host:"), self.hostEdit)
        
        self.portEdit = QtWidgets.QLineEdit()
        self.portEdit.setValidator(QtGui.QIntValidator(0, 65535, self))
        formLayout.addRow(self.tr("Port:"), self.portEdit)
        
        self.passwordEdit = QtWidgets.QLineEdit()
        formLayout.addRow(self.tr("Password:"), self.passwordEdit)
        
        self.passwordVisibleBox = QtWidgets.QCheckBox()
        self.passwordVisibleBox.toggled.connect(self._handlePasswordVisibleBox)
        formLayout.addRow(self.tr("Password visible?"), self.passwordVisibleBox)
        
        self.pathEdit = lineedits.PathLineEdit(self.tr("Path to music folder"), pathType='existingDirectory')
        formLayout.addRow(self.tr("Path to music folder:"), self.pathEdit)
        
        self.saveButton = QtWidgets.QPushButton(self.tr("Save"))
        self.saveButton.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.saveButton.setEnabled(False)
        self.saveButton.clicked.connect(self.save)
        layout.addWidget(self.saveButton)
        layout.addStretch(1)
        
        self.setProfile(profile)
        
        self.hostEdit.textChanged.connect(self._handleChange)
        self.portEdit.textChanged.connect(self._handleChange)
        self.passwordEdit.textChanged.connect(self._handleChange)
        self.pathEdit.textChanged.connect(self._handleChange)

    def setProfile(self, profile):
        """Change the profile whose data is displayed."""
        self.profile = profile
        self.hostEdit.setText(profile.host)
        self.portEdit.setText(str(profile.port))
        self.passwordEdit.setText(profile.password)
        self.passwordVisibleBox.setChecked(len(profile.password) == 0)
        self.pathEdit.setText(profile.path)

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
        path = self.pathEdit.text()
        return (
            host != self.profile.host or
            port != self.profile.port or
            password != self.profile.password or
            path != self.profile.path
        )

    def save(self):
        """Really change the profile."""
        host = self.hostEdit.text()
        port = int(self.portEdit.text())
        password = self.passwordEdit.text()
        path = self.pathEdit.text()
        self.profile.setConnectionParameters(host, port, password)
        self.profile.setPath(path)
        profiles.category('playback').save()
        self.saveButton.setEnabled(False)

    def _handlePasswordVisibleBox(self, checked):
        """Change whether the password is visible in self.passwordEdit."""
        self.passwordEdit.setEchoMode(QtWidgets.QLineEdit.Normal if checked else QtWidgets.QLineEdit.Password)

    def okToClose(self):
        """In case of unsaved configuration data, ask the user what to do."""
        if self.isModified():
            button = QtWidgets.QMessageBox.question(
                                    self, self.tr("Unsaved changes"),
                                    self.tr("MPD configuration has been modified. Save changes?"),
                                    QtWidgets.QMessageBox.Abort | QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            if button == QtWidgets.QMessageBox.Abort:
                return False
            elif button == QtWidgets.QMessageBox.Yes:
                self.save()
            else:
                self.setProfile(self.profile) # reset
        return True
