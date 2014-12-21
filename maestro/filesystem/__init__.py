# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
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

import multiprocessing, os, queue, threading
import enum
from os.path import basename, dirname, join, split
from datetime import datetime, timezone, MINYEAR

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt
from maestro.filesystem.identification import AcoustIDIdentifier

translate = QtCore.QCoreApplication.translate

from .. import application, logging, config, utils, database as db, stack, constants
from ..filebackends import BackendURL
from ..filebackends.filesystem import FileURL
from ..core import levels, tags, domains

logger = logging.getLogger(__name__)

synchronizer = None
sources = None


class FilesystemState(enum.Enum):
    empty = 0
    synced = 1
    unsynced = 2
    unknown = 3
    problem = 4

    def combine(self, other):
        return FilesystemState(max(self.value, other.value))


class ScanState(enum.Enum):
    notScanning = 0
    initialScan = 1
    computingHashes = 2
    checkModified = 3
    realHashOnly = 4


def init():
    """Initialize file system watching.
    
    This will start a separate thread that repeatedly scans the music folder for changes.
    """
    global synchronizer, sources
    from . import identification
    # Create folders even if filesystem watching is disabled (for filesystembrowser etc.)
    sources = [Source(**data) for data in config.storage.filesystem.sources]
    sources.sort(key=lambda s: s.name)


def shutdown():
    """Terminates this module; waits for all threads to complete."""
    global synchronizer, sources
    config.storage.filesystem.sources = [s.save() for s in sources]
    if synchronizer is not None:
        levels.real.filesystemDispatcher.disconnect(synchronizer.handleRealFileEvent)
        synchronizer.shouldStop.set()
        synchronizer.exit()
        synchronizer.wait()
        synchronizer = None
        application.dispatcher.emit(application.ModuleStateChangeEvent("filesystem", "disabled"))
    sources = None
    logger.debug("Filesystem module: shutdown complete")


