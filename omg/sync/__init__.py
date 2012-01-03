# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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

"""The sync module is responsible for the synchronization of the database with the file system."""

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt
from .. import logging, config, utils, database as db, realfiles
import os.path, subprocess, hashlib, datetime, threading, queue, time
logger = logging.getLogger(__name__)
RESCAN_INTERVAL = 100 # seconds between rescans of the music directory

def init():
    global syncThread, notifier
    syncThread = FileSystemSynchronizer()
    syncThread.start()
    notifier = Notifier()
    notifier.newFileElementsCreated.connect(syncThread.handleFileElementCreation, Qt.QueuedConnection)
    
def shutdown():
    """Terminates this module; waits for all threads to complete."""
    syncThread.should_stop.set()
    syncThread.exit()
    syncThread.wait()

def computeHash(path):
    """Compute the audio hash of a single file. This method uses
    the "ffmpeg" binary ot extract the first 15 seconds in raw
    PCM format and then creates the MD5 hash of that data. It would
    be nicer to have this either as a plugin with possibly alternative
    methods, or even better use something like
    https://github.com/sampsyo/audioread/tree/master/audioread
    that determines an available backend automatically."""
    try:
        proc = subprocess.Popen(
            ['ffmpeg', '-i', utils.absPath(path),
             '-v', 'quiet',
             '-f', 's16le',
             '-t', '15',
             '-'],
            stdout=subprocess.PIPE, stderr=None
        )
        data = proc.stdout.readall()
        hash = hashlib.md5(data).hexdigest()
        return hash
    except OSError:
        logger.error('need ffmpeg binary to compute hashes')

class Notifier(QtCore.QObject):
    
    
    def requestHashComputation(self, elements):
        """Asynchronously starts to compute hashes for the given elements
        (a list of (id, path) tuples) and fills them into the files table."""
        for tup in elements:
            syncThread.hashJobs.put(tup)

    newFileElementsCreated = QtCore.pyqtSignal(list)
    
def mTimeStamp(path):
    """Returns a datetime.datetime object representing the modification timestamp
    of the file given by the (relative) path *path*."""
    return datetime.datetime.fromtimestamp(os.path.getmtime(utils.absPath(path)))
     
                        
