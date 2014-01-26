# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2013-2014 Martin Altmayer, Michael Helmling
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

"""This module is in charge of the actual ripping process of the audiocd plugin.
"""

import tempfile
import os, shutil
from glob import glob
from os.path import dirname, exists,join

from PyQt4 import QtCore, QtGui

from omg import utils, database as db, logging
from omg.core import levels
from omg.gui import mainwindow
from omg.filebackends.filesystem import RealFile, FileURL

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

finishedTracks = []
activeRipper = None

class Ripper(QtCore.QObject):
    
    trackFinished = QtCore.pyqtSignal(str, int, str)
    
    def __init__(self, device, discid, tracks=None):
        super().__init__()
        self.device = device
        self.discid = discid
        self.tmpdir = tempfile.mkdtemp(prefix='omg_rip')
        self.encodingProcess = self.ripProcess = None
        QtGui.qApp.aboutToQuit.connect(self.cleanup)
        global activeRipper
        if tracks is not None:
            self.trackArg = "{}-{}".format(min(tracks), max(tracks))
            #TODO: really only rip needed files. unfortunatelly cdparanoia can't select
            # individual tracks, only ranges :(
        else:
            self.trackArg = "1-"
        activeRipper = self
        
    def start(self):
        logger.debug("starting to rip tracks {} from {}".format(self.trackArg, self.device))
        self.watcher = QtCore.QFileSystemWatcher([self.tmpdir])
        self.watcher.directoryChanged.connect(self._handleDirChanged)
        self.ripProcess = QtCore.QProcess()
        self.ripProcess.setWorkingDirectory(self.tmpdir)
        self.ripProcess.finished.connect(self._handleRipperFinished)
        self.ripProcess.start("cdparanoia",
                              ["-q", "-B", "-d", self.device, self.trackArg])
        mainwindow.mainWindow.statusBar().addWidget(
            QtGui.QLabel("ripping disc in drive {} ...".format(self.device)))
        
    def _handleDirChanged(self, dir):
        wavs = glob(join(self.tmpdir, "track*.wav"))

    def _handleRipperFinished(self):
        tracks = sorted(os.listdir(self.tmpdir))
        print('ripper finisehd. tracks: {}'.format(tracks))
        import re
        regex = re.compile("track([0-9]+)\\.cdda\\.wav")
        self.tracksToEncode = [(int(regex.findall(track)[0]), track) for track in tracks]
        self.lastEncoded = None
        self.encode()
    
    def encode(self):
        print('encode')
        if self.lastEncoded:
            tracknr, wavFile, encodedFile = self.lastEncoded
            os.remove(wavFile)
            try:
                ans = db.query("SELECT element_id FROM {}files WHERE url LIKE 'audiocd://{}.{}/%'"
                               .format(db.prefix, self.discid, tracknr)).getSingle()
                print("found file: {}".format(ans))
                elem = levels.real.collect(ans)
                levels.real.stack.push(InsertRippedFileCommand(elem, encodedFile))
                
            except db.sql.EmptyResultException:
                print("adding finished Track")
                finishedTracks.append((self.discid, tracknr, encodedFile))
            self.lastEncoded = None

        if len(self.tracksToEncode) == 0:
            return
        # start next encoder if there are tracks left
        tracknr, track = self.tracksToEncode.pop(-1)
        print('encoding track: {}'.format(track))
        self.encodingProcess = QtCore.QProcess()
        self.encodingProcess.setWorkingDirectory(self.tmpdir)
        self.encodingProcess.finished.connect(self.encode)
        self.lastEncoded = tracknr, join(self.tmpdir, track), join(self.tmpdir, track[:-3] + "flac")
        self.encodingProcess.start("flac", [track])
        
    def cleanup(self):
        if self.ripProcess:
            self.ripProcess.finished.disconnect(self._handleRipperFinished)
        for proc in self.ripProcess, self.encodingProcess:
            if proc and proc.state() != proc.NotRunning:
                proc.terminate()
                proc.waitForFinished()

class InsertRippedFileCommand:
    
    def __init__(self, element, tmpPath):
        self.element = element
        self.tmpPath = tmpPath
        self.oldUrl = self.element.url
        self.newUrl = FileURL('file:///' + self.element.url.targetPath)
        self.text = translate("AudioCD Plugin", "Ripped Track {}".format(element.url.tracknr))
        
    def redo(self):
        targetAbs = utils.absPath(self.element.url.targetPath)
        if not exists(dirname(targetAbs)):
            os.makedirs(dirname(targetAbs))
        shutil.move(self.tmpPath, targetAbs)
        tmpFile = RealFile(self.newUrl)
        tmpFile.readTags()
        length = tmpFile.length
        tmpFile.tags = self.element.tags.withoutPrivateTags(copy=True)
        tmpFile.specialTags = {"tracknumber" : "{:02d}".format(self.element.url.tracknr)}
        tmpFile.saveTags()
        db.query("UPDATE {p}files SET url=?,length=? WHERE element_id=?",
                 str(self.newUrl), length, self.element.id)
        for level in levels.allLevels:
            if self.element.id in level:
                levelElem = level[self.element.id]
                levelElem.length = length
                levelElem.url = self.newUrl
                level.emitEvent(dataIds=[self.element.id])
        levels.real.emitFilesystemEvent(added=[self.element])
        
    def undo(self):
        if not exists(dirname(self.tmpPath)):
            os.makedirs(dirname(self.tmpPath))
        shutil.move(utils.absPath(self.element.url.path), self.tmpPath)
        db.query("UPDATE {}files SET url=? WHERE element_id=?".format(db.prefix),
                 str(self.oldUrl), self.element.id)
        for level in levels.allLevels:
            if self.element.id in level:
                levelElem = level[self.element.id]
                levelElem.url = self.oldUrl
                level.emitEvent(dataIds=[self.element.id])
        levels.real.emitFilesystemEvent(deleted=[self.element])

def fileChangerHook(level,elements):
    """Commit-hook for the real level."""
    aFiles = list(filter(lambda el: el.isFile() and el.url.scheme == "audiocd", elements))
    for i in reversed(range(len(finishedTracks))):
        discid, tracknr, encodedFile = finishedTracks[i] 
        for file in aFiles:
            if file.url.parsedUrl.netloc == "{}.{}".format(discid, tracknr):
                level.stack.push(InsertRippedFileCommand(file, encodedFile))
                del finishedTracks[i]

    