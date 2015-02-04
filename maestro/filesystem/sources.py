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

import enum
import os.path
import threading, queue
from datetime import datetime, timezone

from PyQt4 import QtCore

from maestro import logging, stack, utils
from maestro import database as db
from maestro.core import domains, levels, urls
from maestro.filesystem.identification import AcoustIDIdentifier

translate = QtCore.QCoreApplication.translate


minVerified = datetime(1000, 1, 1, tzinfo=timezone.utc)  # default date for never verified files


class FilesystemState(enum.Enum):
    """State of a folder or file in a source directory."""
    empty = 0
    synced = 1
    unsynced = 2
    unknown = 3

    def combine(self, other):
        """Compute the cumulative state. For example, if a directory contains synced as well as
        unsynced files / subdirectories, its combined state is unsynced.
        """
        return FilesystemState(max(self.value, other.value))


class File:
    """Representation of a monitored file in a Source."""
    def __init__(self, url: urls.URL, id=None, verified=minVerified, hash=None):
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


class ScanState(enum.Enum):
    """State of the filesystem scan. Used internally in :class:`Source`."""
    notScanning = 0
    initialScan = 1
    computingHashes = 2
    checkModified = 3
    realHashOnly = 4


class Source(QtCore.QObject):
    """A source is a path in the filesystem that is watched by maestro. If enabled, maestro
    periodically scans the filesystem in order to detect differences between the layouts of the
    database and the filesystem.

    :param str name: Name of the source (free-form string)
    :param str path: Root path of the source.
    :param object domain: Domain associated to this source (either Domain object or its ID).
    :param bool enabled: Determines if filesystem scanning is enabled.
    """

    folderStateChanged = QtCore.pyqtSignal(object)
    fileStateChanged = QtCore.pyqtSignal(object)

    def __init__(self, name, path, domain, enabled):
        super().__init__()
        self.name = name
        self.path = path
        self.domain = domains.domainById(domain) if isinstance(domain, int) else domain
        self.scanTimer = QtCore.QTimer()
        self.scanTimer.setInterval(200)
        self.scanTimer.timeout.connect(self.checkScan)
        self.enabled = False
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
        logging.debug(__name__, 'loading filesystem source {}'.format(self.name))
        self.loadFolders() # TODO: could be done in worker thread to decrease startup time
        self.loadDBFiles()
        self.loadNewFiles()
        QtCore.QTimer.singleShot(5000, self.scan)
        levels.real.filesystemDispatcher.connect(self.handleRealFileEvent)

    def disable(self):
        self.enabled = False
        if self.scanState != ScanState.notScanning:
            self.scanTimer.stop()
        self.hashThread.stop()
        levels.real.filesystemDispatcher.connect(self.handleRealFileEvent)

    def setPath(self, path):
        """Change the path of this source to *path*. Will recreate internal structures if changed.
        """
        self.path = path
        if path != self.path and self.enabled:
            self.disable()
            self.enable()

    def loadFolders(self):
        """Load the folders table from the database. Initializes *self.folders*.
        """
        for path, state in db.query("SELECT path, state FROM {p}folders WHERE path LIKE "
                       + "'{}%' ORDER BY LENGTH(path)".format(self.path.replace("'", "\\'"))):
            if path == self.path:
                folder = Folder(path=self.path, parent=None)
            else:
                parentName = os.path.split(path)[0]
                parent = self.folders[parentName]
                folder = Folder(path, parent)
            folder.state = FilesystemState(state)
            self.folders[folder.path] = folder

    def loadDBFiles(self):
        """Load files table. Adds all files in there to self.files."""
        ans = list(db.query("SELECT element_id, url, hash, verified FROM {p}files WHERE url LIKE "
                       + "'{}%'".format('file://' + self.path.replace("'", "\\'"))))
        for elid, urlstring, elhash, verified in ans:
            url = urls.URL(urlstring)
            self.addFile(url, id=elid, verified=db.getDate(verified), hash=elhash)

    def loadNewFiles(self):
        """Load the newfiles table and add the files to self.files.
        """
        newDirectories = []
        toDelete = []
        for urlstring, elhash, verified in db.query("SELECT url, hash, verified FROM {p}newfiles "
            + "WHERE url LIKE '{}%'".format('file://' + self.path.replace("'", "\\'"))):
            file = File(urls.URL(urlstring))
            if file.url.path in self.files:
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
        parentPath = None if path == '/' else os.path.split(path)[0]
        parent, new = self.getFolder(parentPath)
        dir = Folder(path, parent)
        self.folders[path] = dir
        if storeNew:
            self.storeFolders(new + [dir])
        return dir, new + [dir]

    def storeFolders(self, folders):
        """Insert the given list of :class:`Folder` objects into the folders table."""
        if len(folders):
            db.multiQuery("INSERT INTO {p}folders (path, state) VALUES(?,?)",
                          [(dir.path, dir.state.value) for dir in folders])

    def storeNewFiles(self, newfiles):
        """Inserts the given list of :class:`File` objects into the newfiles table."""
        if len(newfiles):
            db.multiQuery('INSERT INTO {p}newfiles (url, hash, verified) VALUES (?,?,?)',
                          [(str(file.url), file.hash,
                           file.verified.strftime("%Y-%m-%d %H:%M:%S")) for file in newfiles])

    def updateFolders(self, folders, emit=True):
        """Updates entries for given list of :class:`Folder` objects in the folders table. Emits
        :attr:folderStateChanged: unless *emit* is set to `False`.
        """
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
        logging.debug(__name__, 'source {} scanning path {}'.format(self.name, self.path))

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
                file, newdirs = self.addFile(urls.URL.fileURL(path), storeFolders=False, storeFile=False)
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
            logging.warning(__name__, '{} files in DB missing on filesystem'.format(len(self.missingDB)))
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
                logging.debug(__name__, 'track {} modified'.format(os.path.basename(path)))
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
            logging.debug(__name__, "detected {} files with modified tags".format(len(self.modifiedTags)))
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
        logging.debug(__name__, 'scan finished')

    def save(self):
        return {'name': self.name,
                'path': self.path,
                'domain': self.domain.id,
                'enabled': self.enabled}

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

    def moveFile(self, file: File, newUrl):
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

    def addFile(self, url, id=None, hash=None, verified=minVerified,
                storeFolders=True, storeFile=True) -> (File, list):
        """Adds a new file with the given parameters to the internal structure. New folders will be
        created if necessary, and stored in the database unless *storeFolders=False*. If
        *storeFile=True* and *id is None*, the file will be stored in the newfiles table.
        """
        dir, newdirs = self.getFolder(url.directory, storeNew=storeFolders)
        file = File(url, id=id, hash=hash, verified=verified)
        dir.add(file)
        self.files[url.path] = file
        if storeFile and id is None:
            self.storeNewFiles([file])
        return file, newdirs

    def handleRealFileEvent(self, event):
        """Handle an event issued by levels.real if something has affected the filesystem.

        Updates the internal directory tree structure, and recomputes hashes if necessary.
        """
        if self.scanState not in  (ScanState.notScanning, ScanState.realHashOnly):
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


