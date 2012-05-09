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

import os

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import config


COVER_DIR = os.path.join(config.CONFDIR,'cover')


def hasCover(elementId):
    """Return whether the element with the given id has a cover."""
    assert isinstance(elementId,int)
    return os.path.exists(os.path.join(COVER_DIR,"large",str(elementId)))


def getCoverPath(elementId,size=None):
    """Return the path to the cover of the element with id *elementId* in size *size*x*size* pixel or in
    original size, if *size* is None. Return None if the element has no cover."""
    assert isinstance(elementId,int)
    if size is None:
        dir = os.path.join(COVER_DIR,'large')
    else: dir = os.path.join(COVER_DIR,'cache_{0}'.format(size))
    path = os.path.join(dir,str(elementId))
    
    if not os.path.exists(path):
        if size is None:
            return None # Element does not have a cover
        else:
            try:
                cacheCover(elementId,size)
                return path
            except IOError:
                return None
    else: return path


def getCover(elementId,size=None):
    """Return the cover of the given element as QPixmap. If no cover is found or Qt was not able to load the
    image, return None. If *size* is None, the large cover will be returned. Otherwise the cover will be
    scaled to size x size pixels and cached in the appropriate folder."""
    assert isinstance(elementId,int)
    path = getCoverPath(elementId,size)
    if path is not None:
        cover = QtGui.QPixmap(path)
        if not cover.isNull(): # Loading succeeded
            return cover
    return None


def cacheCover(elementId,size):
    """Create a thumbnail of the cover of the element with the given id with *size*x*size* pixels and cache
    it in the appropriate cache-folder."""
    assert isinstance(elementId,int)
    assert isinstance(size,int)
    largeCover = QtGui.QPixmap(os.path.join(COVER_DIR,'large',str(elementId)))
    if largeCover.isNull():
        raise IOError("Cover of element {} could not be loaded.".format(elementId))
    smallCover = largeCover.scaled(QtCore.QSize(size,size),Qt.KeepAspectRatio,Qt.SmoothTransformation)
    
    dir = os.path.join(COVER_DIR,'cache_{}'.format(size))
    if not os.path.isdir(dir):
        os.mkdir(dir)
    
    path = os.path.join(dir,str(elementId))
    if not smallCover.save(path,"png"):
        raise IOError("File {} could not be saved.".format(path))


def cacheAll(size):
    """Create thumbnails with *size*x*size* pixels of all covers and save them in the appropriate
    cache-folder."""
    for path in os.listdir(os.path.join(COVER_DIR,'large')):
        if path.isdigit() and os.path.isfile(os.path.join(COVER_DIR,'large',path)):
            try:
                cacheCover(path,size)
            except IOError as e:
                print(e)
      
      
def setCover(id,cover):
    """Set the cover of the element with the given id to the QPixmap *cover*. If *cover* is None remove any
    previous cover. This method will push a CoverUndoCommand on the stack so the change can be undone."""
    if not isinstance(cover,QtGui.QPixmap) or not isinstance(id,int):
        raise TypeError("cover must be a QPixmap, id an int")
    from . import modify
    modify.push(modify.commands.CoverUndoCommand(id,cover))
    
        
def saveCover(id,cover):
    """Set the cover of the element with the given id to the QPixmap *cover*.  If *cover* is None remove any
    previous cover. This method will not push a CoverUndoCommand on the stack, use setCover instead. Return
    whether saving was successful."""
    assert isinstance(id,int)
    if not os.path.exists(COVER_DIR):
        os.mkdir(COVER_DIR)
    if not os.path.exists(os.path.join(COVER_DIR,'large')):
        os.mkdir(os.path.join(COVER_DIR,'large'))
        
    if cover is not None:
        success = cover.save(os.path.join(COVER_DIR,'large',str(id)),"png")
    else:
        if os.path.exists(os.path.join(COVER_DIR,'large',str(id))):
            os.remove(os.path.join(COVER_DIR,'large',str(id)))
        success = True
    
    if success:
        # Remove cached files
        for path in os.listdir(COVER_DIR):
            if path[0:6] == "cache_" and os.path.isfile(os.path.join(COVER_DIR,path,str(id))):
                os.remove(os.path.join(COVER_DIR,path,str(id)))
        
        from . import modify
        modify.dispatcher.changes.emit(modify.events.CoverChangeEvent(id))
        
    return success
