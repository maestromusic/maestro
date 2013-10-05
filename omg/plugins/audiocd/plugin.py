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


from PyQt4 import QtCore, QtGui
from omg import filebackends
from omg.gui import editor
from omg import config


def defaultConfig():
    return {"audiocd": {
            "rippath":  (str, "ripped", "Default path in which ripped tracks are put."),
            "earlyrip": (bool, True, "Start ripping before the MusicBrainz dialog is opened."),
        }}


def enable():
    from . import filebackend as cdfilebackend
    filebackends.urlTypes["audiocd"] = cdfilebackend.AudioCDURL
    from .gui import ImportAudioCDAction
    editor.EditorTreeView.actionConfig.addActionDefinition((("plugins", 'audiocd'),), ImportAudioCDAction)
    from omg.core.levels import real
    from .ripper import fileChangerHook
    real.commitHooks.append(fileChangerHook)

def disable():
    del filebackends.urlTypes["audiocd"]
    editor.EditorTreeView.actionConfig.removeActionDefinition( (("plugins", "audiocd"),) )
    from omg.core.levels import real
    from .ripper import fileChangerHook
    real.commitHooks.remove(fileChangerHook)

def simpleDiscContainer(discid, trackCount, level):
    from omg.core.elements import TYPE_ALBUM
    
    elems = []
    for i in range(1, trackCount+1):
        url = filebackends.BackendURL.fromString("audiocd://{0}.{1}/{2}/{0}/{1}.flac".format(
                        discid, i, config.options.audiocd.rippath))
        elems.append(level.collect(url))
    return level.createContainer(contents=elems, type=TYPE_ALBUM)
    

        