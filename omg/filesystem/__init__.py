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

import os.path, subprocess, hashlib, threading
from datetime import datetime, timezone, MINYEAR

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from .. import logging, config, utils, database as db, filebackends
from ..core import levels, tags

logger = logging.getLogger(__name__)
translate = QtCore.QCoreApplication.translate

synchronizer = None
enabled = False
idProvider = None

NO_MUSIC = 0
HAS_FILES = 1
HAS_NEW_FILES = 2
PROBLEM = 4

def init():
    global synchronizer, notifier, idProvider
    import _strptime
    from . import identification
    if config.options.filesystem.disable:
        return
    apikey = "8XaBELgH" #TODO: AcoustID test key - we should change this
    idProvider = identification.AcoustIDIdentifier(apikey)
    synchronizer = FileSystemSynchronizer()
    
def shutdown():
    """Terminates this module; waits for all threads to complete."""
    global synchronizer, enabled
    if config.options.filesystem.disable or synchronizer is None:
        return
    enabled = False
    levels.real.filesystemDispatcher.disconnect(synchronizer.handleRealFileEvent)
    synchronizer.should_stop.set()
    synchronizer.eventThread.exit()
    synchronizer.eventThread.wait()
    synchronizer = None
    logger.debug("Filesystem module: shutdown complete")


def folderState(path):
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


def fileState(url):
    """Return the state of a given file (one of 'problem', 'ok', 'unsynced', 'unknown').
    """
    if enabled and synchronizer.initialized.is_set():
        try:
            track = synchronizer.tracks[url]
            if track.problem:
                return 'problem'
            elif track.id is not None:
                return 'ok'
            else:
                return 'unsynced'
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

def mTimeStamp(url):
    """Get the modification timestamp of a file given by *url*.
    
    Returns a datetime object with timezone UTC.
    """
    return datetime.fromtimestamp(os.path.getmtime(url.absPath), tz=timezone.utc\
                                 ).replace(microsecond=0)



class Track:
    """A track represents a real audio file inside the music collection folder.
    
    This class is a pure data class, storing URL, directory, possibly the ID (or None if the track
    is not in the database), and a *problem* flag if there is a synchronization problem with this
    track.
    """
    
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
            
        
class SynchronizeHelper(QtCore.QObject):
    """Cdoe running in the main event thread to change the files table and display GUIs."""
    
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
            db.multiQuery("UPDATE {}files SET hash=?, verified=CURRENT_TIMESTAMP "
                                         "WHERE element_id=?".format(db.prefix),
                                         [ (track.hash, track.id) for track in tracks ]) 

    def changeURL(self, id, newUrl):
        """Call when a URL change was detected. Displays a notice and updates the files table."""
        from ..gui.dialogs import warning
        from .. import application
        warning(self.tr("Move detected"),
                self.tr("A file was renamed (or moved) outside OMG:\n"
                        "{}".format(str(newUrl))), application.mainWindow)
        db.query('UPDATE {}files SET url=? WHERE element_id=?'.format(db.prefix), str(newUrl), id)
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


