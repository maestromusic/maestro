# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

from . import criteria
from .. import utils, logging
from ..gui.misc.lineedits import IconLineEdit

logger = logging.getLogger(__name__)


class SearchBox(IconLineEdit):
    """This is a lineedit that will parse the given text as a search criterion and will emit criterionChanged
    whenever a new valid criterion is entered. If the attribute 'instant' is set to False, the signal
    will only be emitted when the user hits return/enter."""
    criterionChanged = QtCore.pyqtSignal()

    def __init__(self, text=''):
        super().__init__(utils.getIcon("clear.png"))
        self.setText(text)
        self.button.clicked.connect(self.clear)
        self.textChanged.connect(self._handleTextChanged)
        self.instant = True
        self._criterion = None

    @property
    def criterion(self):
        return self._criterion
    
    def setInstantSearch(self, instant):
        """Set the attribute 'instant'. This is a convenience method to be connected to e.g. the
        toggled-signal of checkboxes."""
        self.instant = instant

    def _handleTextChanged(self, text):
        if self.instant:
            try:
                criterion = criteria.parse(self.text())
            except criteria.ParseException as e:
                # No logger message as this appears normally while a long query is entered.
                return
            if criterion != self._criterion:
                self._criterion = criterion
                self.criterionChanged.emit()
                
    def keyPressEvent(self,event):
        QtGui.QLineEdit.keyPressEvent(self, event)
        if event.key() in (Qt.Key_Return,Qt.Key_Enter):
            try:
                criterion = criteria.parse(self.text())
            except criteria.ParseException as e:
                logger.info(str(e))
                return
            if criterion != self._criterion:
                self._criterion = criterion
                self.criterionChanged.emit()
