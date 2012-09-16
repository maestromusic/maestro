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
EPSILON_TIME = datetime.timedelta(seconds=3)

def init():
    global synchronizer, notifier, null, enabled
    import _strptime
    if config.options.filesystem.disable:
        return
    synchronizer = FileSystemSynchronizer()
    synchronizer.eventThread.start()
    levels.real.filesRenamed.connect(synchronizer.handleRename)
    levels.real.filesAdded.connect(synchronizer.handleAdd)
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
    synchronizer.should_stop.set()
    synchronizer.eventThread.exit()
    synchronizer.eventThread.wait()
    synchronizer = None
    null.close()
    logger.debug("Filesystem module: shutdown complete")

def getFolderState(path):
    """Return the state of a given folder, or 'unknown' if it can't be obtained.
    """
    if not enabled or not synchronizer.initialized.is_set():
        return 'unknown'
    try:
        return synchronizer.knownFolders[path]
    except KeyError:
        return None

def getNewfileHash(url):
    """Return the hash of a file specified by *url* which is not yet in the database.
    
    If the hash is not known, returns None.
    """
    if not enabled or not synchronizer.initialized.is_set():
        return None
    try:
        return synchronizer.knownNewFiles[url].hash
    except KeyError:
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
    """Returns a datetime.datetime object representing the modification timestamp
    of the file given by *url*."""
    return datetime.datetime.fromtimestamp(os.path.getmtime(url.absPath), tz=datetime.timezone.utc)

class SynchronizeHelper(QtCore.QObject):
    """Class running in the main event thread to change database and display GUIs."""
    
    @QtCore.pyqtSlot(object)
    def addFileHashes(self, newHashes):
        db.multiQuery("UPDATE {}files SET hash=? WHERE element_id=?"
                      .format(db.prefix), [ (hash, id) for id, hash in newHashes ]) 

    @QtCore.pyqtSlot(int, object)
    def changeURL(self, id, newUrl):
        db.query('UPDATE {}files SET url=? WHERE element_id=?'.format(db.prefix), str(newUrl), id)
        if id in levels.real.elements:
            levels.real.get(id).url = newUrl
            levels.real.emitEvent([id])
        
class EventThread(QtCore.QThread):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.timer = QtCore.QTimer(self)
        
    def run(self):
        self.timer.start(config.options.filesystem.scan_interval)
        self.exec_()
        db.close()
        print('db clossed')               

class FileInformation:
    
    def __init__(self, url, hash, verified, id=None):
        self.url = url
        self.hash = hash
        self.verified = verified
        self.id = id

