# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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

import os.path, hashlib, re, time

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from .. import config, logging, utils
from . import tags
from .elements import Element

# Absolute path to the cover folder
COVER_DIR = None


# When the last check for unused covers is more than this number of seconds ago, a new one will start at
# application shutdown.
DELETE_UNUSED_COVERS_INTERVAL = 604800 # one week

# Registered providers classes which must be subclasses of AbstractCoverProvider. Plugins may add and remove
# own classes to this list directly.
providerClasses = []

# Whenever a cover is requested in one of the sizes in this list, it will be cached in the corresponding
# cache_<size>-folder. Use addCacheSize to modify this list.
cacheSizes = []


def init():
    """Initialize the cover framework."""
    global COVER_DIR
    coverPath = config.options.misc.cover_path
    if os.path.isabs(coverPath):
        COVER_DIR = coverPath
    else: COVER_DIR = os.path.normpath(os.path.join(config.CONFDIR, coverPath))
    
    # Make sure that this directory exists
    if not os.path.isdir(COVER_DIR):
        os.makedirs(COVER_DIR)
    
    
def shutdown():
    """Shut down the cover framework. Occasionally this will delete superfluous cover files from the 
    internal folder."""
    # Delete cached covers in sizes that have not been added to cacheSizes in this application run
    for folder in os.listdir(COVER_DIR):
        if re.match('cache_\d+$', folder) is not None:
            size = int(folder[len('cache_'):])
            if size not in cacheSizes:
                absFolder = os.path.join(COVER_DIR, folder)
                for file in os.listdir(absFolder):
                    os.remove(os.path.join(absFolder, file))
                os.rmdir(absFolder)
                
    # From time to time remove unused covers
    lastCoverCheck = config.storage.misc.last_cover_check
    if lastCoverCheck < time.time() - DELETE_UNUSED_COVERS_INTERVAL:
        removeUnusedCovers()
        config.storage.misc.last_cover_check = int(time.time())

    
def get(path, size=None):
    """Return a QPixmap with the cover from the specified path which can be absolute or relative to the
    cover folder. If *size* is given, the result will be scaled to have *size* for width and height.
    If *size* is one of the cached sizes, this method will use the cache to skip the scaling.
    """
    # First try to return from cache
    if size in cacheSizes:
        cachePath = _cachePath(path, size)
        if os.path.exists(cachePath):
            return QtGui.QPixmap(cachePath)
        
    # Read the file
    if not os.path.isabs(path):
        path = os.path.join(COVER_DIR, path)
    pixmap = QtGui.QPixmap(path)
    if pixmap.isNull():
        logging.warning(__name__, "Could not load cover from path '{}'.".format(path))
        return None
    if size is not None and (pixmap.width() != size or pixmap.height() != size):
        pixmap = pixmap.scaled(size, size,
                               aspectRatioMode=Qt.KeepAspectRatio,
                               transformMode=Qt.SmoothTransformation)
        
    if size in cacheSizes:
        storeInCache(pixmap, cachePath)
        
    return pixmap


def getHTML(path, size=None, attributes=''):
    """Return a <img>-tag containing the cover at *path* which can be absolute or relative to the cover
    folder. If *size* is given, the <img>-tag will contain a scaled version of the cover. The optional
    argument *attributes* may contain additional HTML-attributes and is simply inserted into the tag.
    
    Note: If *size* is given and not a cached size, the <img>-tag cannot refer to a scaled image on the
    filesystem. Instead, the scaled image is inserted directly into the <img>-tag, making the tag rather
    large.
    """ 
    def makeImgTag(source):
        return '<img width="{0}" height="{0}" {1} src="{2}"/>'.format(size, attributes, source)
    
    if size is None:
        if not os.path.isabs(path):
            path = os.path.join(COVER_DIR, path)
        return makeImgTag(path)
    
    if size in cacheSizes:
        cachePath = _cachePath(path, size)
        if not os.path.exists(cachePath):
            get(path, size)
        return makeImgTag(path)
    
    # Neither the 'large' cover nor any cached size is requested.
    if not os.path.isabs(path):
        path = os.path.join(COVER_DIR, path)
    pixmap = QtGui.QPixmap(path)
    if pixmap.isNull():
        return None
    if pixmap.width() != size or pixmap.height() != size:
        pixmap = pixmap.scaled(size, size,
                               aspectRatioMode=Qt.KeepAspectRatio,
                               transformMode=Qt.SmoothTransformation)
    return utils.images.html(pixmap, 'width="{}" height="{}" {}'
                             .format(pixmap.width(), pixmap.height(), attributes))


def storeInCache(pixmap, cachePath):
    """Store the *pixmap* at *cachePath*."""
    os.makedirs(os.path.dirname(cachePath), exist_ok=True)
    pixmap.save(cachePath, config.options.misc.cover_extension)
    
    
def addCacheSize(size):
    """Add the given size (size=width=height) to the list of sizes that will be cached. Make sure it is not
    added twice."""
    if size not in cacheSizes:
        cacheSizes.append(size)