class Source(QtCore.QObject):

    folderStateChanged = QtCore.pyqtSignal(object)
    fileStateChanged = QtCore.pyqtSignal(object)

    def __init__(self, name, path, domain, enabled):
        super().__init__()
        self.name = name
        self.path = path
        if isinstance(domain, int):
            self.domain = domains.domainById(domain)
        else:
            self.domain = domain
        self.enabled = enabled
        self.scanState = ScanState.notScanning
        self.scanTimer = QtCore.QTimer()
        self.scanTimer.setInterval(200)
        self.scanTimer.timeout.connect(self.checkScan)
        if self.enabled:
            self.init()

    def init(self):
        self.files = {}
        self.folders = {}
        self.hashThread = HashThread()
        self.scanInterrupted = False
        logger.debug('loading filesystem source {}'.format(self.name))
        self.loadFolders()
        self.loadDBFiles()
        self.loadNewFiles()
        for folder in self.folders.values():
            if folder.empty():
                logger.debug('empty folder {} '.format(folder))
        QtCore.QTimer.singleShot(100, self.scan)
        levels.real.filesystemDispatcher.connect(self.handleRealFileEvent)


    def loadFolders(self):
        """Load the folders table from the database.

        Creates the tree of Directory objects and initializes self.directories and
        self.tableFolders.
        """
        for path, state in db.query("SELECT path, state FROM {p}folders WHERE path LIKE "
                                    + "'{}%' ORDER BY LENGTH(path)".format(self.path)):
            if path == self.path: # root folder first
                folder = Folder(path=self.path, parent=None)
            else:
                parentName = os.path.split(path)[0]
                parent = self.folders[parentName]
                folder = Folder(path, parent)
            folder.state = FilesystemState(state)
            self.folders[folder.path] = folder

    def loadDBFiles(self):
        """Load files table.

        Adds them to self.files and self.dbFiles, and to the Directory objects in memory.
        It might happen that the folders table does not contain the directory of some DB file (e.g.
        if Maestro was exited unexpectedly). In such a case the folders table is augmented by that
        directory.

        This method returns a list of Tracks (if any) which are in the files table but have no hash
        set.
        """
        ans = db.query("SELECT element_id, url, hash, verified FROM {p}files WHERE url LIKE "
                       + "'{}%'".format('file://' + self.path)) #TODO: escape!!!!
        for elid, urlstring, elhash, verified in ans:
            url = BackendURL.fromString(urlstring)
            if url.scheme != "file":
                continue
            file = File(url, id=elid, verified=db.getDate(verified), state=FilesystemState.synced,
                        hash=elhash)
            self.files[url.path] = file
            dir = self.getFolder(url.directory, storeNew=True)[0]
            dir.add(file)

    def loadNewFiles(self):
        """Load the newfiles table and add the files to self.files.

        URLs from newfiles already contained in files are deleted.
        """
        newDirectories = []
        for urlstring, elhash, verified in db.query("SELECT url, hash, verified FROM {p}newfiles "
            + "WHERE url LIKE '{}%'".format('file://' + self.path)): # TODO: escape path!!
            file = File(BackendURL.fromString(urlstring))
            if file.url.path in self.files:
                logger.warning("url {} is BOTH n files and newfiles!".format(urlstring))
                db.query('DELETE FROM {p}newfiles WHERE url=?', urlstring)
                continue
            file.hash = elhash
            file.verified = db.getDate(verified)
            file.state = FilesystemState.unsynced
            self.files[file.url.path] = file
            dir, newDirs = self.getFolder(file.url.directory, storeNew=True)
            dir = self.folders[file.url.directory]
            dir.add(file)
            newDirectories += newDirs

    def getFolder(self, path, storeNew=False):
        """Get a :class:`Folder` object for *path*.

        If necessary, the path and potential parents are created and inserted into self.directories
        (but not into the database). The result is a pair consisting of the requested Directory and
        a list of newly created Directory objects.
        When *storeNew* is True and new directories were created, they will be inserted into the
        database. Otherwise the caller is responsible for that.
        """
        if path is None:
            return None, []
        if path in self.folders:
            return self.folders[path], []
        parentPath = None if path == '/' else split(path)[0]
        parent, new = self.getFolder(parentPath)
        dir = Folder(path, parent)
        self.folders[path] = dir
        if storeNew:
            self.storeFolders(new + [dir])
        return dir, new + [dir]

    def storeFolders(self, folders):
        """Insert the given list of :class:`Folder` objects into the folders table."""
        if len(folders) > 0:
            db.multiQuery("INSERT INTO {p}folders (path, state) VALUES(?,?)",
                          [(dir.path, dir.state.value) for dir in folders])

    def storeNewFiles(self, newfiles):
        if len(newfiles):
            logger.debug('inserting {} new files into newfiles table'.format(len(newfiles)))
            db.multiQuery('INSERT INTO {p}newfiles (url, hash, verified) VALUES (?,?,?)',
                          [(str(file.url), file.hash,
                           file.verified.strftime("%Y-%m-%d %H:%M:%S")) for file in newfiles])

    def updateFolders(self, folders=None):
        if folders is None:
            folders = sorted(self.folders.values(), key=lambda f: f.path, reverse=True)
        changes = []
        for folder in folders:
            for changed in folder.updateState(False):
                changes.append((changed.state.value, changed.path))
                self.folderStateChanged.emit(changed.path)
        if len(changes):
            db.multiQuery('UPDATE {p}folders SET state=? WHERE path=?', changes)

    def removeFiles(self, files):
        removedFolders = []
        urlstrings = []
        for file in files:
            folder = file.folder
            folder.files.remove(file)
            while folder.empty():
                removedFolders.append((folder.path,))
                del self.folders[folder.path]
                if folder.parent:
                    folder.parent.subdirs.remove(folder)
                    folder = folder.parent
                else:
                    break
            urlstrings.append((str(file.url),))
            del self.files[file.url.path]
        db.multiQuery("DELETE FROM {p}newfiles WHERE url=?", urlstrings)
        db.multiQuery('DELETE FROM {p}folders WHERE path=?', removedFolders)

    def scan(self):
        """Initiates a filesystem scan in order to synchronize OMG's database with the real
        filesystem layout."""
        self.fsFiles = {}
        self.modifiedTags = {}
        self.changedHash = {}
        self.missingDB = []
        self.fsThread = threading.Thread(target=readFilesystem, args=(self.path, self.fsFiles),
                                         daemon=True)
        self.fsThread.start()
        self.scanInterrupted = False
        self.scanState = ScanState.initialScan
        self.scanTimer.start(200)

    def checkScan(self):
        if self.scanState in (ScanState.computingHashes, ScanState.realHashOnly) \
                or self.scanInterrupted:
            self.checkHashes()
        elif self.scanState == ScanState.initialScan:
            if not self.fsThread.is_alive():
                self.handleInitialScan()
        elif self.scanState == ScanState.checkModified:
            if not self.fsThread.is_alive():
                self.analyzeScanResult()

    def handleInitialScan(self):
        # add newly found files to newfiles table (also creating folders entries)
        newfolders = []
        newfiles = []
        requestHash = []
        for path, stamp in self.fsFiles.items():
            if path in self.files:
                file = self.files[path]
            else:
                dir, new = self.getFolder(dirname(path))
                file = File(FileURL(path))
                dir.add(file)
                newfolders.extend(new)
                newfiles.append(file)
                self.files[path] = file
            if file.hash is None or (file.id is None and file.verified < stamp):
                requestHash.append((int(file.id is None), path))

        self.storeNewFiles(newfiles)
        self.storeFolders(newfolders)
        # remove missing new files
        missingNew = [file for path, file in self.files.items()
                      if path not in self.fsFiles and file.id is None]
        if len(missingNew):
            logger.debug('removing {} missing new files'.format(len(missingNew)))
            self.removeFiles(missingNew)
        # store missing DB files
        self.missingDB = [file for path, file in self.files.items()
                          if path not in self.fsFiles and file.id is not None]
        # update folder states
        self.updateFolders()
        # compute missing hashes, if necessary
        if len(requestHash):
            print('hash of {} files missing'.format(len(requestHash)))
            self.scanState = ScanState.computingHashes
            self.hashThread.lastJobDone.clear()
            for elem in requestHash:
                self.hashThread.jobQueue.put(elem)
            self.scanTimer.start(5000)
        else:
            self.scanCheckModified()

    def checkHashes(self):
        finish = self.hashThread.lastJobDone.is_set()
        hashIds = []
        hashUrls = []
        try:
            while True:
                path, hash = self.hashThread.resultQueue.get(False)
                if path not in self.files:
                    continue
                file = self.files[path]
                file.hash = hash
                if file.id:
                    hashIds.append((hash, file.id))
                else:
                    hashUrls.append((hash, str(file.url)))
        except queue.Empty:
            if len(hashIds):
                db.multiQuery('UPDATE {p}files SET hash=? WHERE element_id=?', hashIds)
            if len(hashUrls):
                db.multiQuery('UPDATE {p}newfiles SET hash=?, verified=CURRENT_TIMESTAMP '
                              'WHERE url=?', hashUrls)
        if finish:
            if self.scanInterrupted:
                self.scan()  # re-initialize scan after all hashes are complete
            else:
                self.scanTimer.stop()
                if self.scanState == ScanState.computingHashes:
                    self.scanCheckModified()

    def scanCheckModified(self):
        self.scanState = ScanState.checkModified
        toCheck = []
        for path, stamp in self.fsFiles.items():
            file = self.files[path]
            if file.id is not None and stamp > file.verified:
                logger.debug('track {} modified'.format(basename(path)))
                toCheck.append(path)
        if len(toCheck):
            self.fsThread = threading.Thread(target=checkFiles,
                                             args=(toCheck, self.modifiedTags, self.changedHash),
                                             daemon=True)
            self.fsThread.start()
            self.scanTimer.start(1000)
        else:
            self.analyzeScanResult()

    def analyzeScanResult(self):
        if len(self.modifiedTags) > 0:
            logger.debug("detected {} files with modified tags".format(len(self.modifiedTags)))
            from . import dialogs
            hashUpdates = []
            for file, (hash, dbTags, fsTags) in self.modifiedTags.items():
                dialog = dialogs.ModifiedTagsDialog(file, dbTags, fsTags)
                dialog.exec_()
                if dialog.result() == dialog.Accepted:
                    if dialog.choice == 'DB':
                        backendFile = file.url.getBackendFile()
                        backendFile.readTags()
                        backendFile.tags = dbTags.withoutPrivateTags()
                        backendFile.saveTags()
                    else:
                        stack.clear()
                        diff = tags.TagStorageDifference(dbTags.withoutPrivateTags(), fsTags)
                        levels.real._changeTags({levels.real.get(file.id) : diff }, dbOnly=True)
                    file.verified = datetime.now(timezone.utc)
                    hashUpdates.append((hash, str(file.url)))
        if len(self.missingDB) > 0: # some files have been (re)moved outside Maestro
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

    def save(self):
        return {'name': self.name,
                'path': self.path,
                'domain': self.domain.id,
                'enabled': self.enabled}
    
    def contains(self, path):
        path = os.path.normpath(path)
        return path.startswith(os.path.normpath(self.path))

    def folderState(self, path):
        if path in self.folders:
            return self.folders[path].state
        return FilesystemState.unknown

    def fileState(self, path):
        if path in self.files:
            return self.files[path].state
        return FilesystemState.unknown

    def moveFile(self, file, newUrl):
        """Internally move *file* to *newUrl* by updating the folders and their states.

        This does not alter the filesystem and normally also not the database. The exception is
        the target URL already exist in self.files; in that case it is removed from newfiles.
        Also if newUrl is in a directory not yet contained in self.directories it (and potential
        parents which are also new) is added to the folders table.
        """
        newDir = self.getFolder(newUrl.directory, storeNew=True)[0]
        oldDir = file.folder
        oldDir.files.remove(file)
        if newUrl.path in self.files:
            existingFile = self.files[newUrl.path]
            newDir.files.remove(existingFile)
            db.query('DELETE FROM {p}newfiles WHERE url=?', str(newUrl))
        newDir.add(file)
        del self.files[file.url.path]
        file.url = newUrl
        self.files[newUrl.path] = file
        stateChanges = newDir.updateState(True)
        if oldDir != newDir:
            stateChanges += oldDir.updateState(True)
        self.updateFolders(stateChanges)
        self.fileStateChanged.emit(newUrl.path)

    def handleRealFileEvent(self, event):
        """Handle an event issued by levels.real if something has affected the filesystem."""
        if self.scanState != ScanState.notScanning:
            self.scanInterrupted = True
        for oldURL, newURL in event.renamed:
            if oldURL.path in self.files:
                if self.files[oldURL.path].id is None:
                    db.query("DELETE FROM {p}newfiles WHERE url=?", str(oldURL))
                self.moveFile(self.files[oldURL.path], newURL)

        updateHash = []
        for url in event.modified:
            if url.path not in self.files:
                continue
            updateHash.append(url.path)  # recompute hash if file was modified

        modifiedDirs = []
        if len(event.added) > 0:
            db.multiQuery('DELETE FROM {p}newfiles WHERE url=?',
                          [(str(elem.url),) for elem in event.added])
            for elem in event.added:
                url = elem.url
                if url.path not in self.files:
                    dir = self.getFolder(url.directory, storeNew=True)[0]
                    file = File(url, state=FilesystemState.synced)
                    dir.addFile(file)
                    self.files[url.path] = file
                    updateHash.append(url.path)
                else:
                    dir = self.folders[url.directory]
                    file = self.files[url.path]
                if file.hash is None:
                    updateHash.append(url.path)
                file.id = elem.id
                modifiedDirs += dir.updateState(True)
                self.fileStateChanged.emit(url.path)
        if len(updateHash) > 0:
            self.hashThread.lastJobDone.clear()
            for path in updateHash:
                self.hashThread.jobQueue.put((-1, path))
            if self.scanState == ScanState.notScanning:
                self.scanTimer.start(5000)

        if len(event.removed) > 0:
            newFiles = []
            for url in event.removed:
                if url.path not in self.files:
                    continue # happens after removals in a LostFilesDialog
                file = self.files[url.path]
                newFiles.append(file)
                file.id = None
                modifiedDirs += file.folder.updateState(True)
            self.storeNewFiles(newFiles)
        self.updateFolders(modifiedDirs)

        if len(event.deleted) > 0:
            changedFolders = []
            urls = []
            for url in event.deleted:
                if url.path not in self.files:
                    continue
                urls.append((str(url),))
                file = self.files[url.path]
                file.folder.files.remove(file)
                changedFolders.extend(file.folder.updateState(True))
                del self.files[url.path]
            self.updateFolders(changedFolders)
            if len(urls) > 0:
                db.multiQuery("DELETE FROM {p}newfiles WHERE url=?", urls)


