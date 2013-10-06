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

import os, subprocess, hashlib, threading
from os.path import basename, dirname, join, split
from datetime import datetime, timezone, MINYEAR

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from omg import application, logging, config, utils, database as db
from omg.filebackends import BackendURL
from omg.filebackends.filesystem import FileURL
from omg.core import levels, tags

logger = logging.getLogger(__name__)
translate = QtCore.QCoreApplication.translate

synchronizer = None
enabled = False

NO_MUSIC = 0
HAS_FILES = 1
HAS_NEW_FILES = 2
PROBLEM = 4

def init():
    """Initialize file system watching.
    
    This will start a separate thread that repeatedly scans the music folder for changes.
    """
    global enabled, synchronizer
    import _strptime
    from . import identification
    if config.options.filesystem.disable:
        return
    synchronizer = FileSystemSynchronizer()
    application.dispatcher.emit(application.ModuleStateChangeEvent("filesystem", "enabled"))
    enabled = True
    

def shutdown():
    """Terminates this module; waits for all threads to complete."""
    global enabled, synchronizer
    if config.options.filesystem.disable or synchronizer is None:
        return
    levels.real.filesystemDispatcher.disconnect(synchronizer.handleRealFileEvent)
    synchronizer.shouldStop.set()
    synchronizer.exit()
    synchronizer.wait()
    synchronizer = None
    application.dispatcher.emit(application.ModuleStateChangeEvent("filesystem", "disabled"))
    enabled = False
    logger.debug("Filesystem module: shutdown complete")


def folderState(path):
    """Return the state of a given folder, or 'unknown' if it can't be obtained. """
    if enabled:
        try:
            return synchronizer.directories[path].simpleState()
        except KeyError: pass
    return 'unknown'


def fileState(url):
    """Return the state of a given file (one of 'problem', 'ok', 'unsynced', 'unknown').
    """
    if enabled:
        try:
            return synchronizer.tracks[url].simpleState()
        except KeyError: pass
    return 'unknown'


def getNewfileHash(url):
    """Return the hash of a file specified by *url* which is not yet in the database.
    
    If the hash is not known, returns None.
    """
    if enabled:
        try:
            return synchronizer.tracks[url].hash
        except KeyError: pass
    return None


class Track:
    """A track represents a real audio file inside the music collection folder.
    
    It stores URL, directory, possibly the ID (or None if the track is not in the database),
    and a *problem* flag if there is a synchronization problem with this track.
    """
    
    def __init__(self, url):
        self.url = url
        self.directory = None
        self.id = self.lastChecked = self.hash = None
        self.problem = False
    
    def simpleState(self):
        """Return the state of this file as one of the strings "problem", "ok", "unsynced".
        """
        if self.problem:
            return 'problem'
        if self.id is not None:
            return 'ok'
        return 'unsynced'
    
    def __str__(self):
        if self.id is not None:
            return "DB Track[{}](url={})".format(self.id, self.url)
        return ("New Track(url={})".format(self.url))


class Directory:
    """A directory inside the music collection directory.
    
    This is used for efficient storing and updating of the folder state. A directory has lists for
    subdirectories and tracks, a pointer to the parent directory (*None* for the root), and a state
    flag.
    """
    
    def __init__(self, path, parent):
        """Create the Directory in *path*. *parent* is the parent Directory object (possibly None).
        
        *path* is always a relative path. If a parent is given, the new directory is automatically
        added to its subdirs.
        """
        
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
        """Adds *track* to the list self.tracks and updates track.directory."""
        track.directory = self
        self.tracks.append(track)
    
    def updateState(self, considerTracks=True, considerSubdirs=True, recurse=False,
                     signal=None):
        """Update the *state* attribute of this directory.
        
        The state is determined by the tracks inside the directory and the state of possible
        subdirectories. For faster updates, consideration of tracks or subdirectories can be
        turned off using the appropriate parameters.
        If *recurse* is True, the state of the parent is updated if this method has changed
        self.state.
        The *signal* parameter optionally specifies a Qt signal which will be emit, with the
        directory's path as single parameter, in case of a state change.
        
        This method returns a list of Directory objects whose states have changed.
        """
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
            
    def simpleState(self):
        """Return the state as one of the strings "problem", "unsynced", "ok", "nomusic"."""
        if self.state & PROBLEM:
            return 'problem'
        if self.state & HAS_NEW_FILES:
            return 'unsynced'
        if self.state & HAS_FILES:
            return 'ok'
        return 'nomusic'


