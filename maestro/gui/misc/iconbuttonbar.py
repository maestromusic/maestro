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

from PyQt5 import QtCore,QtGui
from PyQt5.QtCore import Qt

 
class IconButtonBar(QtWidgets.QWidget):
    def __init__(self,parent = None):
        QtWidgets.QWidget.__init__(self,parent)
        self.setSizePolicy(
                QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding,QtWidgets.QSizePolicy.MinimumExpanding))
        self.setLayout(QtWidgets.QHBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)
        self.layout().setSpacing(0)
        self.layout().addStretch(1)
        
    def addIcon(self,icon,slot = None,toolTip = None):
        button = QtWidgets.QToolButton()
        button.setContentsMargins(0,0,0,0)
        button.setIcon(icon)
        if slot is not None:
            button.clicked.connect(slot)
        if toolTip is not None:
            button.setToolTip(toolTip)
        self.layout().insertWidget(self.layout().count()-1,button,0)