def readFilesystem(path, files: dict):
    """Helper function that walks *path* and stores, for each found music file, an entry in *files*
    mapping its path to its modification timestamp.
    """
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            if utils.files.isMusicFile(filename):
                absFilename = os.path.join(dirpath, filename)
                stamp = utils.files.mTimeStamp(absFilename)
                files[absFilename] = stamp


def checkFiles(files: list, tagDiffs: dict, newHash: dict):
    """Compares database and filesystem state of *files*. If tags differ, adds an entry in
    *tagDiffs*. If the hash is different, adds an entry in *newHash*.
    """
    identifier = AcoustIDIdentifier()
    for file in files:
        hash = identifier(file.url.path)
        if file.id in levels.real:
            dbTags = levels.real.collect(file.id).tags
        else:
            dbTags = db.tags(file.id)
        backendFile = file.url.backendFile()
        backendFile.readTags()
        if dbTags.withoutPrivateTags() != backendFile.tags:
            logging.debug(__name__, 'Detected modification on file "{}": tags differ'.format(file.url))
            tagDiffs[file] = (hash, dbTags, backendFile.tags)
        else:
            if hash != file.hash:
                logging.debug(__name__, "audio data of {} modified!".format(file.url.path))
            newHash[file] = hash


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
        identifier = AcoustIDIdentifier()
        while True:
            prio, path = self.jobQueue.get()
            self.lastJobDone.clear()
            hash = identifier(path)
            self.resultQueue.put((path, hash))
            if self.jobQueue.empty():
                self.lastJobDone.set()


