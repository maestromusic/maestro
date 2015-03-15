# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2015 Martin Altmayer, Michael Helmling
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

import enum, collections
import os.path
import time
import threading, queue

from PyQt5 import QtCore

from maestro import logging, stack, utils, config
from maestro import database as db
from maestro.core import domains, levels, urls
from maestro.filesystem.identification import AudioFileIdentifier


class FilesystemState(enum.Enum):
    """Synchronisation state of a folder or file in a source directory."""
    empty = 0
    synced = 1
    unsynced = 2
    unknown = 3

    def combine(self, other):
        """Compute the cumulative state. For example, if a directory contains synced as well as
        unsynced files / subdirectories, its combined state is unsynced.
        """
        return FilesystemState(max(self.value, other.value))

    def fileIcon(self):
        """Return an icon that is appropriate for a file of the respective state."""
        if self is FilesystemState.synced:
            return utils.images.icon('audio-x-synchronized')
        if self is FilesystemState.unsynced:
            return utils.images.icon('audio-x-unsynchronized')
        return utils.images.icon('audio-x-generic')

    def folderIcon(self):
        """Return an icon that is appropriate for a folder of the respective state."""
        if self is FilesystemState.synced:
            return utils.images.icon('folder-synchronized')
        if self is FilesystemState.unsynced:
            return utils.images.icon('folder-unsynchronized')
        return utils.images.icon('folder')


class File:
    """Representation of a tracked file in a Source."""
    def __init__(self, url: urls.URL, id=None, verified=0, hash=None):
        self.url = url
        self.id = id
        self.verified = verified
        self.hash = hash
        """:type : Folder"""
        self.folder = None

    def __str__(self):
        return "File[{}]({})".format(self.id or 'new', self.url)

    def __repr__(self):
        return 'File({})'.format(self.url)


class Folder:
    """Represents a tracked folder inside a source.

    Folder objects are used to allow efficient querying and update of the synchronisation state of a tracked
    directory.

    Args:
        path: absolute path of the folder
        parent: parent Folder object; may be None for the source's root
    """

    def __init__(self, path: str, parent):
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

    def updateState(self, recurse=False, emit=None):
        """Update the *state* attribute of this directory.

        The state is determined by the tracks inside the directory and the state of possible
        subdirectories.
        """
        ownState = FilesystemState.empty
        for file in self.files:
            ownState = ownState.combine(FilesystemState.synced)
            if file.id is None:
                ownState = ownState.combine(FilesystemState.unsynced)
        for dir in self.subdirs:
            ownState = ownState.combine(dir.state)
        if ownState != self.state:
            self.state = ownState
            if emit:
                emit.emit(self.path)
            if recurse and self.parent:
                self.parent.updateState(True, emit)

    def __str__(self):
        return self.path

    def __repr__(self):
        return 'Folder({})'.format(self.path)


class ScanState(enum.Enum):
    """State of the filesystem scan. Used internally in :class:`Source`."""
    notScanning = 0
    initialScan = 1
    computingHashes = 2
    checkModified = 3
    realHashOnly = 4

HashRequest = collections.namedtuple('HashRequest', 'priority path')


