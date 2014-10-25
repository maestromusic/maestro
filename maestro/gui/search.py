# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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
from ..core import flags
from ..search import criteria
from .misc.lineedits import IconLineEdit


class SearchBox(IconLineEdit):
    """This is a lineedit that will parse the given text as a search criterion and will emit criterionChanged
    whenever a new valid criterion is entered. If the attribute 'instant' is set to False, the signal
    will only be emitted when the user hits return/enter."""
    criterionChanged = QtCore.pyqtSignal()

    def __init__(self, text=''):
        super().__init__(utils.getIcon("clear.png"))
        self.setText(text)
        self.button.clicked.connect(self._handleButton)
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

    def _handleButton(self):
        self.clear()
        if not self.instant: # otherwise it happened already in _handleTextChanged
            self._updateCriterion()
            
    def _handleTextChanged(self, text):
        if self.instant:
            self._updateCriterion()
            
    def _updateCriterion(self):
        """Parse the criterion and emit criterionChanged if appropriate."""
        try:
            criterion = criteria.parse(self.text())
        except criteria.ParseException as e:
            # No logger message as this appears normally while a long query is entered.
            return
        if criterion != self._criterion:
            self._criterion = criterion
            self.criterionChanged.emit()
                
    def keyPressEvent(self, event):
        QtGui.QLineEdit.keyPressEvent(self, event)
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            try:
                criterion = criteria.parse(self.text())
            except criteria.ParseException as e:
                logging.info(__name__, str(e))
                return
            if criterion != self._criterion:
                self._criterion = criterion
                self.criterionChanged.emit()
            
    def focusOutEvent(self, event):
        self._updateCriterion()
        super().focusOutEvent(event)


class CriterionLineEdit(IconLineEdit):
    """Special LineEdit to enter search strings. When the focus leaves the box or Enter is pressed, it will
    check the syntax of the string (see search.criteria.parse) and emit criterionChanged with the given
    criterion or criterionCleared if the criterion is None.
    
    The optional parameter *criterion* may be either a Criterion-instance or a string and will be used to
    fill the box at the beginning.
    """
    criterionChanged = QtCore.pyqtSignal(criteria.Criterion)
    criterionCleared = QtCore.pyqtSignal()
    
    def __init__(self, criterion=None):
        super().__init__(utils.getIcon("clear.png"))
        self.button.clicked.connect(self.clear)
        self.button.clicked.connect(self._handleChange)
        self._criterion = None
        if isinstance(criterion, criteria.Criterion):
            self.setText(repr(criterion))
            self._criterion = criterion
        elif isinstance(criterion, str):
            self.setText(criterion)
            self._handleChange()
        elif criterion is not None:
            raise TypeError("criterion must be either a Criterion-instance or a string.")
        self.returnPressed.connect(self._handleChange)
    
    def getCriterion(self):
        """Return the current criterion if it is valid or the last valid criterion from the box."""
        return self._criterion
    
    def setCriterion(self, criterion):
        """Set the criterion in the box. *criterion* may be None."""
        if criterion is not None:
            self.setText(repr(criterion))
        else: self.setText('')
        
    def isValid(self):
        """Return whether the text in the box can be parsed to a criterion."""
        text = self.text().strip()
        if len(self.text()) == 0:
            return True
        try:
            criterion = criteria.parse(text)
            return True
        except criteria.ParseException:
            return False
        
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
            if criterion != self._criterion:
                self._criterion = criterion
                if criterion is not None:
                    self.criterionChanged.emit(criterion)
                else: self.criterionCleared.emit()


class FlagView(QtGui.QTableWidget):
    """A QTableWidget containing entries for all flags. Whenever the selection changes, selectionChanged is
    emitted. Flags given in *selectedFlagTypes* are selected at the beginnning.
    """
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
        """Fill the table with all flags from the database."""
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
    
        for row, flagType in enumerate(flagList):
            column = 1 if row >= rowCount else 0
            
            item = QtGui.QTableWidgetItem()
            item.setText(flagType.name)
            item.setData(Qt.UserRole, flagType)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if flagType in self.selectedFlagTypes else Qt.Unchecked)
            if flagType.icon is not None:
                item.setIcon(flagType.icon)
            self.setItem(row % rowCount, column, item)
        
        self.resizeColumnsToContents()
    
    def selectFlagType(self, flagType):
        """Select the given flag."""
        if flagType not in self.selectedFlagTypes: 
            self.selectedFlagTypes.append(flagType)
            item = self.findItem(flagType)
            if item is not None: # should always be true
                item.setCheckState(Qt.Checked)
            # Copy the list so that external code doesn't use the internal list
            self.selectionChanged.emit(list(self.selectedFlagTypes))
    
    def unselectFlagType(self, flagType):
        """Unselect the given flag."""
        if flagType in self.selectedFlagTypes:
            self.selectedFlagTypes.remove(flagType)
            item = self.findItem(flagType)
            if item is not None: # should always be true
                item.setCheckState(Qt.Unchecked)
            self.selectionChanged.emit(list(self.selectedFlagTypes))
                
    def _handleItemChanged(self, item):
        flagType = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            self.selectFlagType(flagType)
        elif item.checkState() == Qt.Unchecked:
            self.unselectFlagType(flagType)
        
    def findItem(self, flagType):
        """Return the item for the given flag (or None)."""
        for row in range(self.rowCount()):
            for column in range(self.columnCount()):
                item = self.item(row, column)
                if item is not None and item.data(Qt.UserRole) == flagType:
                    return item
        return None
