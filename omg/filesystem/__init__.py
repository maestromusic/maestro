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

import os.path, subprocess, hashlib, datetime, threading, queue, time

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from .. import logging, config, utils, database as db, filebackends
from ..core import levels

logger = logging.getLogger(__name__)

synchronizer = None
enabled = False

NO_MUSIC = 0
HAS_FILES = 1
HAS_NEW_FILES = 2
PROBLEM = 4

def init():
    global synchronizer, notifier, null, enabled
    import _strptime
    if config.options.filesystem.disable:
        return
    synchronizer = FileSystemSynchronizer()
    synchronizer.eventThread.start()
    levels.real.filesRenamed.connect(synchronizer.handleRename)
    levels.real.filesAdded.connect(synchronizer.handleAdd)
    levels.real.filesRemoved.connect(synchronizer.handleRemove)
    null = open(os.devnull)
    enabled = True
    logger.debug("Filesystem module initialized in thread {}".format(QtCore.QThread.currentThread()))
    
def shutdown():
    """Terminates this module; waits for all threads to complete."""
    global synchronizer, enabled
    if config.options.filesystem.disable or synchronizer is None:
        return
    enabled = False
    logger.debug("Filesystem module: received shutdown() command")
    levels.real.filesRenamed.disconnect(synchronizer.handleRename)
    levels.real.filesAdded.disconnect(synchronizer.handleAdd)
    levels.real.filesRemoved.disconnect(synchronizer.handleRemove)
    synchronizer.should_stop.set()
    synchronizer.eventThread.exit()
    synchronizer.eventThread.wait()
    synchronizer = None
    null.close()
    logger.debug("Filesystem module: shutdown complete")

def getFolderState(path):
    """Return the state of a given folder, or 'unknown' if it can't be obtained.
    """
    if enabled and synchronizer.initialized.is_set():
        try:
            state = synchronizer.directories[path].state
            if state & PROBLEM:
                return 'problem'
            elif state & HAS_NEW_FILES:
                return 'unsynced'
            elif state & HAS_FILES:
                return 'ok'
            else:
                return 'nomusic'
        except KeyError:
            pass
    return 'unknown'

def getNewfileHash(url):
    """Return the hash of a file specified by *url* which is not yet in the database.
    
    If the hash is not known, returns None.
    """
    if enabled:
        try:
            return synchronizer.tracks[url].hash
        except KeyError:
            return None
    return None

def computeHash(url):
    """Compute the audio hash of a single file. This method uses
    the "ffmpeg" binary ot extract the first 15 seconds in raw
    PCM format and then creates the MD5 hash of that data. It would
    be nicer to have this either as a plugin with possibly alternative
    methods, or even better use something like
    https://github.com/sampsyo/audioread/tree/master/audioread
    that determines an available backend automatically."""
    if config.options.filesystem.dump_method == "ffmpeg":
        proc = subprocess.Popen(
            ['ffmpeg', '-i', url.absPath,
             '-v', 'quiet',
             '-f', 's16le',
             '-t', '15',
             '-'],
            stdout=subprocess.PIPE, stderr=null # this is due to a bug that ffmpeg ignores -v quiet
        )
    else:
        raise ValueError('Dump method"{}" not supported'.format(config.options.filesystem.dump_method))
    data = proc.stdout.readall()
    proc.wait()
    hash = hashlib.md5(data).hexdigest()
    assert hash is not None and len(hash) > 10
    return hash


def mTimeStamp(url):
    """Get the modification timestamp of a file given by *url*.
    
    Returns a datetime.datetime object with timezone UTC.
    """
    return datetime.datetime.fromtimestamp(os.path.getmtime(url.absPath), tz=datetime.timezone.utc).replace(microsecond=0)


class Track:
    def __init__(self, url):
        self.url = url
        self.directory = None
        self.id = self.lastChecked = self.hash = None
        self.problem = False
    
    def __str__(self):
        if self.id is not None:
            return "DB Track[{}](url={})".format(self.id, self.url)
        return ("New Track(url={})".format(self.url))