class Source(QtCore.QObject):
    """A source is a path in the filesystem that is watched by maestro. If enabled, maestro
    periodically scans the filesystem in order to detect differences between the layouts of the
    database and the filesystem.

    :param name: Name of the source (free-form string)
    :type name: str
    :param path: Root path of the source.
    :type path: str
    :param domain: Domain associated to this source (either Domain object or its ID).
    :type domain: domains.Domain | int
    :param enabled: Determines if filesystem tracking is enabled.
    """

    folderStateChanged = QtCore.pyqtSignal(object)
    fileStateChanged = QtCore.pyqtSignal(object)

    def __init__(self, name, path, domain, extensions, enabled: bool):
        super().__init__()
        self.name = name
        self.path = path
        self.domain = domains.domainById(domain) if isinstance(domain, int) else domain
        self.scanTimer = QtCore.QTimer()
        self.scanTimer.setInterval(200)
        self.scanTimer.timeout.connect(self.checkScan)
        self.extensions = list(extensions)
        self.enabled = False
        if enabled and not config.options.filesystem.disable:
            self.enable()
        else:
            self.files = {}

    def setEnabled(self, enabled: bool):
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
        logging.debug(__name__, 'loading filesystem source {}'.format(self.name))
        self.load()
        # update all folder states. Start from children to avoid recursive state updates
        for folder in sorted(self.folders.values(), key=lambda f: f.path, reverse=True):
            folder.updateState(False)
        QtCore.QTimer.singleShot(5000, self.scan)
        levels.real.filesystemDispatcher.connect(self.handleRealFileEvent)

    def disable(self):
        self.enabled = False
        if self.scanState != ScanState.notScanning:
            self.scanTimer.stop()
        self.hashThread.stop()
        levels.real.filesystemDispatcher.disconnect(self.handleRealFileEvent)

    def setPath(self, path):
        """Change the path of this source to *path*. Will recreate internal structures if changed.
        """
        self.path = path
        if path != self.path and self.enabled:
            self.disable()
            self.enable()

    def setExtensions(self, extensions):
        self.extensions = extensions
        if self.enabled:
            self.disable()
            self.enable()

    def load(self):
        """Load files and newfiles tables, creating the internal structure of File and Folder objects."""
        for elid, urlstring, elhash, verified in db.query(
                    'SELECT element_id, url, hash, verified FROM {p}files WHERE url LIKE ' +
                        "'{}%'".format('file://' + self.path.replace("'", "\\'"))):
            url = urls.URL(urlstring)
            if url.extension in self.extensions:
                self.addFile(url, id=elid, verified=verified, hash=elhash, store=False)

        toDelete = []
        for urlstring, elhash, verified in db.query("SELECT url, hash, verified FROM {p}newfiles "
            + "WHERE url LIKE '{}%'".format('file://' + self.path.replace("'", "\\'"))):
            url = urls.URL(urlstring)
            if url.extension in self.extensions:
                if url.path in self.files:
                    toDelete.append((urlstring,))
                    continue
                self.addFile(url, hash=elhash, verified=verified, store=False)
            else:
                toDelete.append((urlstring,))
        if len(toDelete):
            db.multiQuery('DELETE FROM {p}newfiles WHERE url=?', toDelete)

    def getFolder(self, path):
        """Get a :class:`Folder` object for *path*.
        :type path: str | None
        :rtype : Folder | None

        If necessary, the path and potential parents are created and inserted into self.folders.
        """
        if path is None:
            return None
        if path in self.folders:
            return self.folders[path]
        parentPath = None if path == self.path else os.path.split(path)[0]
        folder = Folder(path, parent=self.getFolder(parentPath))
        self.folders[path] = folder
        return folder

    def storeNewFiles(self, newfiles):
        """Inserts the given list of :class:`File` objects into the newfiles table."""
        if len(newfiles):
            db.multiQuery('INSERT INTO {p}newfiles (url, hash, verified) VALUES (?,?,?)',
                          [(str(file.url), file.hash, file.verified) for file in newfiles])

    def updateHashesAndVerified(self, files):
        """Updates hash and verification timestamp of given *files* in the database to the values stored in
        the according File objects.
        """
        dbFiles = [(f.hash, f.verified, f.id) for f in files if f.id]
        newFiles = [(f.hash, f.verified, str(f.url)) for f in files if not f.id]
        if len(dbFiles):
            db.multiQuery('UPDATE {p}files SET hash=?, verified=? WHERE element_id=?', dbFiles)
        if len(newFiles):
            db.multiQuery('UPDATE {p}newfiles SET hash=?, verified=? WHERE url=?', newFiles)

    def scan(self):
        """Initiates a filesystem scan in order to synchronize Maestro's database with the real
        filesystem layout.

        The filesystem scan consists of multiple stages:
        1. Walk through the filesystem, storing existing files / directories and modification
           timestamps of all files. This is performed in a different thread by readFilesystem().
        2. Compare the results of 1) with the Source's internal structures (handleInitialScan())
        3. Compute missing hashes of files (class HashThread). checkHashes() inserts them into DB.
        4. For files that were modified since last verification, check if tags and/or audio data
           have changed. This is done in a separate thread by checkFiles().
        5. Finally,nalyzeScanResults() analyzes the results and, if necessary, displays dialogs.
        """
        self.fsFiles = {}
        self.modifiedTags = queue.Queue()
        self.changedHash = queue.Queue()
        self.missingDB = []
        self.fsThread = threading.Thread(target=readFilesystem, args=(self.path, self), daemon=True)
        self.fsThread.start()
        self.scanInterrupted = False
        self.scanState = ScanState.initialScan
        self.scanTimer.start(200)
        logging.debug(__name__, 'source {} scanning path {}'.format(self.name, self.path))

    def checkScan(self):
        """Called periodically by a timer while threaded filesystem operations are running. Checks
        if these operations are finished and calls the apropriate handler method in that case to proceed
        to the next scan state.
        """
        if self.scanState in (ScanState.computingHashes, ScanState.realHashOnly) \
                or self.scanInterrupted:
            self.checkHashes()
        elif self.scanState == ScanState.initialScan:
            if not self.fsThread.is_alive():
                self.handleInitialScan()
        elif self.scanState == ScanState.checkModified:
            self.handleTagAndHashChanges()
            if not self.fsThread.is_alive():
                self.handleMissingFiles()

    def handleInitialScan(self):
        """Called when the initial filesystem walk is finished. Removes newfiles that have not been
        found anymore, adds newly found files, stores a list of missing committed files, and updates
        folder states if necessary.
        """
        # add newly found files to newfiles table (also creating folders entries)
        newfiles = []
        hashRequests = []
        for path, stamp in self.fsFiles.items():
            if path in self.files:
                file = self.files[path]
            else:
                url = urls.URL.fileURL(path)
                file = self.addFile(urls.URL.fileURL(path), store=False)
                newfiles.append(file)
            if file.hash is None or (file.id is None and file.verified < stamp):
                # for files with outdated verified that are in DB, we need to check if tags have changed
                # which is done later in the scan process
                hashRequests.append(HashRequest(priority=int(file.id is None), path=path))

        self.storeNewFiles(newfiles)
        # remove entries in newfiles that don't exist anymore
        self.removeFiles([file for path, file in self.files.items()
                           if file.id is None and path not in self.fsFiles])
        # store missing DB files for later usage
        self.missingDB = [file for path, file in self.files.items() if file.id and path not in self.fsFiles]
        if len(self.missingDB):
            logging.warning(__name__, '{} files in DB missing on filesystem'.format(len(self.missingDB)))
        # compute missing hashes, if necessary
        if len(hashRequests):
            logging.info(__name__, 'Hash value of {} files missing'.format(len(hashRequests)))
            self.scanState = ScanState.computingHashes
            self.hashThread.lastJobDone.clear()
            for elem in hashRequests:
                self.hashThread.jobQueue.put(elem)
            self.scanTimer.start(5000)  # check hash results every 5 seconds
        else:
            self.scanCheckModified()

    def checkHashes(self):
        """Called periodically during hashes computation. If new hashes have been computed, updates
        the database. If hash computation is finished, calls the appropriate next function.
        """
        finish = self.hashThread.lastJobDone.is_set()
        changedFiles = []
        try:
            while True:
                path, hash = self.hashThread.resultQueue.get(False)
                if path not in self.files:
                    continue
                file = self.files[path]
                file.hash = hash
                changedFiles.append(file)
        except queue.Empty:
            if len(changedFiles):
                logging.debug(__name__, 'Adding {} new file hashes to the database'.format(len(changedFiles)))
            self.updateHashesAndVerified(changedFiles)
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
            if file.id and stamp > file.verified:
                toCheck.append(file)
        if len(toCheck):
            logging.debug(__name__, '{} files modified since last check'.format(len(toCheck)))
            self.fsThread = threading.Thread(target=checkFiles, args=(toCheck, self), daemon=True)
            self.fsThread.start()
            self.scanTimer.start(1000)
        else:
            self.handleMissingFiles()

    def handleTagAndHashChanges(self):
        updates = []
        try:
            while True:
                file, hash, dbTags, fileTags = self.modifiedTags.get(False)
                from . import dialogs
                dialog = dialogs.ModifiedTagsDialog(file, dbTags, fileTags)
                dialog.exec_()
                if dialog.result() == dialog.Accepted:
                    file.verified = time.time()
                    file.hash = hash
                    updates.append(file)
        except queue.Empty:
            pass
        try:
            while True:
                file, hash = self.changedHash.get(False)
                file.verified = time.time()
                file.hash = hash
                updates.append(file)
        except queue.Empty:
            pass
        self.updateHashesAndVerified(updates)

    def handleMissingFiles(self):
        """Called after all missing hashes have been computed and all modified files have been examined for
        tag changes.
        """
        self.handleTagAndHashChanges()
        if len(self.missingDB) > 0:  # some files have been (re)moved outside Maestro
            missingHashes = {}  # hashes of missing files mapped to Track objects
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
                    logging.info(__name__, 'renamed outside maestro: {}->{}'.format(file.url, newURL))
                    self.moveFile(file, newURL)
            if len(self.missingDB) > 0:
                # --> some files are lost. Show a dialog and let the user fix this
                from . import dialogs
                dialog = dialogs.MissingFilesDialog([file.id for file in self.missingDB])
                dialog.exec_()
                stack.clear()
                for oldURL, newURL in dialog.setPathAction.setPaths:
                    self.moveFile(self.files[oldURL.path], newURL)
                self.removeFiles([self.files[url.path] for url in dialog.deleteAction.removedURLs])
        self.scanState = ScanState.notScanning
        self.scanTimer.stop()
        logging.debug(__name__, 'scan of source {} finished'.format(self.name))

    def save(self):
        return dict(name=self.name, path=self.path, domain=self.domain.id, extensions=self.extensions,
                    enabled=self.enabled)

    def contains(self, path) -> bool:
        """Tells whether the given *path* is contained in this source."""
        path = os.path.normpath(path)
        return path.startswith(os.path.normpath(self.path))

    def folderState(self, path) -> FilesystemState:
        """Returns the state of the folder given by *path*."""
        if self.enabled and path in self.folders:
            return self.folders[path].state
        return FilesystemState.unknown

    def fileState(self, path) -> FilesystemState:
        """Returns the state of the file given by *path*."""
        if path in self.files:
            if self.files[path].id:
                return FilesystemState.synced
            else:
                return FilesystemState.unsynced
        return FilesystemState.unknown

    def moveFile(self, file: File, newUrl: urls.URL):
        """Internally move *file* to *newUrl* by updating the folders and their states.

        This does not alter the filesystem and normally also not the database. The exception is
        the target URL already exist in self.files; in that case it is removed from newfiles.
        """
        newDir = self.getFolder(newUrl.directory)
        oldDir = file.folder
        oldDir.files.remove(file)
        if newUrl.path in self.files:
            newDir.files.remove(self.files[newUrl.path])
            db.query('DELETE FROM {p}newfiles WHERE url=?', str(newUrl))
        newDir.add(file)
        del self.files[file.url.path]
        file.url = newUrl
        self.files[newUrl.path] = file
        newDir.updateState(True, emit=self.folderStateChanged)
        if oldDir != newDir:
            oldDir.updateState(True, emit=self.folderStateChanged)
        self.fileStateChanged.emit(newUrl.path)

    def addFile(self, url: urls.URL, id=None, hash=None, verified=0, store=True) -> File:
        """Adds a new file with the given parameters to the internal structure. New folders will be
        created if necessary. IF *store* is *True* and *id* is None, store file in the newfiles table.
        """
        dir = self.getFolder(url.directory)
        file = File(url, id=id, hash=hash, verified=verified)
        dir.add(file)
        self.files[url.path] = file
        if store and id is None:
            self.storeNewFiles([file])
        return file

    def removeFiles(self, files):
        """Removes given files from structure and database.
        :type files: list of File
        """
        if len(files) == 0:
            return
        urlstrings = []
        for file in files:
            folder = file.folder
            folder.files.remove(file)
            while folder.empty():
                # recursively delete empty parent folders
                folder.updateState(False, emit=self.folderStateChanged)
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

    def handleRealFileEvent(self, event):
        """Handle an event issued by levels.real if something has affected the filesystem.

        Updates the internal directory tree structure, and recomputes hashes if necessary.
        """
        if self.scanState not in (ScanState.notScanning, ScanState.realHashOnly):
            self.scanInterrupted = True
        updateHash = set()  # paths for which new hashes need to be computed

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

        for url in event.modified:
            if self.contains(url.path):
                updateHash.add(url.path)  # recompute hash if file was modified

        if len(event.added) > 0:
            db.multiQuery('DELETE FROM {p}newfiles WHERE url=?', [(str(elem.url),) for elem in event.added])
            for elem in event.added:
                if self.contains(elem.url.path):
                    url = elem.url
                    if url.path not in self.files:
                        file = self.addFile(url, id=elem.id)
                    else:
                        file = self.files[url.path]
                    if file.hash is None:
                        updateHash.add(url.path)
                    file.id = elem.id
                    file.folder.updateState(True, emit=self.folderStateChanged)
                    self.fileStateChanged.emit(url.path)

        if len(updateHash) > 0:
            self.hashThread.lastJobDone.clear()
            for path in updateHash:
                self.hashThread.jobQueue.put(HashRequest(priority=-1, path=path))
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
                file.folder.updateState(True, emit=self.folderStateChanged)
            self.storeNewFiles(newFiles)

        if len(event.deleted) > 0:
            self.removeFiles([self.files[url.path] for url in event.deleted if url.path in self.files])

    def relPath(self, path):
        """Return the relative path to this source's directory. *path* must be within this source
        (see self.contains)."""
        return os.path.normpath(path)[len(self.path):]
    

