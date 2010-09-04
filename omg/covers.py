#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

import os
import shutil
from PyQt4 import QtGui,QtCore
from PyQt4.QtCore import Qt

# Path to cover directory
COVER_DIR = os.path.expanduser("~/.omg/cover/")


def hasCover(elementId):
    """Return whether the element with the given id has a cover."""
    assert isinstance(elementId,int)
    return os.path.exists(COVER_DIR+"large/"+str(elementId))

def getCoverPath(elementId,size=None):
    """Return the path to the cover of the element with id <elementId> in size <size>x<size> pixel or in original size, if <size> is None."""
    assert isinstance(elementId,int)
    if size is None:
        dir = COVER_DIR+"large/"
    else: dir = COVER_DIR+"cache_{0}/".format(size)
    
    if not os.path.exists(dir+str(elementId)):
        try:
            cacheCover(elementId,size)
        except IOError:
            return None
    
    return dir+str(elementId)
    
def getCover(elementId,size=None):
    """Return the cover of the given element as QImage. If no cover is found or Qt was not able to load the image, return None. If <size> is None, the large cover will be returned. Otherwise the cover will be scaled to size x size pixels and cached in the appropriate folder."""
    assert isinstance(elementId,int)
    path = getCoverPath(elementId,size)
    if path is not None:
        cover = QtGui.QImage(path)
        if not cover.isNull(): # Loading succeeded
            return cover
    return None
    
def cacheCover(elementId,size):
    """Create a thumbnail of the cover of the element with the given id with <size>x<size> pixels and cache it in the appropriate cache-folder."""
    assert isinstance(elementId,int)
    assert isinstance(size,int)
    largeCover = QtGui.QImage(COVER_DIR+"large/"+str(elementId))
    if largeCover.isNull():
        raise IOError("Cover of element {0} could not be loaded.".format(elementId))
    smallCover = largeCover.scaled(QtCore.QSize(size,size),Qt.KeepAspectRatio,Qt.SmoothTransformation)
    
    dir = COVER_DIR+"cache_{0}/".format(size)
    if not os.path.isdir(dir):
        os.mkdir(dir)
    
    if not smallCover.save(dir+str(elementId),"png"):
        raise IOError("File {0} could not be saved.".format(dir+str(elementId)))


def cacheAll(size):
    """Create thumbnails with <size>x<size> pixels of all covers and save them in the appropriate cache-folder."""
    for path in os.listdir(COVER_DIR+"large/"):
        if path.isdigit() and os.path.isfile(COVER_DIR+"large/"+path):
            try:
                cacheCover(path,size)
            except IOError as e:
                print(e)
                

def setCover(id,cover):
    assert isinstance(id,int)
    if not cover.save(COVER_DIR+"large/"+str(id),"png"):
        return False
    else:
        # Remove cached files
        for path in os.listdir(COVER_DIR):
            if path[0:6] == "cache_" and os.path.isfile(COVER_DIR+path+"/"+str(id)):
                os.remove(COVER_DIR+path+"/"+str(id))
        return True