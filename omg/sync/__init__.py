# -*- coding: utf-8 -*-
# Copyright 2011 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
"""The sync module is responsible for the synchronization of the database with the file system."""
import queue, threading
from .. import logging
from .. import database as db
from ..database.sql import EmptyResultException
from .. import config
from ..utils import relPath, hasKnownExtension
import os.path
logger = logging.getLogger("omg.sync")



hashQueue = queue.Queue()
def hasher():
    """Run function for the commit thread."""
    while True:
        fun, args, kwargs = hashQueue.get()
        fun(*args, **kwargs)
        hashQueue.task_done()
        logger.debug("task done")
        
hashThread = threading.Thread(target = hasher)
hashThread.daemon = True
hashThread.start()

def init():
    global fsct
    fsct = FileSystemCheckThread()
    fsct.daemon = True
    fsct.start()
def shutdown():
    """Terminates this module; waits for all threads to complete."""
    hashQueue.join() # wait until all tasks in the commit queue are done
    #fsct.join()
    

class FileSystemCheckThread(threading.Thread):
    
    def __init__(self):
        threading.Thread.__init__(self)
        
    def run(self):
        db.connect()
        for root, dirs, files in os.walk(config.options.main.collection, topdown = True):
            relRoot = relPath(root)
            num = db.query("SELECT count(*) FROM {}folders WHERE path=?".format(db.prefix), relRoot).getSingle()
            if num != 0:
                status = db.query("SELECT state FROM {0}folders WHERE path = ?".format(db.prefix), relRoot).getSingle()
            else:
                db.query("INSERT INTO {0}folders (path) VALUES(?)".format(db.prefix), relRoot)
                logger.info("Previously unseen folder: {}".format(root))
                status = 'unknown'
            if status == 'unknown':
                music = False
                dirty = False
                for f in files:
                    f = os.path.join(root, f)
                    if os.path.isfile(f) and hasKnownExtension(f):
                        if not db.idFromPath(relPath(f)):
                            status = 'unsynced'
                            dirty = True
                            break
                        music = True
                if music and not dirty:
                    status = 'ok'
                else:
                    status = 'nomusic'
                logger.info("Folder {} has status {}".format(relRoot, status))
                db.query("UPDATE {0}folders SET state = ? WHERE path = ?".format(db.prefix), status, relRoot)