def removeUnusedCovers():
    """Check whether the 'large' folder contains covers that are not used in the stickers-table and delete
    those covers. Also delete cached versions of those covers.
    """
    if not os.path.exists(os.path.join(COVER_DIR, 'large')):
        return
    from .. import database as db
    usedPaths = [path for path in db.query("SELECT data FROM {p}stickers WHERE type = 'COVER'")
                 .getSingleColumn() if not os.path.isabs(path)] # never remove external covers
    for path in os.listdir(os.path.join(COVER_DIR, 'large')):
        path = os.path.join('large', path)
        if path not in usedPaths:
            os.remove(os.path.join(COVER_DIR, path))
            cacheFile = _cachePath(path, None)
            for folder in os.listdir(COVER_DIR):
                if re.match('cache_\d+$', folder) is not None:
                    if os.path.exists(os.path.join(COVER_DIR, folder, cacheFile)):
                        os.remove(os.path.join(COVER_DIR, folder, cacheFile))
    

class LoadCoverTask(utils.worker.LoadImageTask):
    """A task to load a cover asynchronously using a utils.worker.Worker.
    *path* and *size* are used as in 'get'.
    """
    def __init__(self, path, size=None):
        super().__init__(path, QtCore.QSize(size, size) if size is not None else None)
        self.cacheImage = False
        if size in cacheSizes:
            self.cachePath = _cachePath(path, size)
            if os.path.exists(self.cachePath):
                self.path = self.cachePath
            else:
                self.cacheImage = True
        if not os.path.isabs(self.path):
            self.path = os.path.join(COVER_DIR, self.path)
        
    def process(self):
        super().process()
        if self.cacheImage and not self._image.isNull():
            storeInCache(self._image, self.cachePath)
    

class AbstractCoverProvider(QtCore.QObject):
    """Abstract base class for cover providers. A cover provider fetches covers for elements, typically from
    a webservice. It may process several elements at the same time and may return more than one cover for
    an element (e.g. if the webservice is not sure which is the correct cover).
    """
    
    # This signal is emitted whenever a cover has been loaded. The signal contains the element and the loaded
    # QPixmap as parameters
    loaded = QtCore.pyqtSignal(Element, QtGui.QPixmap)
    # This signal is emitted when an error occurs. Typically these are network errors
    error = QtCore.pyqtSignal(str)
    # This signal is emitted when the provider finishes processing an element, i.e. after the loaded-signal
    # has been emitted for the last time for this element.
    finished = QtCore.pyqtSignal(Element)
            
    @classmethod
    def name(cls):
        """Return a name that represents this provider class. The name should be translated."""
        raise NotImplementedError()
    
    @classmethod
    def icon(self):
        """Return an icon that represents this provider class."""
        return QtGui.QIcon()
    
    def fetch(self, elements):
        """Start fetching covers for the given elements asynchronously."""
        raise NotImplementedError()
    
    def isBusy(self):
        """Return whether the cover provider is currently busy (e.g. downloading a cover)."""
        raise NotImplementedError()


class CoverUndoCommand:
    """UndoCommand that changes the covers of one or more elements in the given level. *covers* must be a
    dict mapping elements to either a cover path or a QPixmap or None."""
    def __init__(self, level, covers):
        self.level = level
        self.covers = {}
        self.text = translate("CoverUndoCommand", "change covers")
        for element, coverOrPath in covers.items():
            oldPath = element.getCoverPath()
            
            if isinstance(coverOrPath, QtGui.QPixmap):
                pixmap = coverOrPath
                folder = os.path.join(COVER_DIR, 'large')
                # Concatenate all artist-tags and all title-tags
                if tags.get("artist") in element.tags:
                    fileName = "-".join(element.tags[tags.get("artist")])+' - '
                else: fileName = ''
                if tags.TITLE in element.tags:
                    fileName += "-".join(element.tags[tags.TITLE])
                else:
                    # I shortly thought about using the element's id, but often covers are changed on the editor level
                    # before a commit, so the id will be negative and change soon.
                    fileName += 'notitle'
                fileName += '.' + config.options.misc.cover_extension
                path = utils.files.makeFilePath(folder, fileName)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                if not pixmap.save(path):
                    path = utils.files.makeFilePath(folder, fileName, forceAscii=True)
                    pixmap.save(path) #TODO do something if this doesn't work
                newPath = os.path.relpath(path, COVER_DIR)
            elif isinstance(coverOrPath, str) or coverOrPath is None:
                newPath = coverOrPath
            else: raise TypeError("Values of 'covers' must be either QPixmap or str or None")

            if oldPath != newPath:
                self.covers[element] = (oldPath, newPath)
        
    def redo(self):
        elementToSticker = {element: [paths[1]] if paths[1] is not None else None
                            for element, paths in self.covers.items()}
        self.level._setStickers('COVER', elementToSticker)
            
    def undo(self):
        elementToSticker = {element: [paths[0]] if paths[0] is not None else None
                            for element, paths in self.covers.items()}
        self.level._setStickers('COVER', elementToSticker)


def _cachePath(path, size):
    """Return the filename that is used for the cached versions of the cover at *path*. Of course, it would
    be best to use the same filenames as in *path*. But then external files might collide with internal ones.
    Hence this method uses hashes.
    
    If *size* is None, only return the filename without path.
    """
    md5 = hashlib.md5(path.encode()).hexdigest()
    if size is not None:
        return os.path.join(COVER_DIR, 'cache_{}'.format(size), md5)
    else: return md5