class Directory:

    def __init__(self, path, parent):
        self.parent = parent
        self.path = path
        self.tracks = []
        self.subdirs = []
        self.state = NO_MUSIC
        if parent is not None:
            parent.subdirs.append(self)
    
    @property    
    def absPath(self):
        return utils.absPath(self.path)
    
    def addTrack(self, track):
        track.directory = self
        self.tracks.append(track)
    
    def updateState(self, considerTracks=True, considerSubdirs=True, recurse=False,
                     signal=None):
        ownState = NO_MUSIC
        if considerTracks:
            for track in self.tracks:
                ownState |= HAS_FILES
                if track.id is None:
                    ownState |= HAS_NEW_FILES
                if track.problem:
                    ownState |= PROBLEM
                    break
        if considerSubdirs:
            for dir in self.subdirs:
                ownState |= dir.state
        if ownState != self.state:
            self.state = ownState
            ret = [self]
            if recurse and self.parent is not None:
                ret += self.parent.updateState(False, True, True, signal)
            if signal is not None:
                signal.emit(self)
            return ret
        return []
            
        
class SynchronizeHelper(QtCore.QObject):
    """Class running in the main event thread to change database and display GUIs."""
    
    def __init__(self):
        super().__init__()
        self.dialogFinished = threading.Event()
    
    @QtCore.pyqtSlot(object)
    def addFileHashes(self, newHashes):
        db.multiQuery("UPDATE {}files SET hash=? WHERE element_id=?"
                      .format(db.prefix), [ (track.hash, track.id) for track in newHashes ]) 

    @QtCore.pyqtSlot(int, object)
    def changeURL(self, id, newUrl):
        from ..gui.dialogs import warning
        from .. import application
        warning(self.tr("Move detected"),
                self.tr("A file was renamed (or moved) outside OMG:\n"
                        "{}".format(str(newUrl))), application.mainWindow)
        db.query('UPDATE {}files SET url=? WHERE element_id=?'.format(db.prefix), str(newUrl), id)
        if id in levels.real.elements:
            levels.real.get(id).url = newUrl
            levels.real.emitEvent([id])
    
    @QtCore.pyqtSlot(list)
    def showLostTracksDialog(self, tracks):
        from . import dialogs
        dialog = dialogs.MissingFilesDialog([track.id for track in tracks])
        dialog.exec_()
        self.dialogFinished.set()
    
class EventThread(QtCore.QThread):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.timer = QtCore.QTimer(self)
        
    def run(self):
        self.timer.start(config.options.filesystem.scan_interval*1000)
        self.exec_()
        db.close()               

