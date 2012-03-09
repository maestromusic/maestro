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
from .. import logging, config, utils, database as db, realfiles, modify
import os.path, subprocess, hashlib, datetime, threading, queue, time
logger = logging.getLogger(__name__)
RESCAN_INTERVAL = 100 # seconds between rescans of the music directory

def init():
    global syncThread, notifier, null
    syncThread = FileSystemSynchronizer()
    null = open(os.devnull)    
    modify.dispatcher.changes.connect(syncThread.handleEvent, Qt.QueuedConnection)
    notifier = Notifier()
    syncThread.missingFilesDetected.connect(notifier.notifyAboutMissingFiles)
    syncThread.modifiedTagsDetected.connect(notifier.changeModifiedTags)
    syncThread.start()
    
def shutdown():
    """Terminates this module; waits for all threads to complete."""
    syncThread.should_stop.set()
    syncThread.exit()
    syncThread.wait()
    null.close()



def computeHash(path):
    """Compute the audio hash of a single file. This method uses
    the "ffmpeg" binary ot extract the first 15 seconds in raw
    PCM format and then creates the MD5 hash of that data. It would
    be nicer to have this either as a plugin with possibly alternative
    methods, or even better use something like
    https://github.com/sampsyo/audioread/tree/master/audioread
    that determines an available backend automatically."""
    try:
        logger.debug('computing hash for {}'.format(path))
        proc = subprocess.Popen(
            ['ffmpeg', '-i', utils.absPath(path),
             '-v', 'quiet',
             '-f', 's16le',
             '-t', '15',
             '-'],
            stdout=subprocess.PIPE, stderr=null # this is due to a bug that ffmpeg ignores -v quiet
        )
        data = proc.stdout.readall()
        proc.wait()
        hash = hashlib.md5(data).hexdigest()
        return hash
    except OSError:
        logger.error('need ffmpeg binary to compute hashes')

class Notifier(QtCore.QObject):
    
    @QtCore.pyqtSlot(list)
    def notifyAboutMissingFiles(self, paths):
        from . import dialogs
        dialogs.MissingFilesDialog(paths)
        syncThread.dialogFinished.set()
    
    @QtCore.pyqtSlot(object)
    def changeModifiedTags(self, changes):
        from .. import tags
        for id, (dbTags, fileTags) in changes.items():
            
            for tag, values in dbTags.items(): # preserve private tags
                if tag.private:
                    fileTags[tag] = values
            db.write.setTags(id, fileTags)
        QtGui.QMessageBox.information(None, self.tr('detected tag changes'),
                                      self.tr('The tags of the files with ids {} were '
                                              'changed from outside OMG. The database'
                                              'has now been updated accordingly.').format(list(changes.keys())))
            
        
def mTimeStamp(path):
    """Returns a datetime.datetime object representing the modification timestamp
    of the file given by the (relative) path *path*."""
    return datetime.datetime.fromtimestamp(os.path.getmtime(utils.absPath(path)))
     
                        