def readFilesystem(path, files):
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            absFilename = join(dirpath, filename)
            stamp = utils.files.mTimeStamp(absFilename)
            files[absFilename] = stamp


def checkFiles(files, tagDiffs, newHash):
    identifier = AcoustIDIdentifier()
    for file in files:
        hash = identifier(file.url.path)
        if file.id in levels.real:
            dbTags = levels.real.get(file.id).tags
        else:
            dbTags = db.tags(file.id)
        backendFile = file.url.getBackendFile()
        backendFile.readTags()
        if dbTags.withoutPrivateTags() != backendFile.tags:
            logger.debug('Detected modification on file "{}": tags differ'.format(file.url))
            tagDiffs[file] = (hash, dbTags, backendFile.tags)
        else:
            if hash != file.hash:
                logger.debug("audio data of {} modified!".format(file.url.path))
            newHash[file] = hash


class HashThread(threading.Thread):

    def __init__(self):
        super().__init__()
        self.jobQueue = queue.PriorityQueue()
        self.resultQueue = queue.Queue()
        self.daemon = True
        self.lastJobDone = threading.Event()
        self.start()

    def run(self):
        identifier = AcoustIDIdentifier()
        while True:
            prio, path = self.jobQueue.get()
            self.lastJobDone.clear()
            hash = identifier(path)
            logger.debug('worker computed hash {} of {}'.format(hash, path))
            self.resultQueue.put((path, hash))
            if self.jobQueue.empty():
                self.lastJobDone.set()