class SynchronizeHelper(QtCore.QObject):
    """An object living in the main event thread to change the files table and display GUIs."""
    
    def __init__(self):
        super().__init__()
        self.dialogFinished = threading.Event()
    
    @QtCore.pyqtSlot(str, object)
    def handleSynchronizerRequest(self, requestType, args):
        getattr(self, requestType)(*args)

    def updateFileHashes(self, tracks):
        """Updates the hashes of *tracks* in the files table and also their timestamps.
        """ 
        if len(tracks):
            db.multiQuery("UPDATE {p}files SET hash=?, verified=CURRENT_TIMESTAMP "
                                          "WHERE element_id=?",
                          [ (track.hash, track.id) for track in tracks ]) 

    def changeURL(self, id, newUrl):
        """Call when a URL change was detected. Displays a notice and updates the files table."""
        from ..gui.dialogs import warning
        from .. import application
        warning(self.tr("Move detected"),
                self.tr("A file was renamed (or moved) outside OMG:\n"
                        "{}".format(str(newUrl))), application.mainWindow)
        db.query('UPDATE {p}files SET url=? WHERE element_id=?', str(newUrl), id)
        if id in levels.real.elements:
            levels.real.collect(id).url = newUrl
            levels.real.emitEvent(dataIds=[id])
    
    def showLostTracksDialog(self, tracks):
        """To be called when lost tracks have been detected. Opens the respective dialog."""
        from . import dialogs
        dialog = dialogs.MissingFilesDialog([track.id for track in tracks])
        dialog.exec_()
        from .. import application
        application.stack.clear()
        self._dialogResult = {"removed" : dialog.deleteAction.removedURLs,
                              "renamed" : dialog.setPathAction.setPaths } 
        self.dialogFinished.set()

    def showModifiedTagsDialog(self, modifications):
        """Call when a change of on-disk tags occured. Opens a dialog.
        
        *modifications* must be a dict mapping Track instances to (dbTags, fsTags) tuples.
        """
        from . import dialogs
        for track, (dbTags, fsTags) in modifications.items():
            dialog = dialogs.ModifiedTagsDialog(track, dbTags, fsTags)
            dialog.exec_()
            if dialog.result() == dialog.Accepted:
                if dialog.choice == 'DB':
                    backendFile = track.url.getBackendFile()
                    backendFile.readTags()
                    backendFile.tags = dbTags.withoutPrivateTags()
                    backendFile.saveTags()
                else:
                    from .. import application
                    application.stack.clear()
                    diff = tags.TagStorageDifference(dbTags.withoutPrivateTags(), fsTags)
                    levels.real._changeTags({levels.real.get(track.id) : diff }, dbOnly=True)
                track.problem = False
                track.verified = datetime.now(timezone.utc)
                self.updateFileHashes([track])
        synchronizer.modifiedTags = {}
        self.dialogFinished.set()


