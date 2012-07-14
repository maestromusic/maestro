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

COVER_DIR = None

cacheSizes = [80,100]
_coversToDelete = set()

def init():
    global COVER_DIR
    coverPath = config.options.misc.cover_path
    if os.path.isabs(coverPath):
        COVER_DIR = coverPath
    else: COVER_DIR = os.path.normpath(os.path.join(config.CONFDIR,coverPath))
    
    # Make sure that this directory exists
    os.makedirs(COVER_DIR,exist_ok=True)
    
    
def shutdown():
    # Delete unused covers
    print("COVERS TO DELETE: {}".format(_coversToDelete))
    #TODO: remember deleting cached files
    
    
def get(path,size=None):
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


class CoverUndoCommand(QtGui.QUndoCommand):
    def __init__(self,level,element,coverOrPath):
        super().__init__()
        self.level = level
        self.element = element
        if isinstance(coverOrPath,QtGui.QPixmap):
            pixmap = coverOrPath
            self.newPath = _makeFilePath('large',element,allowUnicode=True)
            os.makedirs(os.path.dirname(self.newPath),exist_ok=True)
            if not pixmap.save(self.newPath):
                self.newPath = _makeFilePath('large',element,allowUnicode=False)
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
    # Compute filename of cached file
    # We'd like to use the same filenames as in the directory 'large'. But then external files might lead
    # to collisions. So let's use hashes.
    md5 = hashlib.md5(path).digest()
    return os.path.join(COVER_DIR,str(size),md5)
    
        
def _makeFilePath(folder,element,allowUnicode):
    if tags.get("artist") in element.tags:
        fileName = "-".join(element.tags[tags.get("artist")])+' - '
    else: fileName = ''
    if tags.TITLE in element.tags:
        fileName += "-".join(element.tags[tags.TITLE])
    else:
        # I shortly thought about using the element's id, but often covers are changed on the editor level
        # before a commit, so the id will be negative and change soon.
        fileName += 'notitle'
    
    if not allowUnicode:
        # How to automatically replace characters by their closest ASCII character?
        # unicodedata.normalize('NFKD') represents characters like e.g. 'á' in its decomposed form '´a'.
        # Since the accent is a 'combining accent' it will be combined with the letter automatically and
        # you won't see the difference unless you check the length of the string.
        # encode('ascii','ignore') throws all those scary characters out.
        import unicodedata
        fileName = unicodedata.normalize('NFKD',fileName).encode('ascii','ignore').decode()
        
    fileName = re.sub('[^\w\s_-]','',fileName).strip()
    fileName = re.sub('\s+',' ',fileName)

    path = os.path.join(COVER_DIR,folder,fileName)
    if not os.path.exists(path+'.png'):
        return path+'.png'
    else:
        i = 1
        while os.path.exists('{}_{}.png'.format(path,i)):
            i += 1
        return '{}_{}.png'.format(path,i)
    