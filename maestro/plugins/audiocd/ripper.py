# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2013-2015 Martin Altmayer, Michael Helmling
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

import os, shutil, re, tempfile
from os.path import dirname, exists,join
import subprocess
from PyQt4 import QtCore, QtGui

from ... import utils, database as db, logging, config
from ...core import levels
from ...gui import mainwindow
from ...filebackends.filesystem import RealFile, FileURL

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

finishedTracks = []
activeRipper = None

fromToRe = re.compile(r'from sector\s+(?P<fromSec>[0-9]+).*track\s+(?P<fromTrack>[0-9]+)\s'
                          '.*\n.*to sector\s+(?P<toSec>[0-9]+).*track\s+(?P<toTrack>[0-9]+)')
statusRe = re.compile(r'^##:\s-?[0-9]+\s\[(\w+)\]\s@\s([0-9]+)', re.M)
currentRe = re.compile(r'outputting\sto\strack([0-9]+)\.')

class RipperStatusWidget(QtGui.QWidget):

    cancelled = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.progress = QtGui.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setValue(0)
        self.progress.setFormat(self.tr('starting ripper...'))
        closeButton = QtGui.QToolButton()
        closeButton.setIcon(self.style().standardIcon(QtGui.QStyle.SP_BrowserStop))
        closeButton.clicked.connect(self.cancelled)
        layout = QtGui.QHBoxLayout()
        layout.addWidget(self.progress, 0)
        layout.addWidget(closeButton)
        self.setLayout(layout)
        self.fromSector = self.toSector = None

    def setSectorRange(self, fromSector, toSector):
        self.fromSector, self.toSector = fromSector, toSector
        self.progress.setRange(fromSector, toSector)
        self.progress.setFormat(self.tr('ripping ...'))

    def setByte(self, byte):
        val = int((byte+1)/2352*2) + 1
        self.progress.setValue(val)



class Ripper(QtCore.QObject):

    currentTrackChanged = QtCore.pyqtSignal(int)
    currentByteChanged = QtCore.pyqtSignal(int)

    def __init__(self, device, discid, fromTrack=1, toTrack=None):
        super().__init__()
        self.device = device
        self.discid = discid
        self.tmpdir = tempfile.mkdtemp(prefix='maestro_rip')
        self.encodingProcess = self.ripProcess = None
        QtGui.qApp.aboutToQuit.connect(self.cleanup)
        global activeRipper
        self.fromTrack, self.toTrack = fromTrack, toTrack
        self.currentTrack = None
        activeRipper = self

    def start(self):
        self.watcher = QtCore.QFileSystemWatcher([self.tmpdir])
        self.ripProcess = QtCore.QProcess()
        self.ripProcess.setWorkingDirectory(self.tmpdir)
        self.ripProcess.setReadChannelMode(QtCore.QProcess.MergedChannels)
        self.ripProcess.readyRead.connect(self.parseParanoiaOutput)
        self.ripProcess.finished.connect(self.handleRipFinish)
        trackArg = str(self.fromTrack) + '-' + (str(self.toTrack) if self.toTrack else '')
        self.ripProcess.start('cdparanoia', ['-B', '-e', '-d', self.device, trackArg])
        self.statusWidget = RipperStatusWidget()
        mainwindow.mainWindow.statusBar().addWidget(self.statusWidget)
        self.currentByteChanged.connect(self.statusWidget.setByte)
        self.statusWidget.cancelled.connect(self.cancel)

    def parseParanoiaOutput(self):
        procOut = self.ripProcess.readAll().data().decode()
        if self.statusWidget.fromSector is None:
            found = fromToRe.search(procOut)
            if found:
                self.statusWidget.setSectorRange(*map(int, found.group('fromSec', 'toSec')))
                toTrack = int(found.group('toTrack'))
                if self.toTrack is not None:
                    assert self.toTrack == toTrack
                self.toTrack = toTrack
        found = statusRe.findall(procOut)
        for mode, byte in found:
            if mode == 'wrote':
                self.currentByteChanged.emit(int(byte))
            elif mode == 'finished':
                self.encodeTrack(self.currentFile, self.currentTrack)
        found = currentRe.search(procOut)
        if found:
            self.currentFile = 'track{}.cdda.wav'.format(found.group(1))
            self.currentTrack = int(found.group(1))
            self.currentTrackChanged.emit(self.currentTrack)

    def encodeTrack(self, wavName, tracknumber):
        self.encodingProcess = QtCore.QProcess()
        self.encodingProcess.setWorkingDirectory(self.tmpdir)
        self.encodingProcess.finished.connect(lambda: self.replaceTrack(wavName, tracknumber))
        self.encodingProcess.start("flac", [wavName])

    def replaceTrack(self, wavName, tracknumber):
        os.remove(join(self.tmpdir, wavName))
        flacPath = join(self.tmpdir, wavName[:-3] + 'flac')
        try:
            ans = db.query("SELECT element_id FROM {}files WHERE url LIKE 'audiocd://{}.{}/%'"
                           .format(db.prefix, self.discid, tracknumber)).getSingle()
            elem = levels.real.collect(ans)
            levels.real.stack.push(InsertRippedFileCommand(elem, flacPath))
        except db.EmptyResultException:
            finishedTracks.append((self.discid, tracknumber, flacPath))
        if tracknumber == self.toTrack:
            mainwindow.mainWindow.statusBar().removeWidget(self.statusWidget)
            self.encodingProcess = self.ripProcess = None

    def cleanup(self):
        for proc in self.ripProcess, self.encodingProcess:
            if proc and proc.state() != proc.NotRunning:
                proc.terminate()
                proc.waitForFinished()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def handleRipFinish(self, exitCode, exitStatus):
        if exitCode == 0 and config.options.audiocd.eject:
            try:
                subprocess.Popen(['eject', self.device])
            except FileNotFoundError:
                # 'eject' might not be installed or not working ... well,
                pass

    def cancel(self):
        for proc in self.ripProcess, self.encodingProcess:
            if proc and proc.state() != proc.NotRunning:
                proc.terminate()
        mainwindow.mainWindow.statusBar().removeWidget(self.statusWidget)


class InsertRippedFileCommand:
    """Command to replace a file of backend type `AudioCDURL` by the ripped real file.
    """
    #TODO: when this happens while rename dialog is open, the file is not renamed properly
    def __init__(self, element, tmpPath):
        self.element = element
        self.tmpPath = tmpPath
        self.oldUrl = self.element.url
        self.newUrl = FileURL('file://' + self.element.url.targetPath)
        self.text = translate("AudioCD Plugin", "Ripped Track {}".format(element.url.tracknr))

    def redo(self):
        target = self.element.url.targetPath
        if not exists(dirname(target)):
            os.makedirs(dirname(target))
        shutil.move(self.tmpPath, target)
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
        shutil.move(self.element.url.path, self.tmpPath)
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

