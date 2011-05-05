# -*- coding: utf-8 -*-
# Copyright 2011 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
"""The sync module is responsible for the synchronization of the database with the file system."""
import queue, threading
import logging

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

def shutdown():
    """Terminates this module; waits for all threads to complete."""
    hashQueue.join() # wait until all tasks in the commit queue are done
    

class FileSystemCheckThread(threading.Thread):
    
    def __init__(self):
        threading.Thread.__init__(self)
        
    def run(self):
        pass