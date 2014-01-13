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

from .. import utils, logging
from ..search import criteria
from .misc.lineedits import IconLineEdit

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


class CriterionLineEdit(IconLineEdit):
    criterionChanged = QtCore.pyqtSignal(criteria.Criterion)
    criterionCleared = QtCore.pyqtSignal()
    
    def __init__(self, criterion):
        super().__init__(utils.getIcon("clear.png"))
        self.button.clicked.connect(self.clear)
        self.button.clicked.connect(self._handleChange)
        if criterion is not None:
            self.setText(repr(criterion))
        self.criterion = criterion
        self.returnPressed.connect(self._handleChange)
        
    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._handleChange()
        
    def _handleChange(self):
        text = self.text().strip()
        try:
            if len(text) == 0:
                criterion = None
            else: criterion = criteria.parse(text)
        except criteria.ParseException:
            self.setStyleSheet("QLineEdit { background-color : #FF7094 }")
        else:
            self.setStyleSheet('')
            if criterion != self.criterion:
                self.criterion = criterion
                if criterion is not None:
                    self.criterionChanged.emit(criterion)
                else: self.criterionCleared.emit()


class FlagView(QtGui.QTableWidget):
    selectionChanged = QtCore.pyqtSignal(list)
    
    def __init__(self, selectedFlagTypes, parent=None):
        QtGui.QTableWidget.__init__(self, parent)
        self.verticalHeader().hide()
        self.horizontalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(self.verticalHeader().fontMetrics().height() + 2)
        self.itemChanged.connect(self._handleItemChanged)
        self.setShowGrid(False)
        
        self.selectedFlagTypes = list(selectedFlagTypes)
        self._loadFlags()
        
    def _loadFlags(self):
        self.clear()
        flagList = sorted(flags.allFlags(), key=lambda f: f.name)
        
        if len(flagList):
            self.setColumnCount(2)
            import math
            rowCount = math.ceil(len(flagList)/2)
            self.setRowCount(rowCount)
        else:
            self.setColumnCount(1)
            rowCount = len(flagList)
            self.setRowCount(len(flagList))
    
        for row,flagType in enumerate(flagList):
            column = 1 if row >= rowCount else 0
            
            item = QtGui.QTableWidgetItem()
            item.setText(flagType.name)
            item.setData(Qt.UserRole, flagType)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if flagType in self.selectedFlagTypes else Qt.Unchecked)
            if flagType.icon is not None:
                item.setIcon(flagType.icon)
            self.setItem(row % rowCount,column,item)
        
        self.resizeColumnsToContents()
    
    def selectFlagType(self,flagType):
        if flagType not in self.selectedFlagTypes: 
            self.selectedFlagTypes.append(flagType)
            item = self.findItem(flagType)
            if item is not None: # should always be true
                item.setCheckState(Qt.Checked)
            # Copy the list so that external code doesn't use the internal list
            self.selectionChanged.emit(list(self.selectedFlagTypes))
    
    def unselectFlagType(self,flagType):
        if flagType in self.selectedFlagTypes:
            self.selectedFlagTypes.remove(flagType)
            item = self.findItem(flagType)
            if item is not None: # should always be true
                item.setCheckState(Qt.Unchecked)
            self.selectionChanged.emit(list(self.selectedFlagTypes))
                
    def _handleItemChanged(self,item):
        flagType = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            self.selectFlagType(flagType)
        elif item.checkState() == Qt.Unchecked:
            self.unselectFlagType(flagType)
        
    def findItem(self,flagType):
        for row in range(self.rowCount()):
            for column in range(self.columnCount()):
                item = self.item(row,column)
                if item is not None and item.data(Qt.UserRole) == flagType:
                    return item
        return None