def readFilesystem(path, source: Source):
    """Helper function that walks *path* and stores, for each found music file, an entry in source.fsFiles
    mapping its path to its modification timestamp.
    """
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            _, ext = os.path.splitext(filename)
            if len(ext) > 0 and ext[1:] in source.extensions:
                absFilename = os.path.join(dirpath, filename)
                stamp = os.path.getmtime(absFilename)
                source.fsFiles[absFilename] = stamp


def checkFiles(files: list, source: Source):
    """Compares database and filesystem state of *files*. If tags differ, adds an entry in
    *tagDiffs*. If the hash is different, adds an entry in *newHash*.
    """
    identifier = AudioFileIdentifier()
    for file in files:
        hash = identifier(file.url.path)
        if file.id in levels.real:
            dbTags = levels.real.collect(file.id).tags
        else:
            dbTags = db.tags.getStorage(file.id)
        backendFile = file.url.backendFile()
        backendFile.readTags()
        if dbTags.withoutPrivateTags() != backendFile.tags:
            logging.debug(__name__, 'Detected modification on file "{}": tags differ'.format(file.url))
            source.modifiedTags.put((file, hash, dbTags, backendFile.tags))
        else:
            if hash != file.hash:
                logging.debug(__name__, "audio data of {} modified!".format(file.url.path))
            else:
                logging.debug(__name__, 'updating verification timestamp of {}'.format(file.url.path))
            source.changedHash.put((file, hash))


class HashThread(threading.Thread):
    """Helper thread for :class:`Source` that computes file hashes for files in :attr:`jobQueue`.
    """
    def __init__(self):
        super().__init__()
        self.jobQueue = queue.PriorityQueue()
        self.resultQueue = queue.Queue()
        self.daemon = True
        self.lastJobDone = threading.Event()
        self.start()

    def stop(self):
        try:
            while True:
                self.jobQueue.get_nowait()
        except queue.Empty:
            pass

    def run(self):
        identifier = AudioFileIdentifier()
        while True:
            prio, path = self.jobQueue.get()
            self.lastJobDone.clear()
            hash = identifier(path)
            self.resultQueue.put((path, hash))
            if self.jobQueue.empty():
                self.lastJobDone.set()
