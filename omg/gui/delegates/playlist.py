# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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

from ... import tags, config, models
from . import StandardDelegate, configuration, abstractdelegate

translate = QtCore.QCoreApplication.translate


class PlaylistDelegate(StandardDelegate):
    """Delegate for the playlist."""
    
    configurationType, defaultConfiguration = configuration.createConfigType(
                'playlist',
                translate("Delegates","Playlist"),
                StandardDelegate.options,
                ['t:composer','t:artist','t:performer'],
                ['t:date','t:genre','t:conductor'],
                {"fitInTitleRowData": configuration.DataPiece("filecount+length")}
    )
    def layout(self, index, availableWidth):
        if index == self.model.currentModelIndex or index in self.model.currentParentsModelIndices:
            self.addCenter(abstractdelegate.PlayTriangleItem(QtGui.QColor(20,200,20),9))
        super().layout(index, availableWidth)
    