class FileSystemSynchronizer(QtCore.QObject):
    
    folderStateChanged = QtCore.pyqtSignal(str, str)
    initializationComplete = QtCore.pyqtSignal()
    
    hashesComputed = QtCore.pyqtSignal(object)
    moveDetected = QtCore.pyqtSignal(int, object)
    
    def __init__(self):
        super().__init__()
        self.should_stop = threading.Event()
        self.initialized = threading.Event()
        
        self.helper = SynchronizeHelper()
        self.eventThread = EventThread(self)
        self.moveToThread(self.eventThread)
        self.eventThread.started.connect(self.init)
        self.hashesComputed.connect(self.helper.addFileHashes)
        self.moveDetected.connect(self.helper.changeURL)
        self.dbFiles = {}
        self.lostFiles = set()
        self.missingFiles = {}
        self.modifiedTags = {}
        self.knownNewFiles = {}
        self.knownFolders = {}
    
    def init(self):
        db.connect()
        #  initialize self.dbFiles
        newHashes = []
        for id, url, hash, verified \
                in db.query("SELECT element_id,url,hash,verified FROM {}files".format(db.prefix)):
            url = filebackends.BackendURL.fromString(url)
            if isinstance(url, filebackends.filesystem.BackendURL):
                self.dbFiles[url] = FileInformation(url=url, verified=db.getDate(verified),
                                                    hash=hash, id=id)
            if db.isNull(hash):
                newHashes.append((id, computeHash(url)))
        if len(newHashes) > 0:
            self.hashesComputed.emit(newHashes)
        
        #  initialize self.knownNewFiles 
        for url, hash, timestamp in \
                db.query('SELECT url, hash, verified FROM {}newfiles'.format(db.prefix)):
            url = filebackends.BackendURL.fromString(url)
            timestamp = db.getDate(timestamp)
            self.knownNewFiles[url] = FileInformation(url=url, hash=hash, verified=timestamp)
        
        #  initialize self.knownFolders
        for folder, state in db.query('SELECT path,state FROM {}folders'.format(db.prefix)):
            self.knownFolders[folder] = state
        self.initializationComplete.emit()
        self.initialized.set()
        self.rescanCollection()
        
    def compareTagsWithDB(self, id, url):
        """Checks if the tags inside the file at *path* with id *id* equals those stored in the
        database. Otherwise, *self.modifiedTags[id]* will be set to a tuple (dbTags, fileTags)."""
        if id in levels.real:
            dbTags = levels.real.get(id).tags
        else:
            dbTags = db.tags(id)
        backendFile = url.getBackendFile()
        backendFile.readTags()
        if dbTags.withoutPrivateTags() != backendFile.tags:
            logger.debug('Detected modification on file "{}": tags differ'.format(url.path))
            self.modifiedTags[id] = (dbTags, backendFile.tags)
            return False
    
    def checkDBFiles(self):
        """Find modified and lost DB files."""
        for url, info in self.dbFiles.items():
            if not os.path.exists(url.absPath):
                if db.isNull(info.hash) or info.hash in ["0", ""]:
                    # file without hash deleted -> no chance to find somewhere else
                    self.lostFiles.add(info.id)
                else:
                    self.missingFiles[info.hash] = info
                    print('missing {}'.format(info.hash))
                continue
            elif info.verified + EPSILON_TIME < mTimeStamp(url):
                if not self.compareTagsWithDB(info.id, url):
                    newHash = computeHash(url)
                    if newHash != info.hash:
                        logger.debug('Detected modification of audio data on "{}: {}->{}"'.format(url, info.hash, newHash))
                        db.query('UPDATE {}files SET hash=? WHERE element_id=?'.format(db.prefix),
                                 newHash, info.id)
                    else:
                        logger.debug("update timestamp")
                        db.query('UPDATE {}files SET verified=CURRENT_TIMESTAMP '
                                 'WHERE element_id=?'.format(db.prefix), info.id)
    
    def checkNewFiles(self):
        """Go through the newfiles table and remove entries of files which are deleted on disk."""
        gone = []
        for url in self.knownNewFiles:
            if not os.path.exists(url.absPath):
                gone.append((str(url),))
        if len(gone) > 0:
            db.multiQuery('DELETE FROM {}newfiles WHERE url=?'.format(db.prefix), gone)
    
    def checkFolders(self):
        """Go through the folders table, remove entries of folders which were deleted on disk."""
        gone = []
        for folder in self.knownFolders:
            if not os.path.exists(utils.absPath(folder)):
                gone.append((folder,))
        if len(gone) > 0:
            db.multiQuery('DELETE FROM {}folders WHERE path=?'.format(db.prefix), gone)
        
    def checkFileSystem(self):
        """Walks through the collection, updating folders and searching for new files.
        
        This method has three purposes:
        - update the states of folders (unsynced, ok, nomusic) used for display in filesystembrowser,
        - compute hashes of files which are not yet in the database
        - doing the latter, moved files can be detected
        """
        for root, dirs, files in os.walk(config.options.main.collection, topdown=False):
            folderState = None
            for file in files:
                if self.should_stop.is_set():
                    return
                url = filebackends.filesystem.FileURL(os.path.join(root, file))
                if not utils.hasKnownExtension(url.path):
                    continue # skip non-music files
                if url not in self.dbFiles:
                    if url in self.knownNewFiles:
                        # case 1: file was found in a previous scan
                        folderState = 'unsynced'
                        info = self.knownNewFiles[url]
                        # check if the file's modification time is newer than the DB timestamp
                        # -> recompute hash
                        if mTimeStamp(url) > info.verified:
                            newHash = computeHash(url)
                            db.query('UPDATE {}newfiles SET hash=?, verified=CURRENT_TIMESTAMP '
                                     'WHERE url=?'.format(db.prefix), newHash, str(url))
                            info.hash = newHash
                    else:
                        # case 2: file is completely new
                        logger.debug('hashing newfile {}'.format(url))
                        hash = computeHash(url)
                        if hash in self.missingFiles:
                            # found a file that was missing -> detected move!
                            info = self.missingFiles[hash]
                            if folderState is None:
                                folderState = 'ok'
                            logger.info('detected a move: {} -> {}'.format(info.url, url))
                            self.moveDetected.emit(info.id, url)
                            info.url = url
                            # check if tags were also changed
                            self.compareTagsWithDB(info.id, url)
                            del self.missingFiles[hash]
                        else:
                            folderState = 'unsynced'
                            db.query('INSERT INTO {}newfiles (hash,url) VALUES (?,?)'.format(db.prefix),
                                     hash, str(url))
                            self.knownNewFiles[url] = FileInformation(url, hash, datetime.datetime.now(datetime.timezone.utc))
                elif folderState is None:
                    folderState = 'ok'
            if folderState != 'unsynced':
                folderState = self.updateStateFromSubfolders(root, folderState, dirs)
            relRoot = utils.relPath(root)
            # now update folders table and emit events for FileSystemBrowser
            if (folderState is None and relRoot in self.knownFolders) or \
                    (relRoot not in self.knownFolders) or \
                    (folderState != self.knownFolders[relRoot]):
                self.updateFolderState(relRoot, folderState)        
    
    def updateFolderState(self, path, state, recurse=False):
        if state is None:
            db.query("DELETE FROM {}folders WHERE path=?".format(db.prefix), path)
        elif path not in self.knownFolders:
            db.query("INSERT INTO {}folders (path, state) VALUES (?,?)".format(db.prefix), path, state)
        else:
            db.query("UPDATE {}folders SET state=? WHERE path=?".format(db.prefix), state, path)
        self.folderStateChanged.emit(path, state)
        self.knownFolders[path] = state
        if recurse and path not in ('', '.'):
            path = os.path.dirname(path)
            if path == '':
                path = '.'
            state = self.knownFolders[path]
            newState = self.updateStateFromSubfolders(utils.absPath(path), None, files=True)
            if newState != state:
                self.updateFolderState(path, newState, True)
            
        
    def updateStateFromSubfolders(self, root, folderState, dirs=None, files=False):
        """Returns the updated folderState of abspath *root* when the states
        of the subdirectories are considered. E.g. if root is 'ok' and a subdir
        is 'unsynced', return 'unsynced'. The optional *dirs* parameter is
        a list of given subdirectories; if not specified, they are computed first."""
        if dirs == None:
            dirs = []
            for elem in os.listdir(root):
                if os.path.isdir(os.path.join(root, elem)):
                    # tuning: stop directory testing as soon as an unsynced dir is found
                    if self.knownFolders[utils.relPath(os.path.join(root, elem))] == 'unsynced':
                        return 'unsynced'
                    dirs.append(elem)
                elif files and utils.hasKnownExtension(elem):
                    if utils.relPath(os.path.join(root, elem)) not in self.dbFiles:
                        return 'unsynced'
                    else:
                        folderState = 'ok'
        for dir in dirs:
            path = utils.relPath(os.path.join(root, dir))
            if path not in self.knownFolders:
                continue
            elif self.knownFolders[path] == 'unsynced':
                return 'unsynced'
            elif self.knownFolders[path] == 'ok' and folderState is None:
                folderState = 'ok'
        return folderState
    
    @QtCore.pyqtSlot()
    def rescanCollection(self):
        """Checks the audio hashes in the files table.
        - If a hash is missing, it is recomputed.
        - If a hash is outdated, tags are checked and the user is notified.
        """
        self.checkDBFiles()
        self.checkNewFiles()
        self.checkFolders()
        self.checkFileSystem()
        if self.should_stop.is_set():
            return
        if len(self.modifiedTags) > 0:
            #self.modifiedTagsDetected.emit(self.modifiedTags)
            # TODO: implement
            logger.warning("needs implementation")
        
        if len(self.lostFiles) + len(self.missingFiles) > 0:
            missingIDs = list(self.lostFiles)
            if len(self.missingFiles) > 0:
                missingIDs.extend(info.id for info in self.missingFiles.values())
            print('missing ids: {}'.format(missingIDs))
            #self.dialogFinished.clear()
            #self.missingFilesDetected.emit(missingIDs)
            #self.dialogFinished.wait()
            
        logger.debug('rescanned collection')
    
    @QtCore.pyqtSlot(object)
    def handleRename(self, renamings):
        for id, (oldUrl, newUrl) in renamings.items():
            if oldUrl.scheme != "file":
                continue
            print('rename in filesystem module!! omg')
            
    @QtCore.pyqtSlot(list)
    def handleAdd(self, newFiles):
        needHash = []
        for file in newFiles:
            if file.url not in self.knownNewFiles or db.isNull(self.knownNewFiles[file.url].hash):
                needHash.append(file)
        newHashes = [ (file.id, computeHash(file.url)) for file in needHash ]
        if len(newHashes) > 0:
            self.hashesComputed.emit(newHashes)
            
    
