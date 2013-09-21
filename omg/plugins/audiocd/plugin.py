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
import os, shutil
import subprocess

from PyQt4 import QtCore, QtGui
from omg import filebackends, utils
from omg.gui import editor

translate = QtCore.QCoreApplication.translate

def defaultConfig():
    return {"audiocd": {
            "rippath": (str, "ripped", "Default path in which ripped tracks are put.")
        }}

fileReplacer = None
def enable():
    global fileReplacer
    from . import filebackend as cdfilebackend
    filebackends.urlTypes["audiocd"] = cdfilebackend.AudioCDURL
    from .gui import ImportAudioCDAction
    editor.EditorTreeView.actionConfig.addActionDefinition((("plugins", 'audiocd'),), ImportAudioCDAction)
    fileReplacer = FileReplacer()

def disable():
    filebackends.urlTypes["audiocd"]

def findDrives():
    output = subprocess.check_output("cd-drive")
    drives = []
    for line in output.decode().splitlines():
        if line.startswith("                       Drive: "):
            drives.append(line[30:])
    return drives

class InsertRippedFileCommand:
    
    def __init__(self, element, tmpPath, level):
        self.element = element
        self.tmpPath = tmpPath
        self.level = level
        self.text = translate("AudioCD Plugin", "Ripped Track {}".format(element.url.tracknr))
        
    def redo(self):
        from omg.filebackends.filesystem import RealFile, FileURL
        from omg.core import tags
        from collections import OrderedDict
        targetAbs = utils.absPath(self.element.url.targetPath)
        if not os.path.exists(os.path.dirname(targetAbs)):
            os.makedirs(os.path.dirname(targetAbs))
        shutil.move(self.tmpPath, targetAbs)
        newUrl = FileURL('file:///' + self.element.url.targetPath)
        tmpFile = RealFile(newUrl)
        tmpFile.readTags()
        tmpFile.tags = self.element.tags.withoutPrivateTags(copy=True)
        tmpFile.specialTags = {"tracknumber" : "{:02d}".format(self.element.url.tracknr)}
        tmpFile.saveTags()
        self.element.url = newUrl
        self.level.emitEvent(dataIds=[self.element.id])
        
    def undo(self):
        shutil.move(self.newPath, self.oldPath)

class FileReplacer(QtCore.QObject):
    
    @QtCore.pyqtSlot(str, int, str)
    def replaceFile(self, discid, tracknr, path):
        from . import filebackend as cdfilebackend
        print('FILE REPLACER')
        print(discid, tracknr, path)
        from omg.core import levels
        for element in levels.editor.elements.values():
            if not element.isFile():
                continue
            if not isinstance(element.url, cdfilebackend.AudioCDURL):
                continue
            print(element.url)
            if element.url.discid == discid:
                print('found discid')
                print(element.url.tracknr)
                if element.url.tracknr == tracknr:
                    print('found file: {}'.format(element))
                    levels.editor.stack.push(InsertRippedFileCommand(element, path, levels.editor))
            else:
                print('wrong discid: {}!= {}'.format(discid, element.url.discid))
        