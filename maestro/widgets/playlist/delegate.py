# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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

from PyQt5 import QtCore, QtGui

from maestro.gui.delegates import abstractdelegate, StandardDelegate, profiles
from maestro.core import covers

translate = QtCore.QCoreApplication.translate


def init():
    PlaylistDelegate.profileType = profiles.createProfileType(
        name='playlist',
        title=translate('Delegates', 'Playlist'),
        leftData=['t:composer', 't:artist', 't:performer'],
        rightData=['t:date', 't:genre', 't:conductor'],
        overwrite=dict(fitInTitleRowData=profiles.DataPiece('filecount+length'),
                       showMajorAncestors=True)
    )


class PlaylistDelegate(StandardDelegate):
    """Delegate for the playlist."""
    
    def __init__(self, view, profile):
        super().__init__(view, profile)
        # Don't worry, addCacheSize won't add sizes twice
        covers.addCacheSize(self.profile.options['coverSize'])
    
    def getPreTitleItem(self, wrapper):
        if self.model is not None and wrapper in self.model.currentlyPlayingNodes:
            return abstractdelegate.PlayTriangleItem(QtGui.QColor(20, 200, 20), 9)
        else:
            return None
    
    def _handleProfileChanged(self, profile):
        """React to the configuration dispatcher."""
        super()._handleProfileChanged(profile)
        if profile == self.profile:
            covers.addCacheSize(profile.options['coverSize'])
