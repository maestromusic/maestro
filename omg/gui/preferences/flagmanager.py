# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
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

import functools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ... import application, database as db, utils, stack
from ...core import flags
from .. import misc, dialogs
from ..misc import iconbuttonbar

translate = QtCore.QCoreApplication.translate


class FlagManager(QtGui.QWidget):
    """The FlagManager allows to add, edit and delete flagtypes."""
    def __init__(self, dialog, panel):
        super().__init__(panel)
        self.setLayout(QtGui.QVBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)
        self.layout().setSpacing(0)
        
        buttonBar = QtGui.QToolBar()
        self.layout().addWidget(buttonBar)
                
        addButton = QtGui.QToolButton()
        addButton.setIcon(utils.getIcon("add.png"))
        addButton.setToolTip("Add flag...")
        addButton.clicked.connect(self._handleAddButton)
        buttonBar.addWidget(addButton)
        self.undoButton = QtGui.QToolButton()
        self.undoButton.setIcon(utils.getIcon("undo.png"))
        self.undoButton.clicked.connect(stack.undo)
        buttonBar.addWidget(self.undoButton)
        self.redoButton = QtGui.QToolButton()
        self.redoButton.setIcon(utils.getIcon("redo.png"))
        self.redoButton.clicked.connect(stack.redo)
        buttonBar.addWidget(self.redoButton)
        self.showInBrowserButton = QtGui.QToolButton()
        self.showInBrowserButton.setIcon(utils.getIcon("preferences/goto.png"))
        self.showInBrowserButton.setToolTip(self.tr("Show in browser"))
        self.showInBrowserButton.setEnabled(False)
        self.showInBrowserButton.clicked.connect(self._handleShowInBrowserButton)
        buttonBar.addWidget(self.showInBrowserButton)
        self.deleteButton = QtGui.QToolButton()
        self.deleteButton.setIcon(utils.getIcon("delete.png"))
        self.deleteButton.setToolTip(self.tr("Delete flag"))
        self.deleteButton.setEnabled(False)
        self.deleteButton.clicked.connect(self._handleDeleteButton)
        buttonBar.addWidget(self.deleteButton)
        
        self.columns = [
                ("icon",   self.tr("Icon")),
                ("name",   self.tr("Name")),
                ("number", self.tr("# of elements"))
                ]
        
        self.tableWidget = QtGui.QTableWidget()
        self.tableWidget.setColumnCount(len(self.columns))
        self.tableWidget.verticalHeader().hide()
        self.tableWidget.setSortingEnabled(True)
        self.tableWidget.horizontalHeader().setResizeMode(QtGui.QHeaderView.ResizeToContents)
        self.tableWidget.itemChanged.connect(self._handleItemChanged)
        self.tableWidget.cellDoubleClicked.connect(self._handleCellDoubleClicked)
        self.tableWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tableWidget.customContextMenuRequested.connect(self._handleCustomContextMenuRequested)
        self.tableWidget.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.tableWidget.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.tableWidget.itemSelectionChanged.connect(self._handleSelectionChanged)
        self.layout().addWidget(self.tableWidget)
        self._loadFlags()
        
        self._checkUndoRedoButtons()
        stack.indexChanged.connect(self._checkUndoRedoButtons)
        stack.undoTextChanged.connect(self._checkUndoRedoButtons)
        stack.redoTextChanged.connect(self._checkUndoRedoButtons)
        application.dispatcher.connect(self._handleDispatcher)
        
    def _handleDispatcher(self, event):
        """React to FlagTypeChangeEvents from the dispatcher."""
        if isinstance(event, flags.FlagTypeChangeEvent):
            self._loadFlags()
            
    def _loadFlags(self):
        """Load flags information from flags-module to GUI."""
        self._flagTypes = sorted(flags.allFlags(), key=lambda f: f.name)
        self.tableWidget.clear()
        self.tableWidget.setHorizontalHeaderLabels([column[1] for column in self.columns])
        self.tableWidget.setRowCount(len(self._flagTypes))
        
        NumericSortItem = misc.createSortingTableWidgetClass('NumericSortItem', misc.leadingInt)
        
        for row, flagType in enumerate(self._flagTypes):
            column = self._getColumnIndex("icon")
            label = QtGui.QLabel()       
            label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            index = self.tableWidget.model().index(row, column)   
            self.tableWidget.setIndexWidget(index, label)
            if flagType.iconPath is not None:
                label.setPixmap(QtGui.QPixmap(flagType.iconPath))
                label.setToolTip(flagType.iconPath)           
            
            column = self._getColumnIndex("name")
            item = QtGui.QTableWidgetItem(flagType.name)
            item.setFlags(Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tableWidget.setItem(row, column, item)
            
            column = self._getColumnIndex("number")
            item = NumericSortItem('{}    '.format(self._getElementCount(flagType)))
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tableWidget.setItem(row, column, item)
            
        self.tableWidget.resizeColumnsToContents()
    
    def _getElementCount(self, flagType):
        """Return the number of elements having the given flag."""
        return db.query("SELECT COUNT(*) FROM {p}flags WHERE flag_id = ?", flagType.id).getSingle()
                        
    def _handleAddButton(self):
        """Create a new flag (querying the user for the flag's name)."""
        createNewFlagType(self) # FlagManager will be reloaded via the dispatcher event
    
    def _handleShowInBrowserButton(self):
        """Load all elements containing the selected flag into the default browser."""
        from .. import browser
        rows = self.tableWidget.selectionModel().selectedRows()
        if len(rows) == 1 and browser.defaultBrowser is not None:
            flag = self._flagTypes[rows[0].row()]
            browser.defaultBrowser.search('{flag='+flag.name+'}')
            
    def _handleDeleteButton(self):
        """Ask the user if he really wants this and if so, delete the flag."""
        rows = self.tableWidget.selectionModel().selectedRows()
        if len(rows) == 1:
            flagType = self._flagTypes[rows[0].row()]
            number = self._getElementCount(flagType)
            if number > 0:
                question = self.tr("Do you really want to delete the flag '{}'? "
                                   "It will be deleted from %n element(s).", None, number)
            flags.deleteFlagType(flagType)

    def _handleItemChanged(self, item):
        """When the name of a flag has been changed, ask the user if he really wants this and if so perform
        the change in the database and reload."""
        if item.column() != self._getColumnIndex("name"): # Only the name column is editable
            return
        flagType = self._flagTypes[item.row()]
        oldName = flagType.name
        newName = item.text()
        if oldName == newName:
            return
        
        if not flags.isValidFlagname(newName):
            QtGui.QMessageBox(self, self.tr("Cannot change flag"),
                              self.tr("'{}' is not a valid flagname.").format(newName))
            item.setText(oldName)
            return
        
        if flags.exists(newName):
            QtGui.QMessageBox.warning(self, self.tr("Cannot change flag"),
                                      self.tr("A flag named '{}' does already exist.").format(newName))
            item.setText(oldName)
            return
                      
        number = self._getElementCount(flagType)          
        if number > 0:
            question = self.tr("Do you really want to change the flag '{}'?"
                               " It will be changed in %n element(s).",
                               None, number).format(oldName)
            if (QtGui.QMessageBox.question(self, self.tr("Change flag?"), question,
                                   QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
                                   QtGui.QMessageBox.Yes)
                        != QtGui.QMessageBox.Yes):
                item.setText(oldName)
                return
        flags.changeFlagType(flagType, name=newName)
    
    def _checkUndoRedoButtons(self):
        """Enable or disable the undo and redo buttons depending on stack state."""
        self.undoButton.setEnabled(stack.canUndo())
        self.undoButton.setToolTip(self.tr("Undo: {}").format(stack.undoText()))
        self.redoButton.setEnabled(stack.canRedo())
        self.redoButton.setToolTip(self.tr("Redo: {}").format(stack.redoText()))
        
    def _handleSelectionChanged(self):
        rows = self.tableWidget.selectionModel().selectedRows()
        from .. import browser
        self.showInBrowserButton.setEnabled(len(rows) == 1 and browser.defaultBrowser is not None)
        self.deleteButton.setEnabled(len(rows) == 1)
        
    def _handleCellDoubleClicked(self, row, column):
        """Handle double clicks on the first column containing icons. A click will open a file dialog to
        change the icon."""
        if column == 0:
            flagType = self._flagTypes[row]
            self._openIconDialog(flagType)
    
    def _handleCustomContextMenuRequested(self, pos):
        """React to customContextMenuRequested signals."""
        row = self.tableWidget.rowAt(pos.y())
        column = self.tableWidget.columnAt(pos.x())
        if column == 0 and row != -1:
            flagType = self._flagTypes[row]
            menu = QtGui.QMenu(self.tableWidget)
            if flagType.iconPath is None:
                changeAction = QtGui.QAction(self.tr("Add icon..."), menu)
            else: changeAction = QtGui.QAction(self.tr("Change icon..."), menu)
            changeAction.triggered.connect(lambda: self._openIconDialog(flagType))
            menu.addAction(changeAction)
            removeAction = QtGui.QAction(self.tr("Remove icon"), menu)
            removeAction.setEnabled(flagType.iconPath is not None)
            removeAction.triggered.connect(lambda: self._setIcon(flagType, None))
            menu.addAction(removeAction)
            menu.exec_(self.tableWidget.viewport().mapToGlobal(pos))
    
    def _openIconDialog(self, flagType):
        """Open a file dialog so that the user may choose an icon for the given flag."""
        # Choose a sensible directory as starting point
        from ..misc import iconchooser
        result = iconchooser.IconChooser.getIcon([':omg/flags', ':omg/tags'], flagType.iconPath, self)
        
        if result and result[1] != flagType.iconPath:
            self._setIcon(flagType, result[1])
            
    def _setIcon(self, flagType, iconPath):
        """Set the icon(-path) of *flagType* to *iconPath* and update the GUI.""" 
        flags.changeFlagType(flagType, iconPath=iconPath)
        # Update the widget
        row = self._flagTypes.index(flagType)
        index = self.tableWidget.model().index(row, 0)                     
        label = self.tableWidget.indexWidget(index)
        # Both works also if iconPath is None
        label.setPixmap(QtGui.QPixmap(flagType.iconPath))
        label.setToolTip(flagType.iconPath)
        
    def _getColumnIndex(self, columnKey):
        """Return the index of the column with the given key (i.e. the first part of the corresponding tuple
        in self.columns."""
        for i in range(len(self.columns)):
            if self.columns[i][0] == columnKey:
                return i
        raise ValueError("Invalid key {}".format(columnKey))
    

def createNewFlagType(parent=None):
    """Ask the user to supply a name and then create a new flag with this name. Return the new flag or None
    if no flag was created (e.g. if the user aborted the dialog or the supplied name was invalid)."""
    name, ok = QtGui.QInputDialog.getText(parent, translate("FlagManager", "New Flag"),
                                          translate("FlagManager", "Please enter the name of the new flag:"))
    if not ok:
        return None
    
    if flags.exists(name):
        QtGui.QMessageBox.warning(parent, translate("FlagManager", "Cannot create flag"),
                                  translate("FlagManager", "This flag does already exist."))
        return None
    elif not flags.isValidFlagname(name):
        QtGui.QMessageBox.warning(parent, translate("FlagManager", "Invalid flagname"),
                                  translate("FlagManager", "This is not a valid flagname."))
        return None
    
    return flags.addFlagType(name)
    