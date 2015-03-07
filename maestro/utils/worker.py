# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2014-2015 Martin Altmayer, Michael Helmling
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

import enum
import threading

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt


class State(enum.Enum):
    """Internal states that are used to manage the worker thread"""
    Init = 0
    Running = 1
    Quit = 3


class ResetException(Exception):
    """This exception is used to abort tasks when the worker thread has been resetted or quitted."""
    pass


class Task:
    """A unit of work that can be given to a worker thread.
    """
        
    def process(self):
        """Called from the worker thread to get this task done. Big tasks can implement this as a generator
        which yields between each major step. This gives the worker the chance to abort the task in between.
        """
        raise NotImplementedError()
        
    def processImmediately(self):
        """In subclasses that return a generator in "process" this can be used to process the task
        without suspending on 'yield'. Use this when processing a task by yourself, not in a Worker thread.
        """
        generator = self.process()
        if generator is not None:
            for n in self.process():
                pass
        
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
                self._fullEvent.clear()  # This line must be covered by the lock, the next one must not!
            self._fullEvent.wait()  # If no item was available, block until something is put into the queue
        
    def clear(self):
        """Clear the queue."""
        with self._lock:
            self._tasks.clear()
            self._fullEvent.clear()
    

class Worker(QtCore.QObject):
    """A worker thread that processes tasks. Tasks should be added with the 'submit' method. When a task
    is finished, the done-signal is emitted with the task as argument. The signal is emitted from the 
    thread, that created the worker, so it is usually not necessary to use a queued connection.
    """
    done = QtCore.pyqtSignal(Task)
    _done = QtCore.pyqtSignal(Task)
    
    def __init__(self):
        super().__init__()
        self.state = State.Init
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
        if self.state != State.Quit:
            self._emptyEvent.clear()
            task._resetCount = self._resetCount
            self._queue.put(task)
    
    def submitMany(self, tasks):
        """Submit a list of tasks to be processed in the worker thread."""
        for task in tasks:
            self.submit(task)
            
    def reset(self):
        """Reset the worker thread, i.e. stop and remove all submitted tasks."""
        if self.state != State.Quit:
            self._resetCount += 1
            self._queue.put(None)  # wake up worker if it is blocking in queue.get
    
    def quit(self):
        """Quit the worker thread."""
        self.state = State.Quit
        self._resetCount += 1  # don't handle tasks anymore
        self._queue.put(None)  # wake up worker if it is blocking in queue.get
        
    def join(self, timeout=None):
        """Block until all tasks have been processed (or *timeout* has elapsed)."""
        self._emptyEvent.wait(timeout)
            
    def runInit(self):
        """Called at the beginning of the worker thread. Subclasses might reimplement it."""
        pass
    
    def runShutdown(self):
        """Called at the end of the worker thread. Subclasses might reimplement it."""
        pass
    
    def run(self):
        self.state = State.Running
        self.runInit()
        try:
            while True:
                try:
                    if self._queue.isEmpty():
                        self._emptyEvent.set()
                    task = self._queue.get()
                    if task is None or task._resetCount != self._resetCount:
                        raise ResetException() # None is inserted to wake up the thread in reset/quit
                    generator = task.process()
                    i = 1
                    if generator is not None: # tasks yields None between each major step...
                        for n in generator:   # ...to give us the chance to abort in between.
                            i += 1
                            if task._resetCount != self._resetCount:
                                raise ResetException()
                    self._done.emit(task)
                except ResetException:
                    if self.state == State.Quit:
                        break
        finally:
            self.state = State.Quit  # don't accept new tasks (if execution stopped due to an exception)
            self._emptyEvent.set()  # don't forget to unblock threads waiting for this event
            self.runShutdown()
    
    def _handleDone(self, task):
        """Before emitting the real 'done'-signal, filter tasks out that were added before the last reset."""
        # This method is executed in the main thread, not in the worker thread
        if task._resetCount == self._resetCount:
            self.done.emit(task)


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
            self._image = None  # save memory
            return self._pixmap

    def process(self):
        # QPixmap may only be used in the GUI thread. Thus we have to load the images as QImage and
        # transform them later in the GUI thread (see FutureImage.pixmap).
        image = QtGui.QImage(self.path)
        if not image.isNull() and self.size is not None and image.size() != self.size:
            image = image.scaled(self.size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._image = image

    def merge(self, other):
        return self.path == other.path and self.size == other.size
