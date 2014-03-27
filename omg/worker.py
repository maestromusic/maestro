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

# Internal states that are used to manage the worker thread
STATE_INIT, STATE_RUNNING, STATE_QUIT = 1,2,3


class ResetException(Exception):
    """This exception is used to abort tasks when the worker thread has been resetted or quitted."""
    pass


class Dispatcher(QtCore.QObject):
    """Internal dispatcher used to signal finished tasks."""
    finished = QtCore.pyqtSignal(object)


class Task:
    """A unit of work that can be given to a worker thread. The worker will call *callable* with the given
    arguments. It is also possible to subclass Task and implement custom behaviour in the process-method.
    
    A subclass can implement the method 'merge' which should take another Task as argument. It should try
    to merge the other task into itself and return whether this was possible.
    """ 
    def __init__(self, callable, *args, **kwargs):
        self.callable = callable
        self.args = args
        self.kwargs = kwargs
        
    def process(self):
        """Called from the worker thread to get this task done."""
        self.callable(*self.args, **self.kwargs)
       
    
class Queue:
    """A simple FIFO-queue for inter-thread communication. Contrary to Python's queue.Queue it supports
    merging: Whenever a task is added, the existing tasks are asked to instead merge the new task into itself
    (see Task).
    """ 
    def __init__(self):
        self._lock = threading.Lock()
        self._fullEvent = threading.Event()
        self._tasks = []
    
    def isEmpty(self):
        """Return whether the queue is empty."""
        with self._lock:
            return len(self._tasks) == 0
            
    def put(self, task):
        """Add a Task to the queue. If possible, merge the task with an existing one."""
        with self._lock:
            for t in self._tasks:
                if hasattr(t, 'merge') and t.merge(task):
                    return
            else:
                self._tasks.append(task)
                self._fullEvent.set()
            
    def get(self):
        """Remove and return the first (oldest) task from the queue or block until one is available."""
        while True:
            with self._lock:
                if len(self._tasks) > 0:
                    return self._tasks.pop(0)
                self._fullEvent.clear() # This line must be covered by the lock, the next one must not!
            self._fullEvent.wait() # If no item was available, block until something is put into the queue
        
    def clear(self):
        """Clear the queue."""
        with self._lock:
            self._tasks.clear()
            self._fullEvent.clear()
    
    
class Worker(threading.Thread):
    """A worker thread that processes tasks. Tasks should be added with the 'submit' method. When a task
    is finished *callable* is called with the task as argument. This call is done in the thread that created
    the Worker, not in the worker thread. If *dbConnection* is True, the worker thread will establish a
    database connection so that Tasks can use database.query and the like.
    """
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
        """Submit a task to be processed in the worker thread."""
        if self.state != STATE_QUIT:
            self._emptyEvent.clear()
            task._resetCount = self._resetCount
            self._queue.put(task)
        
    def reset(self):
        """Reset the worker thread, i.e. stop and remove all submitted tasks."""
        if self.state != STATE_QUIT:
            self._resetCount += 1
            self._queue.put(None) # wake up worker if it is blocking in queue.get
    
    def quit(self):
        """Quit the worker thread."""
        self.state = STATE_QUIT
        self._resetCount += 1 # don't handle tasks anymore
        self._queue.put(None) # wake up worker if it is blocking in queue.get
        
    def join(self, timeout=None):
        """Block until all tasks have been processed (or *timeout* has elapsed)."""
        self._emptyEvent.wait(timeout)
    
    def checkWorkerState(self, task):
        """This method is called before tasks are processed. If for some reason the task should not be
        processed anymore (e.g. reset has been called), this method will raise a ResetException.
        Also this method is stored in the attribute 'checkWorkerState' of each task. Long-running tasks
        may call it during processing so that processing is aborted if the worker state requires it.
        Note that it is not possible or necessary to pass the specific task as argument to
        task.checkWorkerState.
        """
        if task._resetCount != self._resetCount:
            raise ResetException()
    
    def _handleFinished(self, task):
        if task._resetCount == self._resetCount:
            self.callable(task)
            
    def runInit(self):
        """Called at the beginning of the worker thread. Subclasses might reimplement it."""
        if self.dbConnection:
            from . import database
            database.connect()
    
    def runShutdown(self):
        """Called at the end of the worker thread. Subclasses might reimplement it."""
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
