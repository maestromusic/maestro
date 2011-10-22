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

from .. import utils
from . import searchparser
from ..gui.misc.iconlineedit import IconLineEdit

class SearchBox(IconLineEdit):
    criteriaChanged = QtCore.pyqtSignal()

    def __init__(self,parent=None):
        IconLineEdit.__init__(self,utils.getIcon("clear.png"),parent)
        self.button.clicked.connect(self.clear)
        self.textChanged.connect(self._handleTextChanged)
        self.instant = True
        self._criteria = []

    def getCriteria(self):
        return self._criteria

    def getInstantSearch(self):
        return self.instant

    def setInstantSearch(self,instant):
        self.instant = instant

    def _handleTextChanged(self,text):
        if self.instant:
            criteria = searchparser.parseSearchString(text)
            if criteria != self._criteria:
                self._criteria = criteria
                self.criteriaChanged.emit()
                
    def keyPressEvent(self,event):
        QtGui.QLineEdit.keyPressEvent(self,event)
        if event.key() in (Qt.Key_Return,Qt.Key_Enter):
            criteria = searchparser.parseSearchString(self.text())
            if criteria != self._criteria:
                self._criteria = criteria
                self.criteriaChanged.emit()