def sourceByName(name):
    for source in sources:
        if source.name == name:
            return source
    else: return None
    

def sourceByPath(path):
    for source in sources:
        if source.contains(path):
            return source
    else: return None
    

def isValidSourceName(name):
    return name == name.strip() and 0 < len(name) <= 64


def addSource(**data):
    source = Source(**data)
    stack.push(translate("Filesystem", "Add source"), 
               stack.Call(_addSource, source),
               stack.Call(_deleteSource, source))


def _addSource(source):
    sources.append(source)
    sources.sort(key=lambda s: s.name)
    application.dispatcher.emit(SourceChangeEvent(constants.ADDED, source))
    
def deleteSource(source):
    stack.push(translate("Filesystem", "Delete source"),
               stack.Call(_deleteSource, source), 
               stack.Call(_addSource, source))


def _deleteSource(source):
    sources.remove(source)
    application.dispatcher.emit(SourceChangeEvent(constants.DELETED, source))
    

def changeSource(source, **data):
    oldData = {attr: getattr(source, attr) for attr in ['name', 'path', 'domain', 'enabled']}
    stack.push(translate("Filesystem", "Change source"),
               stack.Call(_changeSource, source, data),
               stack.Call(_changeSource, source, oldData))


def _changeSource(source, data):
    for attr in ['name', 'path', 'domain', 'enabled']:
        if attr in data:
            setattr(source, attr, data[attr])
    application.dispatcher.emit(SourceChangeEvent(constants.CHANGED, source))


