# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2013-2015 Martin Altmayer, Michael Helmling
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
from maestro import application, database as db
from maestro.gui import editor
from maestro.core import urls, tags

translate = QtCore.QCoreApplication.translate


def defaultConfig():
    return {"audiocd": {
            "rippath":  (str, "/tmp", "Default path in which ripped tracks are put."),
            "earlyrip": (bool, True, "Start ripping before the MusicBrainz dialog is opened."),
            'eject':    (bool, True, 'Eject CD after ripping is completed or aborted'),
        }}


def enable():
    urls.fileBackends.append(AudioCDTrack)
    from .gui import ImportAudioCDAction
    ImportAudioCDAction.register('importAudioCD', context='plugins',
                                 description=translate('ImportAudioCDAction', 'Open CD ripping dialog'))
    editor.EditorTreeView.addActionDefinition('importAudioCD')
    from maestro.core.levels import real
    from .ripper import fileChangerHook
    real.commitHooks.append(fileChangerHook)


def mainWindowInit():
    global _action
    _action = QtGui.QAction(application.mainWindow)
    _action.setText(translate("AudioCD Plugin", "rip missing tracks..."))
    _action.triggered.connect(showRipMissingDialog)
    application.mainWindow.menus['extras'].addAction(_action)


def disable():
    urls.fileBackends.remove(AudioCDTrack)
    from maestro.gui import actions
    actions.manager.unregisterAction('importAudioCD')
    from maestro.core.levels import real
    from .ripper import fileChangerHook
    real.commitHooks.remove(fileChangerHook)
    application.mainWindow.menus['extras'].removeAction(_action)


def parseNetloc(url: urls.URL):
    """Parse the netloc of an audiocd:// url into the disc id and track number, returned as tuple."""
    a, b = url.netloc.rsplit('.', 1)
    return a, int(b)


class AudioCDTrack(urls.BackendFile):

    scheme = 'audiocd'

    def readTags(self):
        self.tags, self.length = tags.Storage(), 0

    def saveTags(self):
        pass

    def rename(self, newpath: str):
        self.url = self.url.copy(path=newpath)


def showRipMissingDialog():
    ans = list(db.query("SELECT url, element_id FROM {p}files WHERE url LIKE 'audiocd://%'"))
    from ...gui.dialogs import warning
    if len(ans) == 0:    
        warning(translate("AudioCD Plugin", "no unripped tracks"),
                translate("AudioCD Plugin", "Your database does not contain any unripped audio-cd tracks!"))
        return
    discids = {}
    for url, id in ans:
        url = urls.URL(url)
        discid, tracknr = parseNetloc(url)
        if discid not in discids:
            discids[discid] = (id, set())
        assert tracknr not in discids[discid][1]
        discids[discid][1].add(tracknr)
    from . import gui

    ans = gui.ImportAudioCDAction.askForDiscId()
    if not ans:
        return
    dev, discid, ntracks = ans
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
    
        
    