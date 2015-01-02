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

from .. import application, logging, config, utils, database as db, stack
from ..filebackends import BackendURL
from ..filebackends.filesystem import FileURL
from ..core import levels, tags, domains

logger = logging.getLogger(__name__)

synchronizer = None
sources = None
min_verified = datetime(1000,1,1, tzinfo=timezone.utc)


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
        self.scanTimer = QtCore.QTimer()
        self.scanTimer.setInterval(200)
        self.scanTimer.timeout.connect(self.checkScan)
        if enabled:
            self.enable()

    def setEnabled(self, enabled):
        if enabled and not self.enabled:
            self.enable()
        if not enabled and self.enabled:
            self.disable()

    def enable(self):
        self.enabled = True
        self.files = {}
        self.folders = {}
        self.hashThread = HashThread()
        self.scanInterrupted = False
        self.scanState = ScanState.notScanning
        logger.debug('loading filesystem source {}'.format(self.name))
        self.loadFolders()
        self.loadDBFiles()
        self.loadNewFiles()
        QtCore.QTimer.singleShot(5000, self.scan)
        levels.real.filesystemDispatcher.connect(self.handleRealFileEvent)

    def disable(self):
        self.enabled = False
        if self.scanState != ScanState.notScanning:
            self.scanTimer.stop()
        levels.real.filesystemDispatcher.connect(self.handleRealFileEvent)

    def setPath(self, path):
        self.path = path
        if path != self.path and self.enabled:
            self.disable()
            self.enable()

    def loadFolders(self):
        """Load the folders table from the database.

        Creates the tree of Folder objects and initializes self.folders.
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
                       + "'{}%'".format('file://' + self.path.replace("'", "\\'")))
        for elid, urlstring, elhash, verified in ans:
            url = BackendURL.fromString(urlstring)
            if url.scheme != "file":
                continue
            self.addFile(url, id=elid, verified=db.getDate(verified), hash=elhash)

    def loadNewFiles(self):
        """Load the newfiles table and add the files to self.files.

        URLs from newfiles already contained in files are deleted.
        """
        newDirectories = []
        toDelete = []
        for urlstring, elhash, verified in db.query("SELECT url, hash, verified FROM {p}newfiles "
            + "WHERE url LIKE '{}%'".format('file://' + self.path.replace("'", "\\'"))):
            file = File(BackendURL.fromString(urlstring))
            if file.url.path in self.files:
                logger.warning("url {} is BOTH in files and newfiles!".format(urlstring))
                toDelete.append((urlstring,))
                continue
            file.hash = elhash
            file.verified = db.getDate(verified)
            self.files[file.url.path] = file
            dir, newDirs = self.getFolder(file.url.directory, storeNew=True)
            dir = self.folders[file.url.directory]
            dir.add(file)
            newDirectories += newDirs
        if len(toDelete):
            db.multiQuery('DELETE FROM {p}newfiles WHERE url=?', toDelete)

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

    def updateFolders(self, folders, emit=True):
        if len(folders):
            db.multiQuery('UPDATE {p}folders SET state=? WHERE path=?',
                          [(folder.state.value, folder.path) for folder in folders])
        if emit:
            for folder in folders:
                self.folderStateChanged.emit(folder.path)

    def removeFiles(self, files):
        """Removes given files from structure and database."""
        if len(files) == 0:
            return
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
        if len(urlstrings):
            db.multiQuery("DELETE FROM {p}newfiles WHERE url=?", urlstrings)
        if len(removedFolders):
            db.multiQuery('DELETE FROM {p}folders WHERE path=?', removedFolders)

    def scan(self):
        """Initiates a filesystem scan in order to synchronize OMG's database with the real
        filesystem layout.

        The filesystem scan consists of multiple stages:
        1. Walk through the filesystem, storing existing files / directories and modification
           timestamps of all files. This is performed in a different thread by the function
           :func:`readFilesystem`.
        2. Compare the results of 1. with the information stored in the Source's internal structure.
           This is done in :func:`handleInitialScan`.
        3. Compute missing hashes of files. This is done by the :class:`HashThread`. Afterwards,
           :func:`checkHashes` is called.
        4. For files that were modified since last verification, check if tags and/or audio data
           have changed. This is done in a separate thread by :func:`checkFiles`.
        5. Finally, :func:`analyzeScanResults` analyzes the results and, if necessary, displays
           lost files / changed tags dialogs to the user.
        """
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
        logger.debug('source {} scanning path {}'.format(self.name, self.path))

    def checkScan(self):
        """Called periodically by a timer while threaded filesystem operations are running. Checks
        if these operations are finished and calls the apropriate handler method in that case.
        """
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
        """Called when the initial filesystem walk is finished. Removes newfiles that have not been
        found anymore, adds newly found files, stores a list of missing committed files, and updates
        folder states if necessary.
        """
        # add newly found files to newfiles table (also creating folders entries)
        newfolders = []
        newfiles = []
        requestHash = []
        for path, stamp in self.fsFiles.items():
            if path in self.files:
                file = self.files[path]
            else:
                file, newdirs = self.addFile(FileURL(path), storeFolders=False, storeFile=False)
                newfolders.extend(newdirs)
                newfiles.append(file)
            if file.hash is None or (file.id is None and file.verified < stamp):
                requestHash.append((int(file.id is None), path))

        self.storeNewFiles(newfiles)
        self.storeFolders(newfolders)
        # remove missing new files
        missingNew = [file for path, file in self.files.items()
                      if path not in self.fsFiles and file.id is None]
        if len(missingNew):
            self.removeFiles(missingNew)
        # store missing DB files
        self.missingDB = [file for path, file in self.files.items()
                          if path not in self.fsFiles and file.id is not None]
        if len(self.missingDB):
            logger.warning('{} files in DB missing on filesystem'.format(len(self.missingDB)))
        # update folder states
        folders = sorted(self.folders.values(), key=lambda f: f.path, reverse=True)
        changedFolders = []
        for folder in folders:
            changedFolders.extend(folder.updateState(False))
        self.updateFolders(changedFolders, emit=False)
        # remove empty folders
        emptyFolders = [folder for folder in self.folders.values() if folder.empty()]
        if len(emptyFolders):
            for folder in emptyFolders:
                del self.folders[folder.path]
                if folder.parent:
                    folder.parent.subdirs.remove(folder)
            db.multiQuery('DELETE FROM {p}folders WHERE path=?', [(f.path,) for f in emptyFolders])
        # compute missing hashes, if necessary
        if len(requestHash):
            self.scanState = ScanState.computingHashes
            self.hashThread.lastJobDone.clear()
            for elem in requestHash:
                self.hashThread.jobQueue.put(elem)
            self.scanTimer.start(5000)
        else:
            self.scanCheckModified()

    def checkHashes(self):
        """Called periodically during hashes computation. If new hashes have been computed, updates
        the database. If hash computation is finished, calls the appropriate next function.
        """
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
                db.multiQuery('UPDATE {p}files SET hash=?, verified=CURRENT_TIMESTAMP '
                              'WHERE element_id=?', hashIds)
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
                else:
                    self.scanState = ScanState.notScanning

    def scanCheckModified(self):
        self.scanState = ScanState.checkModified
        toCheck = []
        for path, stamp in self.fsFiles.items():
            file = self.files[path]
            if file.id is not None and stamp > file.verified:
                logger.debug('track {} modified'.format(basename(path)))
                toCheck.append(file)
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
            for file, (hash, dbTags, fsTags) in self.modifiedTags.items():
                dialog = dialogs.ModifiedTagsDialog(file, dbTags, fsTags)
                dialog.exec_()
                if dialog.result() == dialog.Accepted:
                    file.verified = datetime.now(timezone.utc)
                    self.changedHash[file] = hash
        if len(self.changedHash):
            db.multiQuery('UPDATE {p}files SET hash=?, verified=CURRENT_TIMESTAMP WHERE url=?',
                          [(hash, str(file.url)) for file, hash in self.changedHash.items()])
        if len(self.missingDB) > 0: # some files have been (re)moved outside Maestro
            missingHashes = {} # hashes of missing files mapped to Track objects
            for file in self.missingDB:
                if file.hash is not None:
                    missingHashes[file.hash] = file
            if len(missingHashes) > 0:
                # search newfiles for the missing hashes in order to detect moves
                detectedMoves = []
                for file in self.files.values():
                    if file.id is None and file.hash in missingHashes:
                        oldFile = missingHashes[file.hash]
                        detectedMoves.append((oldFile, file.url))
                        self.missingDB.remove(oldFile)
                        del missingHashes[file.hash]
                for file, newURL in detectedMoves:
                    db.query('UPDATE {p}files SET url=? WHERE element_id=?', str(newURL), file.id)
                    logger.info('renamed outside maestro: {}->{}'.format(file.url, newURL))
                    self.moveFile(file, newURL)
            if len(self.missingDB) > 0:
                # --> some files are lost. Show a dialog and let the user fix this
                from . import dialogs
                dialog = dialogs.MissingFilesDialog([file.id for file in self.missingDB])
                dialog.exec_()
                stack.clear()
                for oldURL, newURL in dialog.setPathAction.setPaths:
                    self.moveFile(self.files[oldURL.path], newURL.path)
                self.removeFiles([self.files[url.path] for url in dialog.deleteAction.removedURLs])
        self.scanState = ScanState.notScanning
        self.scanTimer.stop()
        logger.debug('scan finished')

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
            if self.files[path].id:
                return FilesystemState.synced
            else:
                return FilesystemState.unsynced
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
            newDir.files.remove(self.files[newUrl.path])
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

    def addFile(self, url, id=None, hash=None, verified=min_verified,
                storeFolders=True, storeFile=True):
        dir, newdirs = self.getFolder(url.directory, storeNew=storeFolders)
        file = File(url, id=id, hash=hash, verified=verified)
        dir.add(file)
        self.files[url.path] = file
        return file, newdirs

    def handleRealFileEvent(self, event):
        """Handle an event issued by levels.real if something has affected the filesystem.

        Updates the internal directory tree structure, and recomputes hashes if necessary.
        """
        if self.scanState != ScanState.notScanning:
            self.scanInterrupted = True
        updateHash = set()  # paths for which new hashes need to be computed
        updatedDirs = []
        for oldURL, newURL in event.renamed:
            if oldURL.path in self.files:
                if self.files[oldURL.path].id is None:
                    db.query('DELETE FROM {p}newfiles WHERE url=?', str(oldURL))
                if self.contains(newURL.path):
                    self.moveFile(self.files[oldURL.path], newURL)
                else:
                    self.removeFiles([self.files[oldURL.path]])
            elif self.contains(newURL.path):
                elem = levels.real.fetch(newURL)
                self.addFile(url=newURL, id=elem.id)
                updateHash.add(newURL.path)
            if self.contains(newURL.path):
                dir, _ = self.getFolder(newURL.directory, storeNew=True)
                updatedDirs.extend(dir.updateState(True))
        for url in event.modified:
            if self.contains(url.path):
                updateHash.add(url.path)  # recompute hash if file was modified
        if len(event.added) > 0:
            db.multiQuery('DELETE FROM {p}newfiles WHERE url=?',
                          [(str(elem.url),) for elem in event.added])
            for elem in event.added:
                if self.contains(elem.url.path):
                    url = elem.url
                    if url.path not in self.files:
                        file = self.addFile(url, id=elem.id)[0]
                    else:
                        file = self.files[url.path]
                    if file.hash is None:
                        updateHash.add(url.path)
                    file.id = elem.id
                    dir = self.folders[url.directory]
                    updatedDirs += dir.updateState(True)
                    self.fileStateChanged.emit(url.path)
        if len(updateHash) > 0:
            self.hashThread.lastJobDone.clear()
            for path in updateHash:
                self.hashThread.jobQueue.put((-1, path))
            if self.scanState == ScanState.notScanning:
                self.scanState = ScanState.realHashOnly
                self.scanTimer.start(5000)

        if len(event.removed) > 0:  # removed means deleted from DB, but not filesystem
            newFiles = []
            for url in event.removed:
                if url.path not in self.files:
                    continue
                file = self.files[url.path]
                newFiles.append(file)
                file.id = None
                self.fileStateChanged.emit(url.path)
                updatedDirs += file.folder.updateState(True)
            self.storeNewFiles(newFiles)

        if len(event.deleted) > 0:
            urls = []
            for url in event.deleted:
                if url.path not in self.files:
                    continue
                urls.append((str(url),))
                file = self.files[url.path]
                file.folder.files.remove(file)
                updatedDirs.extend(file.folder.updateState(True))
                del self.files[url.path]
            if len(urls) > 0:
                db.multiQuery("DELETE FROM {p}newfiles WHERE url=?", urls)
        self.updateFolders(updatedDirs)


def readFilesystem(path, files):
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            if utils.files.isMusicFile(filename):
                absFilename = join(dirpath, filename)
                stamp = utils.files.mTimeStamp(absFilename)
                files[absFilename] = stamp


def checkFiles(files, tagDiffs, newHash):
    identifier = AcoustIDIdentifier()
    for file in files:
        hash = identifier(file.url.path)
        if file.id in levels.real:
            dbTags = levels.real.collect(file.id).tags
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
    application.dispatcher.emit(SourceChangeEvent(application.ChangeType.added, source))
    
def deleteSource(source):
    stack.push(translate("Filesystem", "Delete source"),
               stack.Call(_deleteSource, source), 
               stack.Call(_addSource, source))


def _deleteSource(source):
    sources.remove(source)
    application.dispatcher.emit(SourceChangeEvent(application.ChangeType.deleted, source))
    

def changeSource(source, **data):
    oldData = {attr: getattr(source, attr) for attr in ['name', 'path', 'domain', 'enabled']}
    stack.push(translate("Filesystem", "Change source"),
               stack.Call(_changeSource, source, data),
               stack.Call(_changeSource, source, oldData))


def _changeSource(source, data):
    if 'name' in data:
        source.name = data['name']
    if 'path' in data:
        source.setPath(data['path'])
    if 'domain' in data:
        source.domain = data['domain']
    if 'enabled' in data:
        source.setEnabled(data['enabled'])
    application.dispatcher.emit(SourceChangeEvent(application.ChangeType.changed, source))


class SourceChangeEvent(application.ChangeEvent):
    """SourceChangeEvent are used when a source is added, changed or deleted."""
    def __init__(self, action, source):
        assert isinstance(action, application.ChangeType)
        self.action = action
        self.source = source
        

def getNewfileHash(url):
    """Return the hash of a file specified by *url* which is not yet in the database.
    
    If the hash is not known, returns None.
    """
    source = sourceByPath(url.path)
    if source and source.enabled and url.path in source.files:
        return source.files[url.path].hash


class File:

    def __init__(self, url, id=None, verified=min_verified, hash=None):
        self.url = url
        self.id = id
        self.verified = verified
        self.hash = hash
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
            self.state = ownState
            if recurse and self.parent:
                ret += self.parent.updateState(True)
            return ret
        return []

    def __str__(self):
        return self.path

    def __repr__(self):
        return 'Folder({})'.format(self.path)
