# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2013-2014 Martin Altmayer, Michael Helmling
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

try:
    import discid
except ImportError:
    raise ImportError('discid module not installed')
from PyQt4 import QtCore, QtGui
from omg import application, database as db, filebackends
from omg.gui import editor
from omg import config
from omg.core import domains

translate = QtCore.QCoreApplication.translate

def defaultConfig():
    return {"audiocd": {
            "rippath":  (str, "/tmp", "Default path in which ripped tracks are put."),
            "earlyrip": (bool, True, "Start ripping before the MusicBrainz dialog is opened."),
            'eject':    (bool, True, 'Eject CD after ripping is completed or aborted'),
        }}


def enable():
    from . import filebackend as cdfilebackend
    filebackends.urlTypes["audiocd"] = cdfilebackend.AudioCDURL
    from .gui import ImportAudioCDAction
    editor.EditorTreeView.actionConfig.addActionDefinition((("plugins", 'audiocd'),), ImportAudioCDAction)
    from omg.core.levels import real
    from .ripper import fileChangerHook
    real.commitHooks.append(fileChangerHook)

def mainWindowInit():
    global _action
    _action = QtGui.QAction(application.mainWindow)
    _action.setText(translate("AudioCD Plugin", "rip missing tracks..."))
    _action.triggered.connect(showRipMissingDialog)
    application.mainWindow.menus['extras'].addAction(_action)
    
def disable():
    del filebackends.urlTypes["audiocd"]
    editor.EditorTreeView.actionConfig.removeActionDefinition( (("plugins", "audiocd"),) )
    from omg.core.levels import real
    from .ripper import fileChangerHook
    real.commitHooks.remove(fileChangerHook)
    application.mainWindow.menus['extras'].removeAction(_action)

def simpleDiscContainer(discid, trackCount, level):
    from omg.core.elements import TYPE_ALBUM
    
    elems = []
    for i in range(1, trackCount+1):
        url = filebackends.BackendURL.fromString("audiocd://{0}.{1}/{2}/{0}/{1}.flac".format(
                        discid, i, config.options.audiocd.rippath))
        elems.append(level.collect(url))
    return level.createContainer(contents=elems, type=TYPE_ALBUM)
    

def showRipMissingDialog():
    ans = list(db.query("SELECT url, element_id FROM {p}files WHERE url LIKE 'audiocd://%'"))
    from omg.gui.dialogs import warning
    if len(ans) == 0:    
        warning(translate("AudioCD Plugin", "no unripped tracks"),
                translate("AudioCD Plugin", "Your database does not contain any unripped audio-cd tracks!"))
        return
    discids = {}
    for url, id in ans:
        url = filebackends.BackendURL.fromString(url)
        if url.discid not in discids:
            discids[url.discid] = (id, set())
        assert url.tracknr not in discids[url.discid][1]
        discids[url.discid][1].add(url.tracknr)
    from . import gui
    dev, discid, ntracks = gui.ImportAudioCDAction.askForDiscId()
    if discid in discids:
        id, tracks = discids[discid]
        assert set(range(min(tracks), max(tracks)+1)) == tracks
        from . import ripper
        rppr = ripper.Ripper(dev, discid, fromTrack=min(tracks), toTrack=max(tracks))
        rppr.start()
        warning(translate("AudioCD Plugin", "unripped tracks found"),
                translate("AudioCD Plugin", "The disc in the selected drive contains {} tracks "
                          "that are marked as un-ripped in the database. Ripping started ...")
                .format(len(tracks)))
    
        
    