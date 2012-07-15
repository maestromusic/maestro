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

COVER_DIR = None

# Maximum length of an encoded filename. Since the names aren't really important there is no need to get
# the real limit which depends on the filesystem and operating system, of course.
# Actually filenames may be a little bit longer due to the suffixes that are used to avoid collisions.
MAX_FILENAME_LENGTH = 80


providerClasses = []

#TODO make editable
cacheSizes = [80,100]

#TODO: make this a config variable
extension = '.png'


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
    # TODO: From time to time delete unused covers
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
        pixmap.save(cachePath)
    return pixmap


class AbstractCoverProvider(QtCore.QObject):
    loaded = QtCore.pyqtSignal(Element,QtGui.QPixmap)
    error = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(Element)
            
    @classmethod
    def name(cls):
        """Return a name that represents this provider class. The name should be translated."""
        raise NotImplementedError()
    
    @classmethod
    def icon(self):
        """Return an icon that represents this provider class."""
        raise NotImplementedError()
    
    def fetch(self,elements):
        """Start fetching covers for the given elements."""
        raise NotImplementedError()


class CoverUndoCommand(QtGui.QUndoCommand):
    def __init__(self,level,element,coverOrPath):
        super().__init__()
        self.level = level
        self.element = element
        if isinstance(coverOrPath,QtGui.QPixmap):
            pixmap = coverOrPath
            self.newPath = _makeFilePath(element)
            os.makedirs(os.path.dirname(self.newPath),exist_ok=True)
            if not pixmap.save(self.newPath):
                self.newPath = _makeFilePath(element,forceAscii=True)
                pixmap.save(self.newPath) #TODO do something if this goes wrong
        elif isinstance(coverOrPath,str) or coverOrPath is None:
            self.newPath = coverOrPath
        else: raise TypeError("coverOrPath must be either QPixmap or str or None")

        if element.hasCover():
            self.oldPath = element.getCoverPath()
        else: self.oldPath = None
        
    def redo(self):
        if self.newPath is not None:
            _coversToDelete.discard(self.newPath)
            data = (self.newPath,)
        else: data = None
        # Delete unused files at the end. Do not delete external files
        if self.oldPath is not None and self.oldPath.startswith(COVER_DIR):
            _coversToDelete.add(self.oldPath)
        self.level._setData(self.element,'COVER',data)
            
    def undo(self):
        if self.oldPath is not None:
            _coversToDelete.discard(self.oldPath)
            data = (self.oldPath,)
        else: data = None 
        # Delete unused files at the end. Do not delete external files
        if self.newPath is not None and self.newPath.startswith(COVER_DIR):
            _coversToDelete.add(self.newPath)
        self.level._setData(self.element,'COVER',data)


def _cachePath(path,size):
    """Return the filename that is used for the cached versions of the cover at *path*. Of course, it would
    be best to use the same filenames as in *path*. But then external files might collide with internal ones.
    Hence this method uses hashes.
    """
    md5 = hashlib.md5(path).digest()
    return os.path.join(COVER_DIR,'cache_{}'.format(size),md5)
    
        
def _makeFilePath(element,forceAscii=False):
    """Return an absolute file path that can be used to save the large cover of the given element. The 
    path should be based on the element's artist-tags and title-tags. If *forceAscii* is True, the result
    will only contain ASCII characters. Otherwise the result might contain all unicode letters, but
    not all unicode characters.
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
    if not allowUnicode:
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
    
    # Handle filenames that are too long
    if len(fileName.encoded()) > MAX_FILENAME_LENGTH-len(extension):
        # ignore errors that may arise from cropping the string inside a multibyte character
        fileName = fileName.encoded()[:MAX_FILENAME_LENGTH-len(extension)].decode('utf-8','ignore')
        
    # Append extension and a suffix to make the filename unique
    path = os.path.join(COVER_DIR,'large',fileName)
    if not os.path.exists(path+extension):
        return path+extension
    else:
        i = 1
        while os.path.exists('{}_{}{}'.format(path,i,extension)):
            i += 1
        return '{}_{}{}'.format(path,i,extension)
    