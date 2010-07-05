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


def hasCover(containerId):
    """Return whether the container with the given id has a cover."""
    assert isinstance(containerId,int)
    return os.path.exists(COVER_DIR+"large/"+str(containerId))

def getCoverPath(containerId,size=None):
    assert isinstance(containerId,int)
    if size is None:
        dir = COVER_DIR+"large/"
    else: dir = COVER_DIR+"cache_{0}/".format(size)
    
    if not os.path.exists(dir+str(containerId)):
        try:
            cacheCover(containerId,size)
        except IOError:
            return None
    
    return dir+str(containerId)
    
def getCover(containerId,size=None):
    """Return the cover of the given container as QImage. If no cover is found or Qt was not able to load the image, return None. If <size> is None, the large cover will be returned. Otherwise the cover will be scaled to size x size pixels and cached in the appropriate folder."""
    assert isinstance(containerId,int)
    path = getCoverPath(containerId,size)
    if path is not None:
        cover = QtGui.QImage(path)
        if not cover.isNull(): # Loading succeeded
            return cover
    return None
    
def cacheCover(containerId,size):
    """Create a thumbnail of the cover of the container with the given id with <size>x<size> pixels and cache it in the appropriate cache-folder."""
    assert isinstance(containerId,int)
    assert isinstance(size,int)
    largeCover = QtGui.QImage(COVER_DIR+"large/"+str(containerId))
    if largeCover.isNull():
        raise IOError("Cover of container {0} could not be loaded.".format(containerId))
    smallCover = largeCover.scaled(QtCore.QSize(size,size),Qt.KeepAspectRatio,Qt.SmoothTransformation)
    
    dir = COVER_DIR+"cache_{0}/".format(size)
    if not os.path.isdir(dir):
        os.mkdir(dir)
    
    if not smallCover.save(dir+str(containerId),"png"):
        raise IOError("File {0} could not be saved.".format(dir+str(containerId)))


def cacheAll(size):
    """Create thumbnails with <size>x<size> pixels of all covers and save them in the appropriate cache-folder."""
    for path in os.listdir(COVER_DIR+"large/"):
        if path.isdigit() and os.path.isfile(COVER_DIR+"large/"+path):
            try:
                cacheCover(path,size)
            except IOError as e:
                print(e)