class FileSystemSynchronizer(QtCore.QObject):
    
    folderStateChanged = QtCore.pyqtSignal(object)
    initializationComplete = QtCore.pyqtSignal()
    
    hashesComputed = QtCore.pyqtSignal(list)
    moveDetected = QtCore.pyqtSignal(int, object)
    lostTracksDetected = QtCore.pyqtSignal(list)
    
    def __init__(self):
        super().__init__()
        self.should_stop = threading.Event()
        self.initialized = threading.Event()
        
        self.helper = SynchronizeHelper()
        self.eventThread = EventThread(self)
        self.moveToThread(self.eventThread)
        self.moveDetected.connect(self.helper.changeURL)
        self.lostTracksDetected.connect(self.helper.showLostTracksDialog)
        self.eventThread.started.connect(self.init)
        self.eventThread.timer.timeout.connect(self.scanFilesystem)
        self.tracks = {}
        self.dbTracks = set()
        self.dbDirectories = set()
        self.directories = {}

    def loadFolders(self):
        for path, state in db.query(
                    "SELECT path, state FROM {}folders ORDER BY LENGTH(path)".format(db.prefix)):
            parent, basename = os.path.split(path)
            if parent == '' and basename == '':
                dir = Directory(path='', parent=None)                    
            else:
                parent = self.directories[parent]
                dir = Directory(path, parent)
            dir.state = state
            self.directories[dir.path] = dir
            self.dbDirectories.add(dir.path)
    
    def loadDBFiles(self):
        newDirectories = []
        for elid, urlstring, elhash, verified in db.query(
                       "SELECT element_id, url, hash, verified FROM {}files".format(db.prefix)):
            url = filebackends.BackendURL.fromString(urlstring)
            if url.scheme != "file":
                continue
            track = Track(url)
            track.id = elid
            if not db.isNull(elhash):
                track.hash = elhash
            track.verified = db.getDate(verified)
            self.tracks[track.url] = track
            self.dbTracks.add(track.url)
            dir, newDirs = self.getDirectory(os.path.dirname(track.url.path))
            newDirectories += newDirs
            dir.addTrack(track)
        if len(newDirectories) > 0:
            db.multiQuery("INSERT INTO {}folders (path, state) VALUES (?,?)".format(db.prefix),
                          [(dir.path, dir.state) for dir in newDirectories])
    
    def loadNewFiles(self):
        deleteFromNewFiles = []
        for urlstring, elhash, verified in db.query(
                       "SELECT url, hash, verified FROM {}newfiles".format(db.prefix)):
            track = Track(filebackends.BackendURL.fromString(urlstring))
            if track.url in self.dbTracks:
                logger.warning("url {} in both files and newfiles ... ?".format(urlstring))
                deleteFromNewFiles.append((urlstring,))
                continue
            track.hash = elhash
            track.verified = db.getDate(verified)
            self.tracks[track.url] = track
            self.dbTracks.add(track.url)
            dir = self.directories[os.path.dirname(track.url.path)]
            dir.addTrack(track)
        if len(deleteFromNewFiles) > 0:
            db.multiQuery("DELETE FROM {}newfiles WHERE url=?".format(db.prefix),
                          deleteFromNewFiles)  
    
    def init(self):
        db.connect()
        self.loadFolders()
        self.loadDBFiles()
        self.loadNewFiles()
        self.initialized.set()
        self.initializationComplete.emit()
        self.scanFilesystem()
    
    def getDirectory(self, path):
        if path is None:
            return None, []
        if path in self.directories:
            return self.directories[path], []
        parentPath = None if path == "" else os.path.split(path)[0]
        parent, new = self.getDirectory(parentPath)
        dir = Directory(path, parent)
        self.directories[path] = dir
        return dir, new + [dir]
        
    def checkTrack(self, dir, track):
        modified = mTimeStamp(track.url)
        if modified > track.verified:
            logger.debug('found modified track {}: {}>{}'.format(track.url, modified, track.verified))
            if track.id is None:
                logger.debug("just updating hash")
                track.hash = computeHash(track.url)
                track.verified = modified
            else:
                if track.id in levels.real:
                    dbTags = levels.real.get(track.id).tags
                else:
                    dbTags = db.tags(track.id)
                backendFile = track.url.getBackendFile()
                backendFile.readTags()
                if dbTags.withoutPrivateTags() != backendFile.tags:
                    logger.debug('Detected modification on file "{}": tags differ'.format(track.url))
                    self.modifiedTags[track.id] = (dbTags, backendFile.tags)
                    track.problem = True
                else:
                    filehash = computeHash(track.url)
                    if filehash != track.hash:
                        logger.debug("audio data modified!")
                        track.hash = filehash
                        track.verified = modified 
    
    def addTrack(self, dir, url):
        filehash = computeHash(url)
        track = Track(url)
        dir.addTrack(track)
        self.tracks[url] = track
        track.hash = filehash
        track.verified = mTimeStamp(url)
        return track
    
    def storeDirectories(self, directories):
        if len(directories) > 0:
            logger.debug("Storing {} new directories into folders table".format(len(directories)))
            db.multiQuery("INSERT INTO {}folders (path, state) VALUES(?,?)".format(db.prefix),
                          [ (dir.path, dir.state) for dir in directories])
    
    def updateDirectories(self, directories):
        if len(directories) > 0:
            logger.debug("Updating state of {} directories in folders table".format(len(directories)))
            db.multiQuery("UPDATE {}folders SET state=? WHERE path=?".format(db.prefix),
                          [ (dir.state, dir.path) for dir in directories])
    
    def storeNewTracks(self, tracks):
        if len(tracks) > 0:
            logger.debug("Storing {} new tracks into newfiles table".format(len(tracks)))
            db.multiQuery("INSERT INTO {}newfiles (url, hash, verified) VALUES (?,?,?)"
                          .format(db.prefix),
                          [(str(track.url), track.hash,
                            track.verified.strftime("%Y-%m-%d %H:%M:%S"))
                           for track in tracks])
    
    @QtCore.pyqtSlot()
    def scanFilesystem(self):
        """Walks through the collection, updating folders and searching for new files.
        """
        
        #  updates on directories and tracks are collected  and then commited batch-wise
        #  to improve database performance. 
        newDirectories, modifiedDirectories, newTracks = set(), set(), set()
        THRESHOLD = 250  # number of updates bevor database is called
        
        for root, dirs, files in os.walk(config.options.main.collection, topdown=True):
            dirs.sort()
            newTracksInDir = 0
            relPath = utils.relPath(root)
            if relPath == ".":
                relPath = ""
            if relPath in self.dbDirectories:
                self.dbDirectories.remove(relPath)
            dir, newDirs = self.getDirectory(relPath)
            newDirectories.update(newDirs)
            if self.should_stop.is_set():
                break
            for file in files:
                if self.should_stop.is_set():
                    break
                if not utils.hasKnownExtension(file):
                    continue
                url = filebackends.filesystem.FileURL(os.path.join(relPath, file))
                if url in self.tracks:
                    track = self.tracks[url]
                    self.checkTrack(dir, track)
                    if url in self.dbTracks:
                        self.dbTracks.remove(url)
                else:
                    track = self.addTrack(dir, url)
                    newTracks.add(track)
                    newTracksInDir += 1
            for modifiedDir in dir.updateState(True, True, True, signal=self.folderStateChanged):
                logger.debug('state of {} updated'.format(modifiedDir.path))
                if modifiedDir not in newDirectories:
                    modifiedDirectories.add(modifiedDir)
            if newTracksInDir > 0:
                logger.debug("Found {} new tracks in {}".format(newTracksInDir, relPath))
            if len(newTracks) + len(newDirectories) + len(modifiedDirectories) > THRESHOLD:
                db.transaction()
                self.storeDirectories(newDirectories)
                self.updateDirectories(modifiedDirectories)
                self.storeNewTracks(newTracks)
                db.commit()
                newTracks, newDirectories, modifiedDirectories = set(), set(), set()
        db.transaction()
        self.storeDirectories(newDirectories)
        self.updateDirectories(modifiedDirectories)
        self.storeNewTracks(newTracks)
        db.commit()
        if self.should_stop.is_set():
            return
        self.findProblems()
        logger.debug("filesystem scan complete")
      
    def findProblems(self):
        if len(self.dbTracks) > 0:
            missingHashes = {}
            goneNewFiles = []
            for url in self.dbTracks:
                track = self.tracks[url]
                if track.id is None:
                    # case 1: file from newfiles table is gone -> Just remove it
                    goneNewFiles.append(track)
                    track.directory.tracks.remove(track)
                    track.directory.updateState(True, False, True, self.folderStateChanged)
                elif track.hash is not None:
                    # case 2: file from files table is gone, but its hash is known
                    missingHashes[track.hash] = track
            if len(goneNewFiles) > 0:
                db.multiQuery("DELETE FROM {}newfiles WHERE url=?".format(db.prefix),
                              [ (str(track.url),) for track in goneNewFiles])
                for track in goneNewFiles:
                    self.dbTracks.remove(track.url)
                    del self.tracks[track.url]
            if len(missingHashes) > 0:
                # search tracks not in DB for the missing hashes 
                detectedMoves = []
                for newTrack in self.tracks.values():
                    if newTrack.id is None and newTrack.hash in missingHashes:
                        detectedMoves.append( (missingHashes[newTrack.hash], newTrack))
                        del missingHashes[newTrack.hash]
                for dbTrack, newTrack in detectedMoves:
                    self.moveDetected.emit(dbTrack.id, newTrack.url)
                    self.moveTrack(dbTrack, newTrack.url)
        if len(self.dbTracks) > 0:
            logger.debug("files which are lost: {}".format(self.dbTracks))
            self.helper.dialogFinished.clear()
            self.lostTracksDetected.emit([self.tracks[url] for url in self.dbTracks])
            self.helper.dialogFinished.wait()
            fixedByUser = []
            for url in self.dbTracks:
                track = self.tracks[url]
                if levels.real.get(track.id).url != url:
                    fixedByUser.append( (track, levels.real.get(track.id).url) )
            for track, newUrl in fixedByUser:
                self.moveTrack(track, newUrl)
        elif len(self.dbDirectories) > 0:
            db.multiQuery("DELETE FROM {}folders WHERE path=?".format(db.prefix),
                          [ (dir, ) for dir in self.dbDirectories ])
            for dirPath in self.dbDirectories:
                dir = self.directories[dirPath]
                assert len(dir.tracks) == 0
                dir.parent.subdirs.remove(dir)
            self.dbDirectories = set()
    
    def moveTrack(self, track, newUrl):
        newDir = self.getDirectory(os.path.dirname(newUrl.path))[0]
        oldDir = track.directory
        oldDir.tracks.remove(track)
        if newUrl in self.tracks:
            existingTrack = self.tracks[newUrl]
            assert existingTrack.id is None
            newDir.tracks.remove(existingTrack)
            db.query("DELETE FROM {}newfiles WHERE url=?".format(db.prefix),
                             str(newUrl))
        if track.url in self.dbTracks:
            self.dbTracks.remove(track.url)
        newDir.addTrack(track)
        del self.tracks[track.url]
        track.url = newUrl
        self.tracks[newUrl] = track
        stateChanges = newDir.updateState(True, False, True, self.folderStateChanged)
        if oldDir != newDir:
            stateChanges += oldDir.updateState(True, False, True, self.folderStateChanged)
        self.updateDirectories(stateChanges)
    
    @QtCore.pyqtSlot(object)
    def handleRename(self, renamings):
        db.transaction()
        for id, (oldUrl, newUrl) in renamings.items():
            if oldUrl.scheme != "file":
                continue
            if oldUrl in self.tracks:
                self.moveTrack(self.tracks[oldUrl], newUrl)
        db.commit()

    @QtCore.pyqtSlot(list)
    def handleAdd(self, newFiles):
        newDirectories = set()
        modifiedDirs = []
        newHashes = []
        db.multiQuery("DELETE FROM {}newfiles WHERE url=?".format(db.prefix),
                      [ (str(file.url),) for file in newFiles ])
        for file in newFiles:
            dir, newDirs = self.getDirectory(os.path.dirname(file.url.path))
            newDirectories.update(newDirs)
            if file.url in self.tracks:
                track = self.tracks[file.url]
            else:
                track = self.addTrack(dir, file.url)
                newHashes.append(track)
            track.id = file.id
            modifiedDirs += dir.updateState(True, False, True, self.folderStateChanged)
        self.storeDirectories(newDirectories)
        self.updateDirectories(modifiedDirs)
    
    @QtCore.pyqtSlot(list)
    def handleRemove(self, removedFiles):
        modifiedDirs = []
        newTracks = []
        for file in removedFiles:
            if file.url in self.tracks:
                track = self.tracks[file.url]
                newTracks.append(track)
                track.id = None
                modifiedDirs += track.directory.updateState(True, False, True,
                                                            self.folderStateChanged)
        self.updateDirectories(modifiedDirs)
        self.storeNewTracks(newTracks)
