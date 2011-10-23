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
import queue, threading
from .. import logging, database as db, config, constants
from ..database.sql import EmptyResultException
from ..utils import relPath, hasKnownExtension
from ..modify import events
import os.path
logger = logging.getLogger("omg.sync")

def init():
    global fsct
    fsct = FileSystemCheckThread()
    fsct.daemon = True
    fsct.start()
    
def shutdown():
    """Terminates this module; waits for all threads to complete."""
#    hashQueue.join() # wait until all tasks in the commit queue are done
    #fsct.join()


class FileSystemCheckThread(threading.Thread):
    
    def __init__(self):
        threading.Thread.__init__(self)
        self.queue = queue.PriorityQueue()
        self.queue.put((1000, config.options.main.collection))
        
    def run(self):
        db.connect()
        while True:
            prio, path = self.queue.get()
            status = 'nomusic'
            music = False
            dirty = False
            files = os.listdir(path)
            for file in files:
                file = os.path.join(path, file)
                if os.path.isfile(file):
                    if hasKnownExtension(file):
                        music = True
                        if not dirty and not db.idFromPath(relPath(file)):
                            status = 'unsynced'
                            dirty = True
                    if music and not dirty:
                        status = 'ok'
                else:
                    self.queue.put((prio-1, os.path.join(path, file)))
            logger.debug('now {}: {}'.format(status, relPath(path)))
            db.query("UPDATE {0}folders SET state = ? WHERE path = ?".format(db.prefix), status, relPath(path))