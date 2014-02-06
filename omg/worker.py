# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2014 Martin Altmayer, Michael Helmling
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

import threading, functools

from PyQt4 import QtCore
from PyQt4.QtCore import Qt

STATE_INIT, STATE_RUNNING, STATE_QUIT = 1,2,3


class ResetException(Exception):
    pass


class Dispatcher(QtCore.QObject):
    finished = QtCore.pyqtSignal(object)


class Task:
    def __init__(self, callable, *args, **kwargs):
        self.callable = callable
        self.args = args
        self.kwargs = kwargs
        
    def process(self):
        self.callable(*self.args, **self.kwargs)
       
    
class Queue:
    def __init__(self):
        self._lock = threading.Lock()
        self._fullEvent = threading.Event()
        self._tasks = []
    
    def isEmpty(self):
        with self._lock:
            return len(self._tasks) == 0
            
    def put(self, task):
        with self._lock:
            for t in self._tasks:
                if hasattr(t, 'merge') and t.merge(task):
                    return
            else:
                self._tasks.append(task)
                self._fullEvent.set()
            
    def get(self):
        while True:
            with self._lock:
                if len(self._tasks) > 0:
                    return self._tasks.pop(0)
                self._fullEvent.clear() # This line must be covered by the lock, the next one must not!
            self._fullEvent.wait() # If no item was available, block until something is put into the queue
        
    def clear(self):
        with self._lock:
            self._tasks.clear()
            self._fullEvent.clear()
    
    
class Worker(threading.Thread):
    def __init__(self, callable, dbConnection=False):
        super().__init__()
        self.daemon = True
        self.state = STATE_INIT
        self.callable = callable
        self.dbConnection = dbConnection
        self._resetCount = 0
        self._dispatcher = Dispatcher()
        self._dispatcher.finished.connect(self._handleFinished, Qt.QueuedConnection)
        self._queue = Queue()
        self._emptyEvent = threading.Event()
    
    def submit(self, task):
        if self.state != STATE_QUIT:
            self._emptyEvent.clear()
            task._resetCount = self._resetCount
            self._queue.put(task)
        
    def reset(self):
        if self.state != STATE_QUIT:
            self._resetCount += 1
            self._queue.put(None) # wake up worker if it is blocking in queue.get
    
    def quit(self):
        self.state = STATE_QUIT
        self._resetCount += 1 # don't handle tasks anymore
        self._queue.put(None) # wake up worker if it is blocking in queue.get
        
    def join(self, timeout=None):
        self._emptyEvent.wait(timeout)
    
    def checkWorkerState(self, task):
        if task._resetCount != self._resetCount:
            raise ResetException()
    
    def _handleFinished(self, task):
        if task._resetCount == self._resetCount:
            self.callable(task)
            
    def runInit(self):
        if self.dbConnection:
            from . import database
            database.connect()
    
    def runShutdown(self):
        if self.dbConnection:
            from . import database
            database.close()
    
    def run(self):
        self.state = STATE_RUNNING
        self.runInit()
        try:
            while True:
                try:
                    if self._queue.isEmpty():
                        self._emptyEvent.set()
                    task = self._queue.get()
                    if task is None:
                        raise ResetException()
                    self.checkWorkerState(task)
                    task.checkWorkerState = functools.partial(self.checkWorkerState, task)
                    task.process()
                    self._dispatcher.finished.emit(task)
                except ResetException:
                    if self.state == STATE_QUIT:
                        break
        finally:
            self.state = STATE_QUIT # don't accept new tasks (if execution stopped due to an exception)
            self._emptyEvent.set() # don't forget to unblock threads waiting for this event
            self.runShutdown()
