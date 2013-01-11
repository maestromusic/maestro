# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2013 Martin Altmayer, Michael Helmling
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

import threading

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

_thread = None

class FutureImage:
    """A wrapper around an image that is currently loaded."""
    def __init__(self):
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
    
    
class ImageLoader(QtCore.QObject):
    """Facility to load images asynchronously. Call loadImage(s) to get FutureImage-instances of your
    images. When an image has been loaded the loaded-attribute of that image is set to True and the
    loaded-signal of this class is emitted with the FutureImage-instance.
    """
    loaded = QtCore.pyqtSignal(FutureImage)
    
    def __init__(self):
        super().__init__()
        global _thread
        if _thread is None:
            _thread = ImageLoaderThread()
            _thread.start()
        
    def loadImage(self, path, size=None):
        """Start loading the image from *path* and return a FutureImage-instance for it.
        If *size* is given, scale the image after loading to *size* (a QSize)."""
        image = FutureImage()
        with _thread.lock:
            _thread.tasks.append((self, path, image, size))
            _thread.event.set()
        return image
    
    def loadImages(self, paths, size=None):
        """Start loading images from *paths* and return a list of FutureImage-instances for them.
        If *size* is given, scale all images after loading to *size* (a QSize)."""
        images = [FutureImage() for path in paths]
        with _thread.lock:
            _thread.tasks.extend((self, path, image, size) for path,image in zip(paths, images))
            _thread.event.set()
        return images


class ImageLoaderThread(threading.Thread):
    """This thread is used internally to load images asynchronously."""
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.lock = threading.Lock()
        self.event = threading.Event()
        self.tasks = [] 
        self.quit = False

    def run(self):
        while True:
            self.lock.acquire()
            if self.quit:
                self.lock.release()
                return # Terminate the thread
            
            if len(self.tasks) == 0:
                # Nothing to do...wait for the event
                self.lock.release()
                self.event.wait()
                self.event.clear()
                continue
            
            loader, path, futureImage, size = self.tasks.pop(0)
            self.lock.release() # release lock so that main thread can add new images without waiting
            
            # QPixmap may only be used in the GUI thread. Thus we have to load the images as QImage and
            # transform them later in the GUI thread (see FutureImage.pixmap).
            image = QtGui.QImage(path)
            if not image.isNull() and size is not None and image.size() != size:
                image = image.scaled(size, transformMode=Qt.SmoothTransformation)
            futureImage._image = image
            loader.loaded.emit(futureImage)
            