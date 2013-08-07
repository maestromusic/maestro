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

import subprocess

from PyQt4 import QtCore
from omg import filebackends
from omg.gui import editor

translate = QtCore.QCoreApplication.translate

drives = None

def enable():
    global drives
    drives = findDrives()
    from . import filebackend as cdfilebackend
    filebackends.urlTypes["audiocd"] = cdfilebackend.AudioCDURL
    from .gui import ImportAudioCDAction
    editor.EditorTreeView.actionConfig.addActionDefinition((("plugins", 'audiocd'),), ImportAudioCDAction)

def disable():
    filebackends.urlTypes["audiocd"]

def findDrives():
    output = subprocess.check_output("cd-drive")
    drives = []
    for line in output.decode().splitlines():
        if line.startswith("                       Drive: "):
            drives.append(line[30:])
    return drives