class FileSystemSynchronizer(QtCore.QThread):
    
    folderStateChanged = QtCore.pyqtSignal(str, str)
    missingFilesDetected = QtCore.pyqtSignal(list)
    modifiedTagsDetected = QtCore.pyqtSignal(object)
    
    def __init__(self):
        super().__init__(None)
        
        self.should_stop = threading.Event()
        self.dialogFinished = threading.Event()
        self.timer = QtCore.QTimer(self)
        self.moveToThread(self)
        self.timer.moveToThread(self)
        self.timer.timeout.connect(self.pollJobs)
        self.hashJobs = queue.Queue()
        self.lastScan = 0
    
    def compareTagsWithDB(self, id, path):
        dbTags = db.tags(id)
        rfile = realfiles.get(utils.absPath(path))
        rfile.read()
        if dbTags.withoutPrivateTags() != rfile.tags:
            logger.debug('Detected modification on file "{}": tags differ'.format(path))
            self.modifiedTags[id] = (dbTags, rfile.tags)
    
    def checkFilesTable(self):
        """go through the files table, add missing hashes and find modified files"""
        for id, path, hash, verified in \
                db.query("SELECT element_id,path,hash,verified FROM {}files".format(db.prefix)):
            if self.should_stop.is_set():
                return
            absPath = utils.absPath(path)
            if not os.path.exists(absPath):
                if db.isNull(hash):
                    self.lostFiles.append(id) # file without hash deleted -> no chance to find somewhere else
                else:
                    logger.info('file {} is missing'.format(path))
                    self.missingFiles[hash] = (path,id)
                continue
            self.dbFiles.append(path)
            if db.isNull(hash):
                hash = computeHash(path)
                logger.debug('Computed hash of {} as {}'.format(path, hash))
                db.setHash(id, hash)
            elif verified < mTimeStamp(path):
                self.compareTagsWithDB(id, path)
                newHash = computeHash(path)
                if newHash != hash:
                    logger.debug('Detected modification of audio data on "{}"'.format(path))
                    db.setHash(id, newHash)
                db.query('UPDATE {}files SET verified=CURRENT_TIMESTAMP() '
                         'WHERE element_id=?'.format(db.prefix),id)
    
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
        for root, dirs, files in os.walk(config.options.main.collection, topdown = False):
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
                        # -> recompute hash
                        if mTimeStamp(relPath) > knownStamp:
                            newHash = computeHash(relPath)
                            db.query('UPDATE {}newfiles SET hash=?, verified=CURRENT_TIMESTAMP() '
                                     'WHERE path = ?'.format(db.prefix), newHash, relPath)
                    else:
                        # case 2: file is completely new
                        logger.debug('hashing newfile {}'.format(relPath))
                        hash = computeHash(relPath)
                        if hash in self.missingFiles:
                            # found a file that was missing -> detected move!
                            if folderState == 'nomusic':
                                folderState = 'ok'
                            logger.info('detected a move: {} -> {}'.format(self.missingFiles[hash][0],
                                                                              relPath))
                            db.query('UPDATE {}files SET path=? WHERE element_id=?'.format(db.prefix),
                                     relPath,
                                     self.missingFiles[hash][1])
                            
                            # check if tags were also changed
                            self.compareTagsWithDB(self.missingFiles[hash][1], relPath)
                            del self.missingFiles[hash]
                            
                        else:
                            folderState = 'unsynced'
                            db.query('INSERT INTO {}newfiles SET hash=?, path=?'.format(db.prefix),
                                     hash, relPath)
                elif folderState == 'nomusic':
                    folderState = 'ok'
            if folderState != 'unsynced':
                folderState = self.updateStateFromSubfolders(root, folderState, dirs)
                
            relRoot = utils.relPath(root)
            # now update folders table and emit events for FileSystemBrowser
            if relRoot not in self.knownFolders or folderState != self.knownFolders[relRoot]:
                self.updateFolderState(relRoot, folderState)        
    
    def updateFolderState(self, path, state, recurse = False):
        if path not in self.knownFolders:
            db.addFolder(path, state)
        else:
            db.updateFolder(path, state)
        self.folderStateChanged.emit(path, state)
        self.knownFolders[path] = state
        if recurse and path not in ('', '.'):
            path = os.path.dirname(path)
            if path == '':
                path = '.'
            state = self.knownFolders[path]
            newState = self.updateStateFromSubfolders(utils.absPath(path), 'nomusic', files = True)
            if newState != state:
                self.updateFolderState(path, newState, True)
            
        
    def updateStateFromSubfolders(self, root, folderState, dirs = None, files = False):
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
            if self.knownFolders[path] == 'unsynced':
                return 'unsynced'
            elif self.knownFolders[path] == 'ok' and folderState == 'nomusic':
                folderState = 'ok'
        return folderState
    
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
       
        if len(self.modifiedTags) > 0:
            self.modifiedTagsDetected.emit(self.modifiedTags)
        
        if len(self.lostFiles) + len(self.missingFiles) > 0:
            missingIDs = self.lostFiles[:]
            if len(self.missingFiles) > 0:
                missingIDs.extend(list(zip(*self.missingFiles.values()))[1])
            self.dialogFinished.clear()
            self.missingFilesDetected.emit(missingIDs)
            self.dialogFinished.wait()
            
        logger.debug('rescanned collection')    
        
    @QtCore.pyqtSlot(list)
    def handleEvent(self, event):
        if isinstance(event, modify.events.FilesAddedEvent):
            # files added to DB -> check if folders have changed
            paths = event.paths
            for path in paths:
                self.hashJobs.put(path)
            filesByFolder = utils.groupFilePaths(paths)
            for folder, files in filesByFolder.items():
                dirContent = os.listdir(utils.absPath(folder))
                folderStillUnsynced = False
                for elem in dirContent:
                    relElemPath = os.path.join(folder, elem)
                    if elem in files:
                        files.remove(elem)
                    elif os.path.isdir(utils.absPath(relElemPath)):
                        if relElemPath in self.knownFolders \
                                and self.knownFolders[relElemPath] == 'unsynced':
                            folderStillUnsynced = True
                            break
                        continue
                    elif not utils.hasKnownExtension(elem):
                        continue
                    elif elem not in self.dbFiles:
                        folderStillUnsynced = True
                        break
                if not folderStillUnsynced:
                    logger.debug('previously unsynced folder now ok: {}'.format(folder))
                    self.updateFolderState(folder, 'ok', True)
                
        elif isinstance(event, modify.events.FilesRemovedEvent):
            byFolder = utils.groupFilePaths(event.paths)
            for folder, files in byFolder.items():
                if event.disk:
                    stillMusicThere = False
                    for thing in os.listdir(utils.absPath(folder)):
                        if os.path.isfile(utils.absPath(os.path.join(folder, thing))):
                            if utils.hasKnownExtension(thing):
                                stillMusicThere = True
                                break
                    if not stillMusicThere:
                        self.updateFolderState(folder, 'nomusic', True)
                        
                else:
                    self.updateFolderState(folder, 'unsynced', True)
    
    def computeAndStoreHash(self, path):
        """Compute the hash of the file at *path* (or fetch it from self.knownNewFiles
        if available) and set it in the database."""
        if path in self.knownNewFiles:
            hash = self.knownNewFiles[path]
            del self.knownNewFiles[path]
        else:
            print('no hash found for {}'.format(path))
            hash = computeHash(path)
        db.setHash(path, hash)
        self.dbFiles.append(path)
        db.query('DELETE FROM {}newfiles WHERE path = ?'.format(db.prefix), path)
        
    def pollJobs(self):
        try:
            while True:
                self.computeAndStoreHash(self.hashJobs.get_nowait())
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