class SourceChangeEvent(application.ChangeEvent):
    """SourceChangeEvent are used when a source is added, changed or deleted."""
    def __init__(self, action, source):
        assert action in constants.CHANGE_TYPES
        self.action = action
        self.source = source
        

def getNewfileHash(url):
    """Return the hash of a file specified by *url* which is not yet in the database.
    
    If the hash is not known, returns None.
    """
    source = sourceByPath(url.path)
    if source.enabled and url.path in source.files:
        return source.files[url.path].hash


min_verified = datetime(1000,1,1, tzinfo=timezone.utc)


class File:

    def __init__(self, url, id=None,
                 verified=min_verified,
                 hash=None, state=FilesystemState.unknown):
        self.url = url
        self.id = id
        self.verified = verified
        self.hash = hash
        self.state = state
        self.folder = None

    def __str__(self):
        if self.id is not None:
            return "DB File[{}](url={})".format(self.id, self.url)
        return "New File(url={})".format(self.url)

    def __repr__(self):
        return 'File({})'.format(self.url)


class Folder:
    """A folder inside a source.

    This is used for efficient storing and updating of the folder state. A :class:`Folder` has lists
    for subfolders and files, a pointer to the parent directory (*None* for the root), and a state
    flag.
    """

    def __init__(self, path, parent):
        """Create the Folder in *path*. *parent* is the parent Folder object (possibly None).

        *path* is always a relative path. If a parent is given, the new directory is automatically
        added to its subdirs.
        """
        self.parent = parent
        self.path = path
        self.files = []
        self.subdirs = []
        self.state = FilesystemState.unknown
        if parent is not None:
            parent.subdirs.append(self)

    def add(self, file):
        """Adds *track* to the list self.tracks and updates track.directory."""
        file.folder = self
        self.files.append(file)

    def empty(self):
        return len(self.files) == 0 and len(self.subdirs) == 0

    def updateState(self, recurse=False):
        """Update the *state* attribute of this directory.

        The state is determined by the tracks inside the directory and the state of possible
        subdirectories.
        This method returns a list of folders whose states have changed.
        """
        ownState = FilesystemState.empty
        for file in self.files:
            ownState = ownState.combine(FilesystemState.synced)
            if file.id is None:
                ownState = ownState.combine(FilesystemState.unsynced)
        for dir in self.subdirs:
            ownState = ownState.combine(dir.state)
        if ownState != self.state:
            ret = [self]
            if recurse and self.parent:
                ret += self.parent.updateState(True)
            self.state = ownState
            return ret
        return []

    def __str__(self):
        return self.path


