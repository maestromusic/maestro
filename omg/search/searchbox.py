# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
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
