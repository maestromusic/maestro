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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

# Internal states that are used to manage the worker thread
STATE_INIT, STATE_RUNNING, STATE_QUIT = 1,2,3

class ResetException(Exception):
    """This exception is used to abort tasks when the worker thread has been resetted or quitted."""
    pass


class Task:
    """A unit of work that can be given to a worker thread. The worker will call *callable* with the given
    arguments. It is also possible to subclass Task and implement custom behaviour in the process-method.
    """ 
    def __init__(self, callable, *args, **kwargs):
        self.callable = callable
        self.args = args
        self.kwargs = kwargs
        
    def process(self):
        """Called from the worker thread to get this task done."""
        self.callable(*self.args, **self.kwargs)
        
    def merge(self, other):
        """Try to merge the task *other* in this task and return whether it was successful. The worker queue
        will try to merge new tasks into older tasks instead of putting them into the queue."""
        return False
       
    
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
    

class Worker(QtCore.QObject):
    """A worker thread that processes tasks. Tasks should be added with the 'submit' method. When a task
    is finished, the done-signal is emitted with the task as argument. The signal is emitted from the 
    thread, that created the worker, so it is usually not necessary to use a queued connection.
    If *dbConnection* is True, the worker thread will establish a database connection so that Tasks can use
    database.query and the like.
    """
    done = QtCore.pyqtSignal(Task)
    _done = QtCore.pyqtSignal(Task)
    
    def __init__(self, dbConnection=False):
        super().__init__()
        self.state = STATE_INIT
        self.dbConnection = dbConnection
        self._resetCount = 0
        self._done.connect(self._handleDone, Qt.QueuedConnection)
        self._queue = Queue()
        self._emptyEvent = threading.Event()
        self._thread = threading.Thread(target=self.run)
        self._thread.daemon = True
    
    def start(self):
        self._thread.start()
    
    def submit(self, task):
        """Submit a task to be processed in the worker thread."""
        if self.state != STATE_QUIT:
            self._emptyEvent.clear()
            task._resetCount = self._resetCount
            self._queue.put(task)
    
    def submitMany(self, tasks):
        """Submit a list of tasks to be processed in the worker thread."""
        for task in tasks:
            self.submit(task)
            
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
            
    def runInit(self):
        """Called at the beginning of the worker thread. Subclasses might reimplement it."""
        if self.dbConnection:
            from .. import database
            database.connect()
    
    def runShutdown(self):
        """Called at the end of the worker thread. Subclasses might reimplement it."""
        if self.dbConnection:
            from .. import database
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
                    self._done.emit(task)
                except ResetException:
                    if self.state == STATE_QUIT:
                        break
        finally:
            self.state = STATE_QUIT # don't accept new tasks (if execution stopped due to an exception)
            self._emptyEvent.set() # don't forget to unblock threads waiting for this event
            self.runShutdown()
    
    def _handleDone(self, task):
        """Before emitting the real 'done'-signal, filter tasks out that were added before the last reset."""
        if task._resetCount == self._resetCount:
            self.done.emit(task)
    
    def loadImage(self, path, size=None):
        """Start loading the image from *path* and return a FutureImage-instance for it.
        If *size* is given, scale the image after loading to *size* (a QSize)."""
        task = LoadImageTask(path, size)
        self.submit(task)
        return tasks
    
    def loadImages(self, paths, size=None):
        """Start loading images from *paths* and return a list of LoadImageTask-instances for them.
        If *size* is given, scale all images after loading to *size* (a QSize)."""
        tasks = [LoadImageTasks(path, size) for path in paths]
        self.submitMany(tasks)
        return tasks


class LoadImageTask(Task):
    """A task that loads an image from *path* and optionally resizes it to *size* (a QSize). When the 
    image has been loaded, the attribute 'loaded' will be set to True and 'pixmap' can be used to retrieve
    it.
    """
    def __init__(self, path, size=None):
        self.path = path
        self.size = size
        # QPixmap may only be used in the GUI thread. Thus we have to use QImage first.
        self._image = None
        self._pixmap = None

    @property
    def loaded(self):
        """True when the image has been loaded."""
        return self._pixmap is not None or self._image is not None
    
    @property
    def pixmap(self):
        """Get the pixmap inside this wrapper or None if it has not been loaded yet."""
        if self._pixmap is not None:
            return self._pixmap
        elif self._image is not None:
            self._pixmap = QtGui.QPixmap.fromImage(self._image)
            self._image = None # save memory
            return self._pixmap
        else: None
        
    def process(self):
        # QPixmap may only be used in the GUI thread. Thus we have to load the images as QImage and
        # transform them later in the GUI thread (see FutureImage.pixmap).
        image = QtGui.QImage(self.path)
        if not image.isNull() and self.size is not None and image.size() != self.size:
            image = image.scaled(self.size, transformMode=Qt.SmoothTransformation)
        self._image = image

    def merge(self, other):
        return self.path == other.path and self.size == other.size
    