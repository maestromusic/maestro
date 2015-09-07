# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2015 Martin Altmayer, Michael Helmling
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

from PyQt5 import QtCore
translate = QtCore.QCoreApplication.translate


def init():
    from maestro.widgets.playlist import gui as pgui
    from maestro.widgets import WidgetClass
    from maestro import utils
    WidgetClass(
        id='playlist', theClass=pgui.PlaylistWidget, name=translate('Playlist', 'Playlist'),
        icon=utils.images.icon('view-media-playlist'),

    ).register()
    pgui.RemoveFromPlaylistAction.register(
        'removeFromPL', context='playback',
        shortcut=translate('RemoveFromPlaylistAction', 'Del')
    )
    pgui.ClearPlaylistAction.register(
        'clearPL', context='playback',
        shortcut=translate('ClearPlaylistAction', 'Shift+Del')
    )
    for definition in 'editTags', 'removeFromPL', 'clearPL':
        pgui.PlaylistTreeView.addActionDefinition(definition)