class FileSystemSynchronizer(QtCore.QThread):
    """This is the main class responsible for scanning the filesystem and updating tracks and dirs.
    
    It runs in its own thread in order not to cause GUI hangs.
    """
    
    # signals for external use (e.g. in FilesystemBrowser)
    folderStateChanged = QtCore.pyqtSignal(object)
    fileStateChanged = QtCore.pyqtSignal(object)
    
    # internal signal, connected to the SynchronizeHelper
    _requestHelper = QtCore.pyqtSignal(str, object)
    
    def __init__(self):
        """Create the synchronizer. Also creates and connects to a SynchronizeHelper."""
        super().__init__()
        self.shouldStop = threading.Event()
        self.timer = QtCore.QTimer(self)
        self.helper = SynchronizeHelper()
        self.moveToThread(self)
        self._requestHelper.connect(self.helper.handleSynchronizerRequest)
        self.timer.timeout.connect(self.scanFilesystem)
        self.tracks = {}           # maps URL->track
        self.directories = {}      # maps (rel) path -> Directory object
        self.dbTracks = {}     # urls in the files table
        self.tableFolders = {} # paths in the folders table
        from .identification import AcoustIDIdentifier
        self.idProvider = AcoustIDIdentifier(config.options.filesystem.acoustid_apikey)
        
        QtCore.QTimer.singleShot(2000, self.start)
        levels.real.filesystemDispatcher.connect(self.handleRealFileEvent, Qt.QueuedConnection)

    def run(self):
        self.init()
        self.timer.start(config.options.filesystem.scan_interval * 1000)
        self.exec_()
        db.close()
    
    def init(self):
        """Initialize the synchronizer by building Directory tree and Tracks from DB tables.
        
        Afterwards, potential missing hashes in the DB table will be updated, if hashing is
        enabled. At last a filesystem scan is initiated.
        """
        db.connect()
        self.loadFolders()
        missingHashes = self.loadDBFiles()
        self.loadNewFiles()
        application.dispatcher.emit(application.ModuleStateChangeEvent("filesystem", "initialized"))
        if len(missingHashes) > 0:
            successful = []
            for i, track in enumerate(missingHashes, start=1):
                logger.info("Computing hash of {} of {} files".format(i, len(missingHashes)))
                track.hash = self.idProvider(track.url)
                if track.hash:
                    successful.append(track)
                if self.shouldStop.is_set():
                    break
            if len(successful):
                self._requestHelper.emit("updateFileHashes", (successful,))
        self.scanFilesystem()
    
    def loadFolders(self):
        """Load the folders table from the database.
        
        Creates the tree of Directory objects and initializes self.directories and
        self.tableFolders.
        """
        for path, state in db.query("SELECT path, state FROM {p}folders ORDER BY LENGTH(path)"):
            parent, basename = split(path)
            if parent == '' and basename == '':
                dir = Directory(path='', parent=None)                    
            else:
                parent = self.directories[parent]
                dir = Directory(path, parent)
            dir.state = state
            self.directories[dir.path] = dir
            self.tableFolders[dir.path] = False
    
    def loadDBFiles(self):
        """Load the commited files from the files table.
        
        Adds them to self.tracks and self.dbTracks, and to the Directory objects in memory.
        It might happen that the folders table does not contain the directory of some DB file (e.g.
        if OMG was exited unexpectedly). In such a case the folders table is augmented by that
        directory.
        
        This method returns a list of Tracks (if any) which are in the files table but have no hash
        set.
        """ 
        newDirectories = []
        missingHashes = set()
        for elid, urlstring, elhash, verified in db.query(
                           "SELECT element_id, url, hash, verified FROM {p}files"):
            url = BackendURL.fromString(urlstring)
            if url.scheme != "file":
                continue
            track = Track(url)
            track.id = elid
            if db.isNull(elhash) or elhash == "0":
                missingHashes.add(track)
            else:
                track.hash = elhash
            track.verified = db.getDate(verified)
            self.tracks[track.url] = track
            self.dbTracks[track.url] = False
            dir, newDirs = self.getDirectory(dirname(track.url.path))
            dir.addTrack(track)
            newDirectories += newDirs
        if len(newDirectories) > 0:
            logger.debug("{} dirs with DBfiles but not in folders".format(len(newDirectories)))
            db.multiQuery("INSERT INTO {p}folders (path, state) VALUES (?,?)",
                          [(dir.path, dir.state) for dir in newDirectories])
        return missingHashes
    
    def loadNewFiles(self):
        """Load the newfiles table and add the tracks to self.tracks.
        
        URLs from newfiles already contained in files are deleted.
        """
        toDelete = []
        for urlstring, elhash, verified in db.query("SELECT url, hash, verified FROM {p}newfiles"):
            track = Track(BackendURL.fromString(urlstring))
            if track.url in self.dbTracks:
                logger.warning("url {} is BOTH n files and newfiles!".format(urlstring))
                toDelete.append((urlstring,))
                continue
            track.hash = elhash
            track.verified = db.getDate(verified)
            self.tracks[track.url] = track
            self.dbTracks[track.url] = False
            dir = self.directories[dirname(track.url.path)]
            dir.addTrack(track)
        if len(toDelete) > 0:
            db.multiQuery("DELETE FROM {p}newfiles WHERE url=?", toDelete)  

    
    def getDirectory(self, path, storeNew=False):
        """Get a Directory object for *path*.
        
        If necessary, the path and potential parents are created and inserted into self.directories
        (but not into the database). The result is a pair consisting of the requested Directory and
        a list of newly created Directory objects.
        When *storeNew* is True and new directories were created, they will be inserted into the
        database. Otherwise the caller is responsible for that.
        """        
        if path is None:
            return None, []
        if path in self.directories:
            return self.directories[path], []
        parentPath = None if path == "" else split(path)[0]
        parent, new = self.getDirectory(parentPath)
        dir = Directory(path, parent)
        self.directories[path] = dir
        if storeNew:
            self.storeDirectories(new + [dir])
        return dir, new + [dir]
        
    def checkTrack(self, track):
        """Perform a check of *track* on the filesystem to find potential differences to the DB.
        
        This method checks the modification timestamp of the file. If it is newer than the track's
        *verified* attribute, then:
        - if it is a new track (not in files), recomputes the hash and updates newfiles
        - if it's in the DB, additionally the tags are checked and compared against those in the
          database. If they differ, a tuple (dbTags, fileTags) is returned, in any other case None.
        """
        modified = utils.mTimeStamp(track.url)
        if modified <= track.verified:
            return None
        logger.debug('checking track {}...'.format(basename(track.url.path)))
        newHash = self.idProvider(track.url)
        if track.id is None:
            track.verified = modified
            if newHash != track.hash:
                logger.debug("... and updating hash in newfiles")
                track.hash = newHash
            else:
                logger.debug("... and updating timestamp")
            db.query("UPDATE {p}newfiles SET hash=?, verified=CURRENT_TIMESTAMP WHERE url=?",
                     track.hash, str(track.url))
        else:
            if track.id in levels.real:
                dbTags = levels.real.get(track.id).tags
            else:
                dbTags = db.tags(track.id)
            backendFile = track.url.getBackendFile()
            backendFile.readTags()
            if dbTags.withoutPrivateTags() != backendFile.tags:
                logger.debug('Detected modification on file "{}": tags differ'.format(track.url))
                track.hash = newHash
                self.modifiedTags[track] = (dbTags, backendFile.tags)
                track.problem = True
                self.fileStateChanged.emit(track.url)
            else:
                if newHash != track.hash:
                    logger.debug("audio data modified! {} != {} ".format(newHash, track.hash))
                    track.hash = newHash
                    track.verified = modified
                self._requestHelper.emit("updateFileHashes", ((track,),)) # will also update verified
    
    def addTrack(self, dir, url, computeHash=True):
        """Create a new Track at *url* and add it to the Directory *dir*.
        
        Computes the track's hash if enabled and adds it to self.tracks.
        """
        track = Track(url)
        dir.addTrack(track)
        self.tracks[url] = track
        if computeHash:
            track.hash = self.idProvider(url)
        track.verified = utils.mTimeStamp(url)
        return track
    
    def storeDirectories(self, directories):
        """Insert the given list of Directory objects into the folders table."""
        if len(directories) > 0:
            db.multiQuery("INSERT INTO {p}folders (path, state) VALUES(?,?)",
                          [ (dir.path, dir.state) for dir in directories])
    
    def updateDirectories(self, directories):
        """Update the given list of directories in the folders table."""
        if len(directories) > 0:
            db.multiQuery("UPDATE {p}folders SET state=? WHERE path=?",
                          [ (dir.state, dir.path) for dir in directories])
    
    def storeNewTracks(self, tracks):
        """Insert the given list of Track objects into the newfiles table."""
        if len(tracks) > 0:
            db.multiQuery("INSERT INTO {p}newfiles (url, hash, verified) VALUES (?,?,?)",
                          [(str(track.url), track.hash,
                              track.verified.strftime("%Y-%m-%d %H:%M:%S")) for track in tracks])
    
    def removeTracks(self, tracks):
        urls = []
        for track in tracks: 
            urls.append(track.url)
            track.directory.tracks.remove(track)
            track.directory.updateState(True, False, True, self.folderStateChanged)
            del self.tracks[track.url]
            if track.url in self.dbTracks:
                del self.dbTracks[track.url]
        if len(urls) > 0:
            db.multiQuery("DELETE FROM {p}newfiles WHERE url=?", [ (str(url),) for url in urls])
    

    def scanFilesystem(self):
        """Walks through the collection, updating folders and searching for new files.
        """
        #  updates on directories and tracks are collected  and then commited batch-wise
        #  to improve database performance. 
        newDirectories, modifiedDirectories, newTracks = set(), set(), set()
        def storeChanges():
            db.transaction()
            self.storeDirectories(newDirectories)
            self.updateDirectories(modifiedDirectories)
            self.storeNewTracks(newTracks)
            db.commit()
        THRESHOLD = 100  # number of updates before database is called
        self.timer.stop()
        self.modifiedTags = {}
        for url in self.dbTracks:
            self.dbTracks[url] = False
        for dir in self.tableFolders:
            self.tableFolders[dir] = False 
        # run through the filesystem. Any directories or tracks being found will be set to True
        # in self.dbTracks and self.tableFolders, respectively. Thus, any entries remaining False
        # in that dicts after scanFilesystem() are detected as missing.
        for root, dirs, files in os.walk(config.options.main.collection, topdown=True):
            dirs.sort()
            newTracksInDir = 0
            relPath = utils.relPath(root)
            if relPath == ".":
                relPath = ""
            self.tableFolders[relPath] = True
            dir, newDirs = self.getDirectory(relPath)
            newDirectories.update(newDirs)
            for file in files:
                if self.shouldStop.is_set():
                    break
                if not utils.hasKnownExtension(file):
                    continue
                url = FileURL(join(relPath, file))
                if url in self.tracks:
                    self.dbTracks[url] = True
                    track = self.tracks[url]
                    tagDiffs = self.checkTrack(track)
                    if tagDiffs is not None:
                        self.modifiedTags[track] = tagDiffs
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
                storeChanges()
                newTracks, newDirectories, modifiedDirectories = set(), set(), set()
        if len(newTracks) + len(newDirectories) + len(modifiedDirectories) > 0:
            storeChanges()
        if self.shouldStop.is_set():
            return
        self.analyzeScanResults()
        self.timer.start()
        logger.debug("filesystem scan complete")
      
    def analyzeScanResults(self):
        """Called after scanFilesystem to detect discrepancies between DB and filesystem.
        
        *modifiedTags* is a dict mapping Tracks to (dbTags, fileTags) pairs. If it is nonempty,
        the helper is called to show a dialog.
        Afterwards it is checked if any files remain in self.dbTracks, i.e., they are contained
        in the database but not on the filesystem. For new files they are just removed from the
        database.
        In case commited files are missing, we first try to detect moves by searching theiry hash
        in self.tracks. Otherwise a LostFilesDialog is requested from the helper.
        """
        if len(self.modifiedTags) > 0:
            logger.debug("files with modified tags: {}".format(self.modifiedTags,))
            self.helper.dialogFinished.clear()
            self._requestHelper.emit("showModifiedTagsDialog", (self.modifiedTags,))
            self.helper.dialogFinished.wait()
        if not all(self.dbTracks.values()): # some files have been (re)moved outside OMG
            notFound = [url for url, found in self.dbTracks.items() if not found]
            notFoundNew = [url for url in notFound if self.tracks[url].id is None]
            notFoundDB = [url for url in notFound if self.tracks[url].id is not None]
            self.removeTracks([self.tracks[url] for url in notFoundNew])
            missingHashes = {} # hashes of missing files mapped to Track objects
            for url in notFoundDB:
                track = self.tracks[url]
                if track.hash is not None:
                    missingHashes[track.hash] = track
            if len(missingHashes) > 0:
                # search tracks not in DB for the missing hashes 
                detectedMoves = []
                for newTrack in self.tracks.values():
                    if newTrack.id is None and newTrack.hash in missingHashes:
                        oldTrack = missingHashes[newTrack.hash]
                        detectedMoves.append( (oldTrack, newTrack))
                        del self.dbTracks[oldTrack.url]
                        notFoundDB.remove(oldTrack.url)
                        del missingHashes[newTrack.hash]
                for dbTrack, newTrack in detectedMoves:
                    self._requestHelper.emit("changeURL", (dbTrack.id, newTrack.url)) # updates DB
                    self.moveTrack(dbTrack, newTrack.url) # updates directories
            if len(notFoundDB) > 0:
                # --> some files are lost. Show a dialog and let the user fix this
                self.helper.dialogFinished.clear()
                logger.debug("Some files could not be found:")
                for url in notFoundDB:
                    logger.debug("  {}".format(url))
                self._requestHelper.emit("showLostTracksDialog",
                                         ([self.tracks[url] for url in notFoundDB],))
                self.helper.dialogFinished.wait()
                result = self.helper._dialogResult
                for oldURL, newURL in result["renamed"]:
                    del self.dbTracks[oldURL]
                    self.moveTrack(self.tracks[oldURL], newURL)
                self.removeTracks([self.tracks[url] for url in result["removed"]])
        notFound = [dir for dir, found in self.tableFolders.items() if not found]
        if all(self.dbTracks.values()) and len(notFound) > 0:
            db.multiQuery("DELETE FROM {p}folders WHERE path=?", [ (dir, ) for dir in notFound ])
            for dirPath in notFound:
                dir = self.directories[dirPath]
                assert len(dir.tracks) == 0
                dir.parent.subdirs.remove(dir)
                del self.tableFolders[dirPath]

    
    def moveTrack(self, track, newUrl):
        """Internally move *track* to *newUrl* by updating the Directories and their states.
        
        This does not alter the filesystem and normally also not the database. The exception is
        the target URL already exist in self.tracks; in that case it is removed from newfiles.
        Also if newUrl is in a directory not yet contained in self.directories it (and potential
        parents which are also new) is added to the folders table.
        """
        newDir = self.getDirectory(dirname(newUrl.path), storeNew=True)[0]
        oldDir = track.directory
        oldDir.tracks.remove(track)
        if newUrl in self.tracks:
            existingTrack = self.tracks[newUrl]
            assert existingTrack.id is None
            newDir.tracks.remove(existingTrack)
            db.query("DELETE FROM {p}newfiles WHERE url=?", str(newUrl))
        newDir.addTrack(track)
        del self.tracks[track.url]
        track.url = newUrl
        self.tracks[newUrl] = track
        stateChanges = newDir.updateState(True, False, True, self.folderStateChanged)
        if oldDir != newDir:
            stateChanges += oldDir.updateState(True, False, True, self.folderStateChanged)
        self.updateDirectories(stateChanges)
        self.fileStateChanged.emit(newUrl)
    
    @QtCore.pyqtSlot(object)
    def handleRealFileEvent(self, event):
        """Handle an event issued by levels.real if something has affected the filesystem."""
        db.transaction()
        
        for oldURL, newURL in event.renamed:
            if oldURL in self.tracks:
                if self.tracks[oldURL].id is None:
                    db.query("DELETE FROM {p}newfiles WHERE url=?", str(oldURL))                        
                self.moveTrack(self.tracks[oldURL], newURL)
        
        newHashes = []
        for url in event.modified:
            if url not in self.tracks:
                continue
            track = self.tracks[url]
            track.verified = utils.mTimeStamp(url)
            if track.id is None:
                db.query("UPDATE {p}newfiles SET verified=CURRENT_TIMESTAMP WHERE url=?", str(url))
            else:
                newHashes.append(track)
    
        modifiedDirs = []
        if len(event.added) > 0:
            db.multiQuery("DELETE FROM {p}newfiles WHERE url=?",
                          [ (str(elem.url),) for elem in event.added ])
            for elem in event.added:
                url = elem.url
                if url not in self.tracks:
                    dir = self.getDirectory(dirname(url.path), storeNew=True)[0]
                    track = self.addTrack(dir, url, computeHash=False)
                    logger.info("adding url not in self.tracks: {}".format(url))
                else:
                    dir = self.directories[dirname(url.path)]
                    track = self.tracks[url]
                if track.hash is None:
                    track.hash = self.idProvider(url)
                    if track.hash is not None:
                        newHashes.append(track)
                track.id = elem.id
                modifiedDirs += dir.updateState(True, False, True, self.folderStateChanged)
                self.fileStateChanged.emit(url)
        if len(newHashes) > 0:
            self._requestHelper.emit("updateFileHashes", (newHashes,))
        
        if len(event.removed) > 0:
            newTracks = []
            for url in event.removed:
                if url not in self.tracks:
                    continue # happens after removals in a LostFilesDialog
                track = self.tracks[url]
                newTracks.append(track)
                track.id = None
                modifiedDirs += track.directory.updateState(True, False, True,
                                                            self.folderStateChanged)
            self.storeNewTracks(newTracks)
        self.updateDirectories(modifiedDirs)
        
        if len(event.deleted) > 0:
            tracks = [ self.tracks[url] for url in event.deleted if url in self.tracks ]
            self.removeTracks(tracks)
        db.commit()
        
    @QtCore.pyqtSlot(str)
    def recheck(self, directory):
        for track in self.tracks.values():
            if directory == "" or track.url.path.startswith(directory+"/"):
                track.verified = datetime(MINYEAR, 1, 1, tzinfo=timezone.utc)
        self.scanFilesystem()
