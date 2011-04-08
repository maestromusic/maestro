#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

# Some global functions that did not fit anywhere else
import os

from PyQt4 import QtGui

from omg import constants
from omg.config import options
import os

def relPath(file):
    """Returns the relative path of a music file against the collection base path."""
    if os.path.isabs(file):
        return os.path.relpath(file, options.music.collection)
    else:
        return file

def absPath(file):
    """Returns the absolute path of a music file inside the collection directory, if it is not absolute already."""
    if not os.path.isabs(file):
        return os.path.join(options.music.collection, file)
    else:
        return file

def getIconPath(name):
    return os.path.join(constants.IMAGES, "icons", name)

def getIcon(name):
    return QtGui.QIcon(getIconPath(name))

