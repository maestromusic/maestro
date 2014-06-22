# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2014 Martin Altmayer, Michael Helmling
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
from ...core import domains
from .. import misc, dialogs
from ..misc import iconbuttonbar

translate = QtCore.QCoreApplication.translate


class DomainManager(QtGui.QWidget):
    """The DomainManager allows to add, edit and delete domains."""
    def __init__(self, dialog, panel):
        super().__init__(panel)
        self.setLayout(QtGui.QVBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)
        self.layout().setSpacing(0)
        
        buttonBar = QtGui.QToolBar()
        self.layout().addWidget(buttonBar)
                
        addButton = QtGui.QToolButton()
        addButton.setIcon(utils.getIcon("add.png"))
        addButton.setToolTip("Add domain...")
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
        self.deleteButton = QtGui.QToolButton()
        self.deleteButton.setIcon(utils.getIcon("delete.png"))
        self.deleteButton.setToolTip(self.tr("Delete domain"))
        self.deleteButton.setEnabled(False)
        self.deleteButton.clicked.connect(self._handleDeleteButton)
        buttonBar.addWidget(self.deleteButton)
        
        self.columns = [
                ("name",   self.tr("Name")),
                ("number", self.tr("# of elements"))
                ]
        
        self.tableWidget = QtGui.QTableWidget()
        self.tableWidget.setColumnCount(len(self.columns))
        self.tableWidget.verticalHeader().hide()
        self.tableWidget.setSortingEnabled(True)
        self.tableWidget.horizontalHeader().setResizeMode(QtGui.QHeaderView.ResizeToContents)
        self.tableWidget.itemChanged.connect(self._handleItemChanged)
        self.tableWidget.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.tableWidget.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.tableWidget.itemSelectionChanged.connect(self._handleSelectionChanged)
        self.layout().addWidget(self.tableWidget)
        self._loadDomains()
        
        self._checkUndoRedoButtons()
        stack.indexChanged.connect(self._checkUndoRedoButtons)
        stack.undoTextChanged.connect(self._checkUndoRedoButtons)
        stack.redoTextChanged.connect(self._checkUndoRedoButtons)
        application.dispatcher.connect(self._handleDispatcher)
        
    def _handleDispatcher(self, event):
        """React to DomainChangedEvent from the dispatcher."""
        if isinstance(event, domains.DomainChangedEvent):
            self._loadDomains()
            
    def _loadDomains(self):
        """Load domain information from domains-module to GUI."""
        self._domains = sorted(domains.domains, key=lambda d: d.name)
        self.tableWidget.clear()
        self.tableWidget.setHorizontalHeaderLabels([column[1] for column in self.columns])
        self.tableWidget.setRowCount(len(self._domains))
        
        NumericSortItem = misc.createSortingTableWidgetClass('NumericSortItem', misc.leadingInt)
        
        for row, domain in enumerate(self._domains):
            column = self._getColumnIndex("name")
            item = QtGui.QTableWidgetItem(domain.name)
            item.setFlags(Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tableWidget.setItem(row, column, item)
            
            column = self._getColumnIndex("number")
            item = NumericSortItem('{}    '.format(self._getElementCount(domain)))
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tableWidget.setItem(row, column, item)
            
        self.tableWidget.resizeColumnsToContents()
    
    def _getElementCount(self, domain):
        """Return the number of elements in the given domain."""
        return db.query("SELECT COUNT(*) FROM {p}elements WHERE domain = ?", domain.id).getSingle()
                        
    def _handleAddButton(self):
        """Create a new domain (querying the user for its name)."""
        createNewDomain(self) # DomainManager will be reloaded via the dispatcher event
            
    def _handleDeleteButton(self):
        """Delete the selected domain."""
        rows = self.tableWidget.selectionModel().selectedRows()
        if len(rows) == 1:
            if len(domains.domains) == 1:
                dialogs.warning(self.tr("Cannot delete domain"),
                                self.tr("Cannot delete the last domain."),
                                self)
                return
            domain = self._domains[rows[0].row()]
            number = self._getElementCount(domain)
            if number > 0:
                dialogs.warning(self.tr("Cannot delete domain"),
                                self.tr("Cannot delete a domain that contains elements."),
                                self)
                return
            domains.deleteDomain(domain)

    def _handleItemChanged(self, item):
        """Change a domain's name after the user edited it."""
        if item.column() != self._getColumnIndex("name"): # Only the name column is editable
            return
        domain = self._domains[item.row()]
        oldName = domain.name
        newName = item.text().strip()
        if oldName == newName:
            return
        
        if not domains.isValidName(newName):
            QtGui.QMessageBox(self, self.tr("Cannot change domain"),
                              self.tr("'{}' is not a valid domain name.").format(newName))
            item.setText(oldName)
            return
        
        if domains.exists(newName):
            QtGui.QMessageBox.warning(self, self.tr("Cannot change domain"),
                                      self.tr("A domain named '{}' already exists.").format(newName))
            item.setText(oldName)
            return
              
        domain.changeDomain(domain, name=newName)
    
    def _checkUndoRedoButtons(self):
        """Enable or disable the undo and redo buttons depending on stack state."""
        self.undoButton.setEnabled(stack.canUndo())
        self.undoButton.setToolTip(self.tr("Undo: {}").format(stack.undoText()))
        self.redoButton.setEnabled(stack.canRedo())
        self.redoButton.setToolTip(self.tr("Redo: {}").format(stack.redoText()))
        
    def _handleSelectionChanged(self):
        rows = self.tableWidget.selectionModel().selectedRows()
        self.deleteButton.setEnabled(len(rows) == 1)
        
    def _getColumnIndex(self, columnKey):
        """Return the index of the column with the given key (i.e. the first part of the corresponding tuple
        in self.columns."""
        for i in range(len(self.columns)):
            if self.columns[i][0] == columnKey:
                return i
        raise ValueError("Invalid key {}".format(columnKey))
    

def createNewDomain(parent=None):
    """Ask the user to supply a name and then create a new domain with this name. Return the new domain or
    None if no domain was created (e.g. if the user aborted the dialog or the supplied name was invalid)."""
    name, ok = QtGui.QInputDialog.getText(parent, translate("DomainManager", "New domain"),
                                    translate("DomainManager", "Please enter the name of the new domain:"))
    if not ok:
        return None
    
    if domains.exists(name):
        QtGui.QMessageBox.warning(parent, translate("DomainManager", "Cannot create domain"),
                                  translate("DomainManager", "This domain does already exist."))
        return None
    elif not domains.isValidName(name):
        QtGui.QMessageBox.warning(parent, translate("DomainManager", "Invalid domain name"),
                                  translate("DomainManager", "This is not a valid domain name."))
        return None
    
    return domains.addDomain(name)
    