class EventThread(QtCore.QThread):
    """The dedicated thread for filesystem access."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.timer = QtCore.QTimer(self)
        
    def run(self):
        global enabled
        enabled = True
        self.timer.start(config.options.filesystem.scan_interval * 1000)
        self.exec_()
        db.close()
        
    def __str__(self):
        return "FilesystemThread"  


class FileSystemSynchronizer(QtCore.QObject):
    """This is the main class responsible for scanning the filesystem and updating tracks and dirs.
    
    It runs in its own thread in order not to cause GUI hangs.
    """
    
    # signals for external use (e.g. in FilesystemBrowser)
    folderStateChanged = QtCore.pyqtSignal(object)
    fileStateChanged = QtCore.pyqtSignal(object)
    initializationComplete = QtCore.pyqtSignal()
    
    # internal signal, connected to the SynchronizeHelper
    _requestHelper = QtCore.pyqtSignal(str, object)
    
    def __init__(self):
        """Create the synchronizer. Also creates and connects to a SynchronizeHelper."""
        super().__init__()
        self.should_stop = threading.Event()
        self.initialized = threading.Event()
        
        self.helper = SynchronizeHelper()
        self.eventThread = EventThread(self)
        self.moveToThread(self.eventThread)
        self._requestHelper.connect(self.helper.handleSynchronizerRequest)
        self.eventThread.started.connect(self.init)
        self.eventThread.timer.timeout.connect(self.scanFilesystem)
        self.tracks = {}           # maps URL->track
        self.directories = {}      # maps (rel) path -> Directory object
        self.dbTracks = set()      # urls in the files or newfiles table
        self.dbDirectories = set() # paths in the folders table
        
        QtCore.QTimer.singleShot(2000, self.eventThread.start)
        levels.real.filesystemDispatcher.connect(self.handleRealFileEvent, Qt.QueuedConnection)

    def loadFolders(self):
        """Load the folders table from the database.
        
        Creates the tree of Directory objects and initializes self.directories and
        self.dbDirectories.
        """
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
                       "SELECT element_id, url, hash, verified FROM {}files".format(db.prefix)):
            url = filebackends.BackendURL.fromString(urlstring)
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
            self.dbTracks.add(track.url)
            dir, newDirs = self.getDirectory(os.path.dirname(track.url.path))
            dir.addTrack(track)
            newDirectories += newDirs
        if len(newDirectories) > 0:
            logger.debug("Found {} directories which have DB files but are not in the folders table"
                         .format(len(newDirectories)))
            db.multiQuery("INSERT INTO {}folders (path, state) VALUES (?,?)".format(db.prefix),
                          [(dir.path, dir.state) for dir in newDirectories])
        return missingHashes
    
    def loadNewFiles(self):
        """Load the newfiles table and add the tracks to self.tracks.
        
        If an URL from newfiles is already contained in files, the newfiles entry is deleted.
        """
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
        """Initialize the synchronizer by building Directory tree and Tracks from DB tables.
        
        After everything is loaded, the event self.initialized is set and the signal
        self.initializationComplete emitted.
        Afterwards, potential missing hashes in the DB table will be updated, if hashing is
        enabled. At last a filesystem scan is initiated.
        """
        db.connect()
        self.loadFolders()
        missingHashes = self.loadDBFiles()
        self.loadNewFiles()
        self.initialized.set()
        self.initializationComplete.emit()
        if len(missingHashes) > 0 and idProvider is not None:
            lenMissing = len(missingHashes)
            for i, track in enumerate(missingHashes):
                track.hash = idProvider(track.url)
                logger.info("Computing hash of {}/{} unhashed files".format(i, lenMissing))
                if self.should_stop.is_set():
                    break
            if lenMissing > 0:
                self._requestHelper.emit("updateFileHashes", (missingHashes,))
        self.scanFilesystem()
    
    def getDirectory(self, path):
        """Get a Directory object for *path*.
        
        If necessary, the path and potential parents are created and inserted into self.directories
        (but not into the database). The result is a pair consisting of the requested Directory and
        a list of newly created Directory objects. The caller is responsible for adding them to
        the database.
        """        
        if path is None:
            return None, []
        if path in self.directories:
            return self.directories[path], []
        parentPath = None if path == "" else os.path.split(path)[0]
        parent, new = self.getDirectory(parentPath)
        dir = Directory(path, parent)
        self.directories[path] = dir
        return dir, new + [dir]
        
    def checkTrack(self, track):
        """Perform a check of *track* on the filesystem to find potential differences to the DB.
        
        This method checks the modification timestamp of the file. If it is newer than the track's
        *verified* attribute, then:
        - if it is a new track (not in files), recomputes the hash and updates newfiles
        - if it's in the DB, additionally the tags are checked and compared against those in the
          database. If they differ, a tuple (dbTags, fileTags) is returned, in any other case None.
        """
        modified = mTimeStamp(track.url)
        if modified <= track.verified:
            return None
        logger.debug('checking track {}...'.format(os.path.basename(track.url.path)))
        newHash = idProvider(track.url) if idProvider is not None else None
        if track.id is None:
            track.verified = modified
            if idProvider is None:
                return
            if newHash != track.hash:
                logger.debug("... and updating hash in newfiles")
                track.hash = newHash
            else:
                logger.debug("... and updating timestamp")
            db.query("UPDATE {}newfiles SET hash=?, verified=CURRENT_TIMESTAMP WHERE url=?"
                     .format(db.prefix), track.hash, str(track.url))
        else:
            if track.id in levels.real:
                dbTags = levels.real.get(track.id).tags
            else:
                dbTags = db.tags(track.id)
            backendFile = track.url.getBackendFile()
            backendFile.readTags()
            if dbTags.withoutPrivateTags() != backendFile.tags:
                logger.debug('Detected modification on file "{}": tags differ'.format(track.url))
                if idProvider is not None:
                    track.hash = newHash
                self.modifiedTags[track] = (dbTags, backendFile.tags)
                track.problem = True
                self.fileStateChanged.emit(track.url)
            elif idProvider is not None:
                if newHash != track.hash:
                    logger.debug("audio data modified! {} != {} ".format(newHash, track.hash))
                    track.hash = newHash
                    track.verified = modified
                self._requestHelper.emit("updateFileHashes", ((track,),)) # will also update verified
    
    def addTrack(self, dir, url):
        """Create a new Track at *url* and add it to the Directory *dir*.
        
        Computes the track's hash if enabled and adds it to self.tracks.
        """
        track = Track(url)
        dir.addTrack(track)
        self.tracks[url] = track
        track.hash = idProvider(url) if idProvider is not None else None
        track.verified = mTimeStamp(url)
        return track
    
    def storeDirectories(self, directories):
        """Insert the given list of Directory objects into the folders table."""
        if len(directories) > 0:
            db.multiQuery("INSERT INTO {}folders (path, state) VALUES(?,?)".format(db.prefix),
                          [ (dir.path, dir.state) for dir in directories])
    
    def updateDirectories(self, directories):
        """Update the given list of directories in the folders table."""
        if len(directories) > 0:
            db.multiQuery("UPDATE {}folders SET state=? WHERE path=?".format(db.prefix),
                          [ (dir.state, dir.path) for dir in directories])
    
    def storeNewTracks(self, tracks):
        """Insert the given list of Track objects into the newfiles table."""
        if len(tracks) > 0:
            db.multiQuery("INSERT INTO {}newfiles (url, hash, verified) VALUES (?,?,?)"
                          .format(db.prefix), [(str(track.url), track.hash,
                              track.verified.strftime("%Y-%m-%d %H:%M:%S")) for track in tracks])
    
    def removeTracks(self, tracks):
        removedURLs = []
        for track in tracks: 
            removedURLs.append(track.url)
            track.directory.tracks.remove(track)
            track.directory.updateState(True, False, True, self.folderStateChanged)
            del self.tracks[track.url]
            if track.url in self.dbTracks:
                self.dbTracks.remove(track.url)
        if len(removedURLs) > 0:
            db.multiQuery("DELETE FROM {}newfiles WHERE url=?".format(db.prefix),
                                  [ (str(url),) for url in removedURLs])
    
    @QtCore.pyqtSlot()
    def scanFilesystem(self):
        """Walks through the collection, updating folders and searching for new files.
        """
        #  updates on directories and tracks are collected  and then commited batch-wise
        #  to improve database performance. 
        newDirectories, modifiedDirectories, newTracks = set(), set(), set()
        THRESHOLD = 100  # number of updates before database is called
        self.eventThread.timer.stop()
        self.modifiedTags = {}
        
        # run through the filesystem. Any directories or tracks being found that are also in
        # self.dbDirectories or self.dbTracks, respectively, will be removed there. Thus, any
        # entries remaining in that sets after scanFilesystem() is complete can be detected as
        # missing during the first run of scanFilesystem().
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
            for file in files:
                if self.should_stop.is_set():
                    break
                if not utils.hasKnownExtension(file):
                    continue
                url = filebackends.filesystem.FileURL(os.path.join(relPath, file))
                if url in self.tracks:
                    if url in self.dbTracks:
                        self.dbTracks.remove(url)
                    track = self.tracks[url]
                    ret = self.checkTrack(track)
                    if ret is not None:
                        self.modifiedTags[track] = ret
                else:
                    track = self.addTrack(dir, url)
                    if idProvider is not None: # no point in adding tracks without hash to nefwfiles
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
        self.analyzeScanResults()
        self.eventThread.timer.start()
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
        if len(self.dbTracks) > 0: # some DB files or newfiles have been (re)moved outside OMG
            removedNewTracks = [ self.tracks[url] for url in self.dbTracks
                                                  if self.tracks[url].id is None ]
            self.removeTracks(removedNewTracks)
            missingHashes = {}
            for url in self.dbTracks:
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
                        self.dbTracks.remove(oldTrack.url)
                        del missingHashes[newTrack.hash]
                for dbTrack, newTrack in detectedMoves:
                    self._requestHelper.emit("changeURL", (dbTrack.id, newTrack.url)) # updates DB
                    self.moveTrack(dbTrack, newTrack.url) # updates directories
        if len(self.dbTracks) > 0:
            # still not empty -> some files are lost. Show a dialog and let the user fix this
            self.helper.dialogFinished.clear()
            logger.debug("requesting lost tracks dialog for {}".format(self.dbTracks))
            self._requestHelper.emit("showLostTracksDialog",
                                     ([self.tracks[url] for url in self.dbTracks],))
            self.helper.dialogFinished.wait()
            result = self.helper._dialogResult
            for oldURL, newURL in result["renamed"]:
                self.dbTracks.remove(oldURL)
                self.moveTrack(self.tracks[oldURL], newURL)
            self.removeTracks([self.tracks[url] for url in result["removed"]])
        if len(self.dbTracks) == 0 and len(self.dbDirectories) > 0:
            db.multiQuery("DELETE FROM {}folders WHERE path=?".format(db.prefix),
                          [ (dir, ) for dir in self.dbDirectories ])
            for dirPath in self.dbDirectories:
                dir = self.directories[dirPath]
                assert len(dir.tracks) == 0
                dir.parent.subdirs.remove(dir)
            self.dbDirectories = set()
    
    def moveTrack(self, track, newUrl):
        """Internally move *track* to *newUrl* by updating the Directories and their states.
        
        This does not alter the filesystem and normally also not the database. The exception is
        the target URL already exist in self.tracks; in that case it is removed from newfiles.
        Also if newUrl is in a directory not yet contained in self.directories it (and potential
        parents which are also new) is added to the folders table.
        """
        newDir, created = self.getDirectory(os.path.dirname(newUrl.path))
        if len(created) > 0:
            self.storeDirectories(created)
        oldDir = track.directory
        oldDir.tracks.remove(track)
        if newUrl in self.tracks:
            existingTrack = self.tracks[newUrl]
            assert existingTrack.id is None
            newDir.tracks.remove(existingTrack)
            db.query("DELETE FROM {}newfiles WHERE url=?".format(db.prefix),
                             str(newUrl))
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
        db.transaction()
        
        for oldURL, newURL in event.renamed:
            if oldURL in self.tracks:
                if self.tracks[oldURL].id is None:
                    db.query("DELETE FROM {}newfiles WHERE url=?".format(db.prefix),
                             str(oldURL))                        
                self.moveTrack(self.tracks[oldURL], newURL)
    
        for url in event.modified:
            if url not in self.tracks:
                logger.warning("handleRealFileEvent got modify for non-existing track: {}".format(url))
                continue
            track = self.tracks[url]
            track.verified = mTimeStamp(url)
            if track.id is None:
                db.query("UPDATE {}newfiles SET verified=CURRENT_TIMESTAMP WHERE url=?"
                         .format(db.prefix), str(url))
            else:
                self._requestHelper.emit("updateFileHashes", ((track,),))
    
        modifiedDirs = []
        if len(event.added) > 0:
            newHashes = []
            db.multiQuery("DELETE FROM {}newfiles WHERE url=?".format(db.prefix),
                          [ (str(elem.url),) for elem in event.added ])
            for elem in event.added:
                url = elem.url
                if url not in self.tracks:
                    logger.error("adding url not in self.tracks: {}".format(url))
                    continue
                dir = self.directories[os.path.dirname(url.path)]
                track = self.tracks[url]
                if track.hash is None and idProvider is not None:
                    logger.warning("hash is None in add to db handling {}".format(url))
                    track.hash = idProvider(url)
                    newHashes.append(track.hash)
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
                print('unverifying {}'.format(track))
                track.verified = datetime(MINYEAR, 1, 1, tzinfo=timezone.utc)
        self.scanFilesystem()
