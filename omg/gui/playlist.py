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

from . import treeview, mainwindow
from .. import logging, player
from ..constants import PLAYLIST

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger("gui.playlist")

class PlaylistTreeView(treeview.TreeView):
    """This is the main widget of a playlist: The tree view showing the current element tree."""
    level = PLAYLIST
    
    def __init__(self, parent = None):
        treeview.TreeView.__init__(self, parent)
        
class PlaylistWidget(QtGui.QDockWidget):
    
    def __init__(self, parent = None, state = None, location = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('playlist'))
        self.backendChooser = player.BackendChooser(self)
        self.backendChooser.backendChanged.connect(lambda b: print('backend changed: {}'.format(b)))
data = mainwindow.WidgetData(id = "playlist",
                             name = translate("Playlist","playlist"),
                             theClass = PlaylistWidget,
                             central = True,
                             dock = True,
                             default = True,
                             unique = False,
                             preferredDockArea = Qt.RightDockWidgetArea)
mainwindow.addWidgetData(data)