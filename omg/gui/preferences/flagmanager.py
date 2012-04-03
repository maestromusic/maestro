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

import functools, os

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ... import database as db, constants, utils, flags, modify
from .. import misc
from ..misc import iconbuttonbar

translate = QtCore.QCoreApplication.translate


class FlagManager(QtGui.QWidget):
    """The FlagManager allows to add, edit and remove flagtypes."""
    def __init__(self,dialog,parent=None):
        super().__init__(parent)
        self.setLayout(QtGui.QVBoxLayout())
        
        self.columns = [
                ("icon",   self.tr("Icon")),
                ("name",   self.tr("Name")),
                ("number", self.tr("# of elements")),
                ("actions",self.tr("Actions"))
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
        self.layout().addWidget(self.tableWidget)
        
        buttonBarLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(buttonBarLayout)
        
        addButton = QtGui.QPushButton(utils.getIcon("add.png"),self.tr("Add flag"))
        addButton.clicked.connect(self._handleAddButton)
        buttonBarLayout.addWidget(addButton)
        
        self.undoButton = QtGui.QPushButton(self.tr("Undo"))
        self.undoButton.clicked.connect(modify.stack.undo)
        buttonBarLayout.addWidget(self.undoButton)
        self.redoButton = QtGui.QPushButton(self.tr("Redo"))
        self.redoButton.clicked.connect(modify.stack.redo)
        buttonBarLayout.addWidget(self.redoButton)
        
        buttonBarLayout.addStretch(1)
        
        style = QtGui.QApplication.style()
        closeButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogCloseButton),
                                        self.tr("Close"))
        closeButton.clicked.connect(dialog.accept)
        buttonBarLayout.addWidget(closeButton)
        
        self._loadFlags()
        self._checkUndoRedoButtons()
        modify.stack.indexChanged.connect(self._checkUndoRedoButtons)
        modify.dispatcher.changes.connect(self._handleDispatcher)
        
    def _handleDispatcher(self,event):
        """React to FlagTypeChangedEvents from the dispatcher."""
        if isinstance(event,flags.FlagTypeChangedEvent):
            self._loadFlags()
            
    def _loadFlags(self):
        """Load flags information from flags-module to GUI."""
        self._flagTypes = sorted(flags.allFlags(),key=lambda f: f.name)
        self.tableWidget.clear()
        self.tableWidget.setHorizontalHeaderLabels(
                    [self.tr("Icon"),self.tr("Name"),self.tr("# of elements"),self.tr("Actions")])
    
        self.tableWidget.setRowCount(len(self._flagTypes))
        
        NumericSortItem = misc.createSortingTableWidgetClass('NumericSortItem',misc.leadingInt)
        
        for row,flagType in enumerate(self._flagTypes):
            column = self._getColumnIndex("icon")
            label = QtGui.QLabel()       
            label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            index = self.tableWidget.model().index(row,column)   
            self.tableWidget.setIndexWidget(index,label)
            if flagType.iconPath is not None:
                label.setPixmap(QtGui.QPixmap(flagType.iconPath))
                label.setToolTip(flagType.iconPath)           
            
            column = self._getColumnIndex("name")
            item = QtGui.QTableWidgetItem(flagType.name)
            item.setFlags(Qt.ItemIsEditable | Qt.ItemIsEnabled)
            self.tableWidget.setItem(row,column,item)
            
            column = self._getColumnIndex("number")
            item = NumericSortItem('{}    '.format(self._getElementCount(flagType)))
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
            item.setFlags(Qt.ItemIsEnabled)
            self.tableWidget.setItem(row,column,item)
            
            column = self._getColumnIndex("actions")
            buttons = iconbuttonbar.IconButtonBar()
            buttons.addIcon(utils.getIcon('delete.png'),
                                 functools.partial(self._handleRemoveButton,flagType),
                                 self.tr("Delete flag"))
            buttons.addIcon(utils.getIcon('goto.png'),
                                 toolTip=self.tr("Show in browser"))
            index = self.tableWidget.model().index(row,column)                     
            self.tableWidget.setIndexWidget(index,buttons)
            
        self.tableWidget.resizeColumnsToContents()
    
    def _getElementCount(self,flagType):
        """Return the number of elements having the given flag."""
        return db.query("SELECT COUNT(*) FROM {}flags WHERE flag_id = ?".format(db.prefix),flagType.id)\
                        .getSingle()
                        
    def _handleAddButton(self):
        """Create a new flag (querying the user for the flag's name)."""
        createNewFlagType(self) # FlagManager will be reloaded via the dispatcher event
    
    def _handleRemoveButton(self,flagType):
        """Ask the user if he really wants this and if so, remove the flag."""
        number,allowChanges = self._appearsInElements(flagType)
        if not allowChanges:
            question = self.tr("Do you really want to remove the flag '{}'? It will be removed from %n element(s).",None,number)
        else: question = self.tr("Do you really want to remove the flag '{}'?")
        if (QtGui.QMessageBox.question(self,self.tr("Remove flag?"),
                                       question.format(flagType.name),
                                       QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
                                       QtGui.QMessageBox.Yes)
                == QtGui.QMessageBox.Yes):
            if number > 0:
                # TODO
                raise NotImplementedError()
            modify.push(flags.FlagTypeUndoCommand(constants.DELETED,flagType))

    def _handleItemChanged(self,item):
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
            QtGui.QMessageBox(self,self.tr("Cannot change flag"),
                              self.tr("'{}' is not a valid flagname.").format(newName))
            item.setText(oldName)
            return
        
        number,allowChanges = self._appearsInElements(flagType)
        if flags.exists(newName):
            QtGui.QMessageBox.warning(self,self.tr("Cannot change flag"),
                                      self.tr("A flag name '{}' does already exist.").format(newName))
            item.setText(oldName)
            return
                                
        if number > 0:
            question = self.tr("Do you really want to change the flag '{}'? It will be changed in %n element(s).",
                               None,number).format(oldName)
            if (QtGui.QMessageBox.question(self,self.tr("Change flag?"),question,
                                   QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
                                   QtGui.QMessageBox.Yes)
                        != QtGui.QMessageBox.Yes):
                item.setText(oldName)
                return
        modify.push(flags.FlagTypeUndoCommand(constants.CHANGED,flagType,name=newName))
    
    def _checkUndoRedoButtons(self):
        """Enable or disable the undo and redo buttons depending on stack state."""
        self.undoButton.setEnabled(modify.stack.canUndo()
                            and isinstance(modify.stack.command(modify.stack.index()-1),
                                           flags.FlagTypeUndoCommand))
        self.redoButton.setEnabled(modify.stack.canRedo()
                            and isinstance(modify.stack.command(modify.stack.index()),
                                           flags.FlagTypeUndoCommand))
        
    def _handleCellDoubleClicked(self,row,column):
        """Handle double clicks on the first column containing icons. A click will open a file dialog to
        change the icon."""
        if column == 0:
            flagType = self._flagTypes[row]
            self._openIconDialog(flagType)
    
    def _handleCustomContextMenuRequested(self,pos):
        """React to customContextMenuRequested signals."""
        row = self.tableWidget.rowAt(pos.y())
        column = self.tableWidget.columnAt(pos.x())
        if column == 0 and row != -1:
            flagType = self._flagTypes[row]
            menu = QtGui.QMenu(self.tableWidget)
            if flagType.iconPath is None:
                changeAction = QtGui.QAction(self.tr("Add icon..."),menu)
            else: changeAction = QtGui.QAction(self.tr("Change icon..."),menu)
            changeAction.triggered.connect(lambda: self._openIconDialog(flagType))
            menu.addAction(changeAction)
            removeAction = QtGui.QAction(self.tr("Remove icon"),menu)
            removeAction.setEnabled(flagType.iconPath is not None)
            removeAction.triggered.connect(lambda: self._setIcon(flagType,None))
            menu.addAction(removeAction)
            menu.exec_(self.tableWidget.viewport().mapToGlobal(pos))
    
    def _openIconDialog(self,flagType):
        """Open a file dialog so that the user may choose an icon for the given flag."""
        # Choose a sensible directory as starting point
        from ..misc import iconchooser
        result = iconchooser.IconChooser.getIcon([':omg/flags'],flagType.iconPath,self)
        
        if result and result[1] != flagType.iconPath:
            self._setIcon(flagType,result[1])
            
    def _setIcon(self,flagType,iconPath):
        """Set the icon(-path) of *flagType* to *iconPath* and update the GUI.""" 
        modify.push(flags.FlagTypeUndoCommand(constants.CHANGED,flagType,iconPath=iconPath))
        # Update the widget
        row = self._flagTypes.index(flagType)
        index = self.tableWidget.model().index(row,0)                     
        label = self.tableWidget.indexWidget(index)
        # Both works also if iconPath is None
        label.setPixmap(QtGui.QPixmap(flagType.iconPath))
        label.setToolTip(flagType.iconPath)
                   
    def _appearsInElements(self,flagType):
        """Return the number of db-elements that contain a flag of the given type in the database. As second 
        result return whether the user should be allowed to change the flag, i.e. whether the flag does not
        appear in any element in the database nor in the editor.
        """
        number = db.query("SELECT COUNT(element_id) FROM {}flags WHERE flag_id = ?"
                            .format(db.prefix),flagType.id).getSingle()  
        if number > 0:
            return number,False
        else:
            from .. import editor
            for model in editor.activeEditorModels():
                if any(flagType in node.flags for node in model.getRoot().getAllNodes(skipSelf=True)):
                    return 0,False
            return 0,True
        
    def _getColumnIndex(self,columnKey):
        """Return the index of the column with the given key (i.e. the first part of the corresponding tuple
        in self.columns."""
        for i in range(len(self.columns)):
            if self.columns[i][0] == columnKey:
                return i
        raise ValueError("Invalid key {}".format(columnKey))
    

def createNewFlagType(parent = None):
    """Ask the user to supply a name and then create a new flag with this name. Return the new flag or None
    if no flag is created (e.g. if the user aborted the dialog or the supplied name was invalid)."""
    name,ok = QtGui.QInputDialog.getText(parent,translate("FlagManager","New Flag"),
                                         translate("FlagManager","Please enter the name of the new flag"))
    if not ok:
        return None
    
    if flags.exists(name):
        QtGui.QMessageBox.warning(parent,translate("FlagManager","Cannot create flag"),
                                  translate("FlagManager","This flag does already exist."))
        return None
    elif not flags.isValidFlagname(name):
        QtGui.QMessageBox.warning(parent,translate("FlagManager","Invalid flagname"),
                                  translate("FlagManager","This is no a valid flagname."))
        return None
    else:
        modify.push(flags.FlagTypeUndoCommand(constants.ADDED,name=name))
        return True
    