class SynchronizeHelper(QtCore.QObject):
    """An object living in the main event thread to change the files table and display GUIs."""
    

    def showLostTracksDialog(self, tracks):
        """To be called when lost tracks have been detected. Opens the respective dialog."""
        from . import dialogs
        dialog = dialogs.MissingFilesDialog([track.id for track in tracks])
        dialog.exec_()
        stack.clear()
        self._dialogResult = {"removed" : dialog.deleteAction.removedURLs,
                              "renamed" : dialog.setPathAction.setPaths } 
        self.dialogFinished.set()


class FileSystemSynchronizer(QtCore.QThread):

        
    def checkTrack(self, track):
        """Perform a check of *track* on the filesystem to find potential differences to the DB.
        
        This method checks the modification timestamp of the file. If it is newer than the track's
        *verified* attribute, then:
        - if it is a new track (not in files), recomputes the hash and updates newfiles
        - if it's in the DB, additionally the tags are checked and compared against those in the
          database. If they differ, a tuple (dbTags, fileTags) is returned, in any other case None.
        """
        modified = utils.files.mTimeStamp(track.url)
        if modified <= track.verified:
            return None
        logger.debug('checking track {}...'.format(basename(track.url.path)))
        newHash = self.idProvider(track.url)
        if track.id is None: # not in database
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
        track.verified = utils.files.mTimeStamp(url)
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
            with db.transaction():
                self.storeDirectories(newDirectories)
                self.updateDirectories(modifiedDirectories)
                self.storeNewTracks(newTracks)

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
            relPath = utils.files.relPath(root)
            if relPath == ".":
                relPath = ""
            self.tableFolders[relPath] = True
            dir, newDirs = self.getDirectory(relPath)
            newDirectories.update(newDirs)
            for file in files:
                if self.shouldStop.is_set():
                    break
                if not utils.files.hasKnownExtension(file):
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
        In case commited files are missing, we first try to detect moves by searching their hash
        in self.tracks. Otherwise a LostFilesDialog is requested from the helper.
        """
        if len(self.modifiedTags) > 0:
            logger.debug("files with modified tags: {}".format(self.modifiedTags,))
            self.helper.dialogFinished.clear()
            self._requestHelper.emit("showModifiedTagsDialog", (self.modifiedTags,))
            self.helper.dialogFinished.wait()
        if not all(self.dbTracks.values()): # some files have been (re)moved outside Maestro
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
        with db.transaction():
        
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
                track.verified = utils.files.mTimeStamp(url)
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
        
    @QtCore.pyqtSlot(str)
    def recheck(self, directory):
        for track in self.tracks.values():
            if directory == "" or track.url.path.startswith(directory+"/"):
                track.verified = datetime(MINYEAR, 1, 1, tzinfo=timezone.utc)
        self.scanFilesystem()