class FileSystemSynchronizer(QtCore.QThread):
    
    folderStateChanged = QtCore.pyqtSignal(str, str)
    def __init__(self):
        super().__init__(None)
        
        self.should_stop = threading.Event()
        self.timer = QtCore.QTimer(self)
        self.moveToThread(self)
        self.timer.moveToThread(self)
        self.timer.timeout.connect(self.pollJobs)
        self.hashJobs = queue.Queue()
        self.lastScan = 0
        
    
    def checkFilesTable(self):
        """go through the files table, add missing hashes and find modified files"""
        for id, path, hash, verified in \
                db.query("SELECT element_id,path,hash,verified FROM {}files".format(db.prefix)):
            if self.should_stop.is_set():
                return
            absPath = utils.absPath(path)
            if not os.path.exists(absPath):
                if db.isNull(hash):
                    self.lostFiles.append(path) # file without hash deleted -> no chance to find somewhere else
                else:
                    logger.info('file {} is missing'.format(path))
                    self.missingFiles[hash] = path
                continue
            self.dbFiles.append(path)
            if db.isNull(hash):
                hash = computeHash(path)
                logger.debug('Computed hash of {} as {}'.format(path, hash))
                db.setHash(id, hash)
            elif verified < mTimeStamp(path):
                dbTags = db.tags(id)
                rfile = realfiles.get(absPath)
                rfile.read()
                if dbTags != rfile.tags:
                    logger.debug('Detected modification on file "{}": tags differ'.format(path))
                    self.modifiedTags[path] = (dbTags, rfile.tags)
                newHash = computeHash(path)
                if newHash != hash:
                    logger.debug('Detected modification of audio data on "{}"'.format(path))
                    db.setHash(id, newHash)
    
    def checkNewFiles(self):
        """Go through the newfiles table and remove entries of files which are deleted on disk."""
        goneNewFiles = []
        for path, hash, timestamp in \
                db.query('SELECT path, hash, verified FROM {}newfiles'.format(db.prefix)):
            if os.path.exists(utils.absPath(path)):
                self.knownNewFiles[path] = (hash, timestamp)
            else:
                goneNewFiles.append((path,))
        if len(goneNewFiles) > 0:
            db.multiQuery('DELETE FROM {}newfiles WHERE PATH=?'.format(db.prefix), goneNewFiles)
    
    def checkFolders(self):
        """Go through the folders table, remove entries of folders which were deleted on disk."""
        goneFolders = []
        
        for folder, state in db.query('SELECT path,state FROM {}folders'.format(db.prefix)):
            if os.path.exists(utils.absPath(folder)):
                self.knownFolders[folder] = state
            else:
                goneFolders.append((folder,))
        if len(goneFolders) > 0:
            db.multiQuery('DELETE FROM {}folders WHERE path=?'.format(db.prefix), goneFolders)
    
    def checkFileSystem(self):
        """Walks through the collection, updating folders and searching for new files.
        
        This method has three purposes:
        - update the states of folders (unsynced, ok, nomusic) used for display in filesystembrowser,
        - compute hashes of files which are not yet in the database
        - doing the latter, moved files can be detected
        """
        for root, dirs, files in os.walk(config.options.main.collection):
            folderState = 'nomusic'
            for file in files:
                if self.should_stop.is_set():
                    return
                absPath = os.path.join(root, file)
                relPath = utils.relPath(absPath)
                if not utils.hasKnownExtension(file):
                    continue # skip non-music files
                if relPath not in self.dbFiles:
                    if relPath in self.knownNewFiles:
                        # case 1: file was found in a previous scan
                        folderState = 'unsynced'
                        knownHash, knownStamp = self.knownNewFiles[relPath]
                        # check if the file's modification time is newer than the DB timestamp
                        if mTimeStamp(relPath) > knownStamp:
                            newHash = computeHash(relPath)
                            if newHash != knownHash:
                                logger.debug('updating hash of not-in-db file {}'.format(relPath))
                                db.query('UPDATE {}newfiles SET hash=? WHERE path = ?'.format(db.prefix),
                                         newHash, relPath)
                    else:
                        # case 2: file is completely new
                        logger.debug('computing hash of not-in-db file {}'.format(relPath))
                        hash = computeHash(relPath)
                        if hash in self.missingFiles:
                            # found a file that was missing -> detected move!
                            if folderState == 'nomusic':
                                folderState = 'ok'
                            logger.info('whoa, found a move: {} -> {}'.format(self.missingFiles[hash],
                                                                              relPath))
                            db.query('UPDATE {}files SET path=? WHERE path=?'.format(db.prefix),
                                     relPath,
                                     self.missingFiles[hash])
                            del self.missingFiles[hash]
                        else:
                            folderState = 'unsynced'
                            db.query('INSERT INTO {}newfiles SET hash=?, path=?'.format(db.prefix),
                                     hash, relPath)
                elif folderState == 'nomusic':
                    folderState = 'ok'
            relRoot = utils.relPath(root)
            # now update folder folders table and emit events for FileSystemBrowser
            if relRoot not in self.knownFolders:
                logger.debug('added "{}" {} to folders table'.format(folderState, relRoot))
                db.addFolder(relRoot, folderState)
                self.folderStateChanged.emit(relRoot, folderState)
            elif folderState != self.knownFolders[relRoot]:
                logger.debug('updated state of {} to {}'.format(relRoot, folderState))
                db.updateFolder(relRoot, folderState)
                self.folderStateChanged.emit(relRoot, folderState)        
    
    def rescanCollection(self):
        """Checks the audio hashes in the files table.
        - If a hash is missing, it is recomputed.
        - If a hash is outdated, tags are checked and the user is notified.
        """
        self.missingFiles = {} # maps hash to missing files (i.e. files moved away or deleted)
        self.lostFiles = [] # list of files without hash that are gone
        self.modifiedTags = {}
        self.dbFiles = []
        self.knownNewFiles = {}
        self.knownFolders = {}
        
        self.checkFilesTable()
        self.checkNewFiles()
        self.checkFolders()
        self.checkFileSystem()
       
        #if len(self.lostFiles) + len(self.missingFiles) > 0:
            
        
    @QtCore.pyqtSlot(list)
    def handleFileElementCreation(self, paths):
        filesByFolder = {}
        for path in paths:
            dir, filename = os.path.split(path)
            if dir not in filesByFolder:
                filesByFolder[dir] = []
            filesByFolder[dir].append(filename)
        for folder, files in filesByFolder.items():
            filesInDir = set(map(utils.relPath, filter(utils.hasKnownExtension, filter(os.path.isfile,
                map(lambda f: os.path.join(folder, f), os.listdir(utils.absPath(folder)))))))
            files = set(files)
            print(filesInDir)
            print(files)
            if files == filesInDir:
                db.updateFolder(folder, 'ok')
                self.folderStateChanged.emit(folder, 'ok')
            elif all( (file in self.dbFiles) for file in (filesInDir - files) ):
                db.updateFolder(folder, 'ok')
                self.folderStateChanged.emit(folder, 'ok')
            
    
    def pollJobs(self):
        try:
            while True:
                id, path = self.hashJobs.get_nowait()
                hash = computeHash(path)
        except queue.Empty:
            pass
        if time.time() - self.lastScan > RESCAN_INTERVAL:
            self.rescanCollection()
            self.lastScan = time.time()
           
    def run(self):
        db.connect()
        self.timer.start(100)
        self.exec_()
        db.close()
