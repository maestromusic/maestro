# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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
from PyQt4.QtCore import Qt

from . import abstractdelegate, StandardDelegate, profiles
from ...core import covers

translate = QtCore.QCoreApplication.translate


profileType = profiles.createProfileType(
                name      = 'playlist',
                title     = translate("Delegates","Playlist"),
                leftData  = ['t:composer','t:artist','t:performer'],
                rightData = ['t:date','t:genre','t:conductor'],
                overwrite = {"fitInTitleRowData": profiles.DataPiece("filecount+length"),
                             "showMajorAncestors": True
                            }
)


class PlaylistDelegate(StandardDelegate):
    """Delegate for the playlist."""
    def __init__(self,view,profile):
        super().__init__(view,profile)
        # Don't worry, addCacheSize won't add sizes twice
        covers.addCacheSize(self.profile.options['coverSize'])
    
    def getPreTitleItem(self,wrapper):
        if wrapper in self.model.currentlyPlayingNodes:
            return abstractdelegate.PlayTriangleItem(QtGui.QColor(20,200,20),9)
        else: return None
    
    def _handleProfileChanged(self,profile):
        """React to the configuration dispatcher."""
        if profile == self.profile:
            covers.addCacheSize(profile.options['coverSize'])
    