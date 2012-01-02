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
import pyinotify as pyi
import os.path, subprocess, hashlib, datetime, threading
logger = logging.getLogger(__name__)


def init():
    global syncThread
    syncThread = FileSystemSynchronizer()
    syncThread.start()
    
def shutdown():
    """Terminates this module; waits for all threads to complete."""
    syncThread.should_stop.set()
    syncThread.exit()
    syncThread.wait()

def computeHash(path):
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

def mTimeStamp(path):
    """Returns a datetime.datetime object representing the modification timestamp
    of the file given by the (relative) path *path*."""
    return datetime.datetime.fromtimestamp(os.path.getmtime(utils.absPath(path)))
     
class InotifyEventHandler(pyi.ProcessEvent):
    
    def __init__(self, synchronizer):
        super().__init__()
        self.synchronizer = synchronizer
        self.wm = synchronizer.wm
        self.wdd = synchronizer.wdd
        
    def process_IN_CREATE(self, event):
        print('file created: {}'.format(event.pathname))
        
    def process_IN_DELETE(self, event):
        print('file deleted: {}'.format(event.pathname))
        
    def process_IN_MOVED_TO(self, event):
        if hasattr(event, 'src_pathname'):
            print('file moved: from {} to {}'.format(event.src_pathname, event.pathname))
        else:
            print('file moved into: {}'.format(event.pathname))
            
    def process_IN_MOVED_FROM(self, event):
        print('file moved away: {}'.format(event.pathname))
        if event.pathname in self.wdd:
            #wm.update_watch(wdd[event.pathname], rec=True)
            print('removing')
            try:
                self.wm.rm_watch(self.wdd[event.pathname], rec=True, quiet = False)
            except pyi.WatchManagerError as e:
                print('error exc')
                print(e)
            except:
                print('wtf')
            print('removed')


                        
class FileSystemSynchronizer(QtCore.QThread):
    
    mask = pyi.IN_DELETE | pyi.IN_MOVED_TO | pyi.IN_CREATE | pyi.IN_MOVED_FROM
    
    def __init__(self):
        super().__init__(None)
        
        self.should_stop = threading.Event()
        self.timer = QtCore.QTimer(self)
        self.moveToThread(self)
        self.timer.moveToThread(self)
        self.timer.timeout.connect(self.checkEvents)
        self.missingFiles = {} # maps hash to missing files (i.e. files moved away or deleted)
        self.lostFiles = [] # list of files without hash that are gone
        self.modifiedTags = {}
        self.knownFiles = []
        
    
    def checkMissingHashes(self):
        """Checks the audio hashes in the files table.
        - If a hash is missing, it is recomputed.
        - If a hash is outdated, tags are checked and the user is notified.
        """
        db.connect()
        for id, path, hash, verified in \
                db.query("SELECT element_id,path,hash,verified FROM {}files".format(db.prefix)):
            if self.should_stop.is_set():
                db.close()
                return
            absPath = utils.absPath(path)
            if not os.path.exists(absPath):
                if db.isNull(hash):
                    self.lostFiles.append(path)
                else:
                    logger.info('file {} is missing'.format(path))
                    self.missingFiles[hash] = path
                continue
            self.knownFiles.append(path)
            if db.isNull(hash):
                hash = computeHash(path)
                logger.debug('Computed hash of {} as {}'.format(path, hash))
                db.setHash(id, hash)
            elif verified < mTimeStamp(path):
                dbTags = db.tags(id)
                rfile = realfiles.get(absPath)
                rfile.read()
                if dbTags != rfile.tags:
                    print('tags modified!')
                    self.modifiedTags[path] = (dbTags, rfile.tags)
                newHash = computeHash(path)
                if newHash != hash:
                    print('audio data modified!')
                    db.setHash(id, newHash)
        
        knownNewFiles = {}
        goneNewFiles = []
        for path, hash, timestamp in \
                db.query('SELECT path, hash, verified FROM {}newfiles'.format(db.prefix)):
            if os.path.exists(utils.absPath(path)):
                knownNewFiles[path] = (hash, timestamp)
            else:
                goneNewFiles.append((path,))
        if len(goneNewFiles) > 0:
            db.multiQuery('DELETE FROM {}newfiles WHERE PATH=?'.format(db.prefix), goneNewFiles)
                
        
        for root, dirs, files in os.walk(config.options.main.collection):
            for file in files:
                if self.should_stop.is_set():
                    db.close()
                    return
                absPath = os.path.join(root, file)
                relPath = utils.relPath(absPath)
                if utils.hasKnownExtension(file) and relPath not in self.knownFiles:
                    if relPath in knownNewFiles:
                        knownHash, knownStamp = knownNewFiles[relPath]
                        if mTimeStamp(relPath) > knownStamp:
                            newHash = computeHash(relPath)
                            if newHash != knownHash:
                                logger.debug('updating hash of not-in-db file {}'.format(relPath))
                                db.query('UPDATE {}newfiles SET hash=? WHERE path = ?'.format(db.prefix),
                                         newHash, relPath)
                    else:
                        logger.debug('computing hash of not-in-db file {}'.format(relPath))
                        hash = computeHash(relPath)
                        if hash in self.missingFiles:
                            logger.info('whoa, found a move: {} -> {}'.format(self.missingFiles[hash],
                                                                              relPath))
                        else:
                            db.query('INSERT INTO {}newfiles SET hash=?, path=?'.format(db.prefix),
                                     hash, relPath)
        
        db.close()
        

            
    def run(self):
        self.checkMissingHashes()
        if self.should_stop.is_set():
            return
        self.timer.start(500)
        self.wm = pyi.WatchManager()
        self.wdd = self.wm.add_watch(config.options.main.collection,
                                     self.mask,
                                     rec = True,
                                     auto_add = True)
        self.handler = InotifyEventHandler(self)        
        self.notifier = pyi.Notifier(self.wm, self.handler, timeout = 10)
        logger.info('installing notifier on music directory...')
        
        logger.info('notifier installed.')
        self.exec_()
        
    def checkEvents(self):
        self.notifier.process_events()
        while self.notifier.check_events():
            self.notifier.read_events()
            self.notifier.process_events()