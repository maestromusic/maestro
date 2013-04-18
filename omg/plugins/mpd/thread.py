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

import time
import socket, threading

import mpd
from PyQt4 import QtCore

from omg import logging, player

logger = logging.getLogger(__name__)

MPD_STATES = { 'play': player.PLAY, 'stop': player.STOP, 'pause': player.PAUSE}
CONNECTION_TIMEOUT = 10 # time in seconds before an initial connection to MPD is given up


class MPDThread(QtCore.QThread):
    """Helper class for the MPD player backend; idles for changes on the server.
    
    The MPDThread opens a connection to MPD and immediately switches to IDLE mode, waiting for
    messages from MPD indicating some state change. In that case the thread will emit the
    *changeFromMPD* signal.
    """
    
    changeFromMPD = QtCore.pyqtSignal(str, object)
    
    def __init__(self, backend, host, port, password):
        super().__init__(None)
        self.backend = backend
        self.host, self.port, self.password = host, port, password
        self.playlistVersion = self.state = None
        self.current = self.elapsed = None
        self.currentLength = self.volume = None
        self.seekRequest = None
        self.connected = False
        self.outputs = None
        self.shouldConnect = threading.Event()
        self.idler = mpd.MPDClient()
        
    def updatePlaylist(self):
        """Update the playlist when it has changed on the server.
        
        Currently, two special cases are detected: Insertion of consecutive songs,
        and removal of consecutive songs. For those cases, the messages "insert" and
        "remove", respectively, are emitted.
        
        In any other case, a complete playlist change message is emitted.
        """
        newVersion = int(self.mpd_status["playlist"])
        if newVersion == self.playlistVersion:
            return
        oldVersion = self.playlistVersion
        logger.debug("detected new plVersion: {}-->{}".format(oldVersion, newVersion))
        
        if oldVersion is None:
            # this happens only on initialization. Here we don't create an UndoCommand
            self.mpd_playlist = [x["file"] for x in self.idler.playlistinfo()]
            self.playlistVersion = newVersion
            return
        
        changes = [(int(a["pos"]),a["file"]) for a in self.idler.plchanges(oldVersion)]
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
                self.mpd_playlist[firstInserted:firstInserted] = [file for pos, file in changes[:numInserted]]
                self.changeFromMPD.emit('insert', changes[:numInserted])
                return
        if len(changes) == 0:
            logger.warning('no changes???')
            return
        # other cases: update self.mpd_playlist and emit a generic "playlist" change message.
        reallyChange = False
        for pos, file in sorted(changes):
            if pos < len(self.mpd_playlist):
                if self.mpd_playlist[pos] != file:
                    reallyChange = True
                self.mpd_playlist[pos] = file
            else:
                reallyChange = True
                self.mpd_playlist.append(file)
        if not reallyChange:
            # this happens e.g. when a stream is updated
            return
        self.changeFromMPD.emit('playlist', self.mpd_playlist[:])
    
    def updateMixer(self):
        volume = int(self.mpd_status['volume'])
        if volume != self.volume:
            self.volume = volume
            self.changeFromMPD.emit('volume', volume)
    
    def updatePlayer(self, emit=True):
        # check if current song has changed. If so, update length of current song
        if "song" in self.mpd_status:
            current = int(self.mpd_status["song"])
        else:
            current = None
        if "elapsed" in self.mpd_status:
            self.elapsed = float(self.mpd_status["elapsed"])
            if emit:
                self.changeFromMPD.emit('elapsed', self.calculateStart(self.elapsed))
        else:
            self.elapsed = None
        
        if current != self.current:
            self.current = current
            if current != None:
                self.mpd_current = self.idler.currentsong()
                if "time" in self.mpd_current:
                    self.currentLength = int(self.mpd_current["time"])
                else:
                    self.currentLength = -1
            else:
                self.currentLength = 0 # no current song
            if emit:
                self.changeFromMPD.emit('current', (self.current, self.currentLength))
             
        # check for a change of playing state
        state = MPD_STATES[self.mpd_status["state"]]
        if state != self.state:
            if emit:
                self.changeFromMPD.emit('state', state)
            if state == player.STOP:
                self.currentLength = 0
                self.current = None
                if emit:
                    self.changeFromMPD.emit('current', (None, 0))
        self.state = state
    
    def calculateStart(self, elapsed):
        if elapsed is None:
            return None
        return time.time() - elapsed
    
    def updateOutputs(self, emit=True):
        outputs = self.idler.outputs()
        if emit and outputs != self.outputs:
            self.changeFromMPD.emit('outputs', outputs)
        self.outputs = outputs
        
    def connect(self):
        self.idler.connect(self.host, self.port, CONNECTION_TIMEOUT)
        self.mpd_status = self.idler.status()
        self.updateMixer()
        self.updatePlaylist()
        self.updatePlayer(False)
        self.updateOutputs(False)
        self.changeFromMPD.emit('connect', (self.mpd_playlist[:], self.current,
                                            self.currentLength, self.calculateStart(self.elapsed),
                                            self.state, self.volume, self.outputs))
        self.connected = True  
    
    def disconnect(self):
        if not self.connected:
            return
        self.connected = False
        self.idler.noidle()
        self.idler.disconnect()
        
        logger.debug('mpd thread disconnected')
        self.changeFromMPD.emit('disconnect', None)
        
    def run(self):
        while self.shouldConnect.is_set():
            try:
                if not self.connected:
                    self.connect()
                self.watchMPDStatus()
            except (mpd.ConnectionError, socket.error):
                if not self.shouldConnect.is_set():
                    return
                logger.debug('MPD {} could not connect'.format(self.host))
                self.connected = False
                self.changeFromMPD.emit('disconnect', 'no connection to MPD host')
                self.sleep(5)
        
    def quit(self):
        self.disconnect()
        super().quit()
    
    def watchMPDStatus(self):
        while True:
            if not self.connected:
                return
            self.idler.send_idle()
            changed = self.idler.fetch_idle()
            with self.playlistLock:
                self.mpd_status = self.idler.status()
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
                elif 'output' in changed:
                    self.updateOutputs()
                    changed.remove('output')
                if len(changed) > 0:
                    logger.warning('unhandled MPD changes: {}'.format(changed))
