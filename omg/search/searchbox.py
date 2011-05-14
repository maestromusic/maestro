# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import searchparser

class SearchBox(QtGui.QLineEdit):
    criteriaChanged = QtCore.pyqtSignal()

    def __init__(self,parent=None):
        QtGui.QLineEdit.__init__(self,parent)
        self.instant = True
        self._criteria = []

    def getCriteria(self):
        return self._criteria

    def getInstantSearch(self):
        return self.instant

    def setInstantSearch(self,instant):
        self.instant = instant

    def keyPressEvent(self,event):
        QtGui.QLineEdit.keyPressEvent(self,event)
        if self.instant or event.key() in (Qt.Key_Return,Qt.Key_Enter):
            criteria = searchparser.parseSearchString(self.text())
            if criteria != self._criteria:
                self._criteria = criteria
                self.criteriaChanged.emit()
