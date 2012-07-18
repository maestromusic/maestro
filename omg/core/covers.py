# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

import os, os.path, hashlib, re

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import config
from . import tags
from .elements import Element

# Absolute path to the cover folder
COVER_DIR = None

# Maximum length of an encoded filename. Since the names aren't really important there is no need to get
# the real limit which depends on the filesystem and operating system.
MAX_FILENAME_LENGTH = 120

# Registered providers classes which must be subclasses of AbstractCoverProvider. Plugins may add and remove
# own classes to this list directly.
providerClasses = []

#TODO make editable
cacheSizes = [40]


def init():
    """Initialize the cover framework."""
    global COVER_DIR
    coverPath = config.options.misc.cover_path
    if os.path.isabs(coverPath):
        COVER_DIR = coverPath
    else: COVER_DIR = os.path.normpath(os.path.join(config.CONFDIR,coverPath))
    
    # Make sure that this directory exists
    os.makedirs(COVER_DIR,exist_ok=True)
    
    
def shutdown():
    """Shut down the cover framework. Occasionally this will delete superfluous cover files from the 
    internal folder."""
    # TODO: From time to time delete unused covers and cache folders
    pass
    
    
def get(path,size=None):
    """Return a QPixmap with the cover from the specified path which can be absolute or relative to the
    cover folder. If *size* is given, the result will be scaled to have *size* for width and height.
    If *size* is one of the cached sizes, this method will use the cache to skip the scaling.
    """ 
    if not os.path.isabs(path):
        path = os.path.join(COVER_DIR,path)
    if size in cacheSizes:
        cachePath = _cachePath(path,size)
        if os.path.exists(cachePath):
            return QtGui.QPixmap(cachePath)
    pixmap = QtGui.QPixmap(path)
    if size is not None and (pixmap.width() != size or pixmap.height() != size):
        pixmap = pixmap.scaled(size,size,transformMode=Qt.SmoothTransformation)
    if size in cacheSizes:
        os.makedirs(os.path.dirname(cachePath),exist_ok=True)
        pixmap.save(cachePath,config.options.misc.cover_extension)
    return pixmap


class AbstractCoverProvider(QtCore.QObject):
    """Abstract base class for cover providers. A cover provider fetches covers for elements, typically from
    a webservice. It may process several elements at the same time and may return more than one cover for
    an element (e.g. if the webservice is not sure which is the correct cover).
    """
    
    # This signal is emitted whenever a cover has been loaded. The signal contains the element and the loaded
    # QPixmap as parameters
    loaded = QtCore.pyqtSignal(Element,QtGui.QPixmap)
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
    
    def fetch(self,elements):
        """Start fetching covers for the given elements asynchronously."""
        raise NotImplementedError()


class CoverUndoCommand(QtGui.QUndoCommand):
    """UndoCommand that changes the covers of one or more elements in the given level. *covers* must be a
    dict mapping elements to either a cover path or a QPixmap or None."""
    def __init__(self,level,covers):
        super().__init__()
        self.level = level
        self.covers = {}
        for element,coverOrPath in covers.items():
            oldPath = element.getCoverPath()
            
            if isinstance(coverOrPath,QtGui.QPixmap):
                pixmap = coverOrPath
                newPath,absPath = _makeFilePath(element)
                os.makedirs(os.path.dirname(absPath),exist_ok=True)
                if not pixmap.save(absPath):
                    newPath,absPath = _makeFilePath(element,forceAscii=True)
                    pixmap.save(absPath) #TODO do something if this goes wrong
            elif isinstance(coverOrPath,str) or coverOrPath is None:
                newPath = coverOrPath
            else: raise TypeError("Values of 'covers' must be either QPixmap or str or None")

            if oldPath != newPath:
                self.covers[element] = (oldPath,newPath)
        
    def redo(self):
        elementToData = {element: [paths[1]] if paths[1] is not None else None
                          for element,paths in self.covers.items()}
        self.level._setData('COVER',elementToData)
            
    def undo(self):
        elementToData = {element: [paths[0]] if paths[0] is not None else None
                          for element,paths in self.covers.items()}
        self.level._setData('COVER',elementToData)


def _cachePath(path,size):
    """Return the filename that is used for the cached versions of the cover at *path*. Of course, it would
    be best to use the same filenames as in *path*. But then external files might collide with internal ones.
    Hence this method uses hashes.
    """
    md5 = hashlib.md5(path.encode()).hexdigest()
    return os.path.join(COVER_DIR,'cache_{}'.format(size),md5)
    
        
def _makeFilePath(element,forceAscii=False):
    """Return a file path that can be used to save the large cover of the given element. The path should be
    based on the element's artist-tags and title-tags. If *forceAscii* is True, the result will only contain
    ASCII characters. Otherwise the result might contain all unicode letters, but not all unicode characters.
    
    This method returns a tuple containing the relative path and the absolute path.
    """ 
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
    
    # Handle unicode characters
    if forceAscii:
        # How to automatically replace characters by their closest ASCII character?
        # unicodedata.normalize('NFKD') represents characters like e.g. 'á' in its decomposed form '´a'.
        # Since the accent is a 'combining accent' it will be combined with the letter automatically and
        # you won't see the difference unless you check the length of the string.
        # encode('ascii','ignore') throws all those scary characters away.
        import unicodedata
        fileName = unicodedata.normalize('NFKD',fileName).encode('ascii','ignore').decode()
    
    # Remove weird characters and weird use of whitespace
    fileName = re.sub('[^\w\s_-]','',fileName).strip()
    fileName = re.sub('\s+',' ',fileName)
    
    # In the easiest form, the following simply adds the extension and returns the path.
    # Actually it deals with two problems that may arise:
    # - The filename may be too long
    # - The filename may exist already
    # To solve the first problem, the fileName is shortened, to solve the second one we append '_n' for some
    # number n to the filename (but in front of the extension)
    # We do this until we have found a valid and non-existent filename.
    extension = '.'+config.options.misc.cover_extension
    i = -1
    currentExt = extension # currentExt is the suffix together with the extension
    while True:
        i += 1
        currentExt = extension if i == 0 else '_{}{}'.format(i,extension)
        if len(fileName.encode()) + len(currentExt.encode()) > MAX_FILENAME_LENGTH:
            length = MAX_FILENAME_LENGTH - len(currentExt.encode())
            # ignore errors that may arise from cropping the string inside a multibyte character
            fileName = fileName.encoded()[:length].decode('utf-8','ignore')
            continue
        
        path = os.path.join(COVER_DIR,'large',fileName+currentExt)
        if os.path.exists(path):
            continue
        
        return os.path.join('large',fileName+currentExt),path
    