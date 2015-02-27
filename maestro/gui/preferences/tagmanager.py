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

import functools

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from ... import application, database as db, utils, stack
from ...core import tags
from .. import tagwidgets, dialogs, misc

CUSTOM_MIME = 'application/x-maestrotagtype'

    
class TagManager(QtWidgets.QWidget):
    """The TagManager allows to add, edit and remove tagtypes (like artist, composer,...). To make things
    easy it only allows changing tagtypes which do not appear in any internal element."""
    def __init__(self, dialog, panel):
        super().__init__(panel)
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)
        self.layout().setSpacing(0)
        
        buttonBar = QtWidgets.QToolBar()
        self.layout().addWidget(buttonBar)

        addButton = QtWidgets.QToolButton()
        addButton.setIcon(QtGui.QIcon.fromTheme('list-add'))
        addButton.setToolTip(self.tr("Add tag..."))
        addButton.clicked.connect(self._handleAddButton)
        buttonBar.addWidget(addButton)
        self.undoButton = QtWidgets.QToolButton()
        self.undoButton.setIcon(QtGui.QIcon.fromTheme('edit-undo'))
        self.undoButton.setToolTip(self.tr("Undo"))
        self.undoButton.clicked.connect(stack.undo)
        buttonBar.addWidget(self.undoButton)
        self.redoButton = QtWidgets.QToolButton()
        self.redoButton.setIcon(QtGui.QIcon.fromTheme('edit-redo'))
        self.redoButton.setToolTip(self.tr("Redo"))
        self.redoButton.clicked.connect(stack.redo)
        buttonBar.addWidget(self.redoButton)
        self.showInBrowserButton = QtWidgets.QToolButton()
        self.showInBrowserButton.setIcon(utils.getIcon("preferences/goto.png"))
        self.showInBrowserButton.setToolTip(self.tr("Show in browser"))
        self.showInBrowserButton.setEnabled(False)
        self.showInBrowserButton.clicked.connect(self._handleShowInBrowserButton)
        buttonBar.addWidget(self.showInBrowserButton)
        self.deleteButton = QtWidgets.QToolButton()
        self.deleteButton.setIcon(QtWidgets.QIcon.fromTheme('edit-delete'))
        self.deleteButton.setToolTip(self.tr("Delete tag"))
        self.deleteButton.setEnabled(False)
        self.deleteButton.clicked.connect(self._handleDeleteButton)
        buttonBar.addWidget(self.deleteButton)
        
        self.table = TagManagerTableWidget()
        self.layout().addWidget(self.table)
        self.table.itemSelectionChanged.connect(self._handleSelectionChanged)
        
        self._checkUndoRedoButtons()
        stack.indexChanged.connect(self._checkUndoRedoButtons)
    
    def _handleAddButton(self):
        """Open a NewTagTypeDialog and create a new tag."""
        # We cannot connect the add button to createTagType directly because the clicked-signal has an
        # argument 'checked'
        tagwidgets.AddTagTypeDialog().exec_()

    def _checkUndoRedoButtons(self):
        """Enable or disable the undo and redo buttons depending on stack state."""
        self.undoButton.setEnabled(stack.canUndo())
        self.redoButton.setEnabled(stack.canRedo())
        
    def _handleSelectionChanged(self):
        rows = self.table.selectionModel().selectedRows()
        from .. import browser
        self.showInBrowserButton.setEnabled(len(rows) == 1 and browser.defaultBrowser is not None)
        self.deleteButton.setEnabled(len(rows) == 1)
    
    def _handleShowInBrowserButton(self):
        """Load all elements containing the selected tag into the default browser."""
        from .. import browser
        rows = self.table.selectionModel().selectedRows()
        if len(rows) == 1 and browser.defaultBrowser is not None:
            tag = self.table.getTag(rows[0].row())
            browser.defaultBrowser.search('{tag='+tag.name+'}')
        
    def _handleDeleteButton(self):
        """Ask the user if he really wants this and if so, delete the tag."""
        rows = self.table.selectionModel().selectedRows()
        if len(rows) == 1:
            tag = self.table.getTag(rows[0].row())
            if self.table.getElementCount(tag) != 0:
                dialogs.warning(self.tr("Cannot delete tag"),
                                self.tr("Cannot delete a tag that appears in elements."),
                                self)
                return
            tags.removeTagType(tag)
            

class TagManagerTableWidget(QtWidgets.QTableWidget):
    """The TableWidget used by the TagManager. We need our own class because of Drag&Drop."""
    def __init__(self):
        super().__init__()
        
        self.columns = [
                ("sort",   self.tr("#")),
                ("icon",   self.tr("Icon")),
                ("name",   self.tr("Name")),
                ("type",   self.tr("Type")),
                ("title",  self.tr("Title")),
                ("private", self.tr("Private?")),
                ("elementCount", self.tr("# of elements")),
                ]
        self.setColumnCount(len(self.columns))
        
        self.verticalHeader().hide()
        self.setSortingEnabled(True)
        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.horizontalHeader().setStretchLastSection(True)
        self.setDragEnabled(True)
        # I first tried to use InternalMove but Qt doesn't call dropMimeData then and there doesn't seem
        # to be another way to intercept drops (ok probably it is possible using some weird event filters).
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDrop)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().setSortIndicator(0, Qt.AscendingOrder)
        
        self.cellDoubleClicked.connect(self._handleCellDoubleClicked)
        self.customContextMenuRequested.connect(self._handleCustomContextMenuRequested)
        
        self._loadTags()
        self.itemChanged.connect(self._handleItemChanged)
        application.dispatcher.connect(self._handleDispatcher)
        
    def _handleDispatcher(self, event):
        """React to TagTypeChangeEvents from the dispatcher."""
        if isinstance(event, (tags.TagTypeChangeEvent, tags.TagTypeOrderChangeEvent)):
            self._loadTags()
            
    def _loadTags(self):
        """Load tag information from tags-module to GUI."""
        # Store the old sorting
        sortIndicator = (self.horizontalHeader().sortIndicatorSection(),
                         self.horizontalHeader().sortIndicatorOrder())
        
        self.clear()
        self.setHorizontalHeaderLabels([column[1] for column in self.columns])
        self.setRowCount(len(tags.tagList))
        self.horizontalHeader().setSortIndicator(0, Qt.AscendingOrder)
        
        CheckedSortItem = misc.createSortingTableWidgetClass('PrivateItemClass', 'checked')
        NumericSortItem = misc.createSortingTableWidgetClass('NumericalSortClass', 'leadingInt')
        
        stdFlags = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled
        
        for row, tag in enumerate(tags.tagList):
            elementCount = self.getElementCount(tag)
            
            column = self._getColumnIndex("sort")
            item = NumericSortItem("{}    ".format(row+1))
            item.setData(Qt.UserRole, tag)
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
            item.setFlags(stdFlags)
            self.setItem(row, column, item)
            
            column = self._getColumnIndex("icon")
            label = QtWidgets.QLabel()
            label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            self.setCellWidget(row, column, label)
            if tag.iconPath is not None:
                label.setPixmap(tag.icon.pixmap(32, 32))
                label.setToolTip(tag.iconPath)     
            
            column = self._getColumnIndex("name")
            item = QtWidgets.QTableWidgetItem(tag.name)
            item.setData(Qt.ToolTipRole, tag.name)
            if elementCount == 0:
                item.setFlags(stdFlags | Qt.ItemIsEditable)
            else: item.setFlags(stdFlags)
            self.setItem(row, column, item)
            
            column = self._getColumnIndex("type")
            if elementCount == 0:
                combo = tagwidgets.ValueTypeBox(tag.type)
                combo.disableMouseWheel = True
                combo.typeChanged.connect(functools.partial(self._handleValueTypeChanged, tag))
                self.setCellWidget(row, column, combo)
            else:
                item = QtWidgets.QTableWidgetItem(tag.type.name)
                item.setFlags(stdFlags)
                self.setItem(row, column, item)
            
            column = self._getColumnIndex("title")
            item = QtWidgets.QTableWidgetItem(tag.rawTitle if tag.rawTitle is not None else '')
            item.setFlags(stdFlags | Qt.ItemIsEditable)
            self.setItem(row, column, item)
            
            column = self._getColumnIndex("private")
            item = CheckedSortItem()
            item.setFlags(stdFlags | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if tag.private else Qt.Unchecked)
            self.setItem(row, column, item)
            
            column = self._getColumnIndex("elementCount")
            item = NumericSortItem("{}    ".format(elementCount))
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
            item.setFlags(stdFlags)
            self.setItem(row, column, item)
                
        for i in range(len(tags.tagList)):
            self.setRowHeight(i, 36)
            
        #self.sortItems(*sortIndicator)
        self.horizontalHeader().setSortIndicator(*sortIndicator)
    
    def getTag(self, row):
        """Return the tagtype in the given row. This is not necessarily tags.tagList[row] due to sorting."""
        itemInFirstColumn = self.item(row, self._getColumnIndex('sort'))
        return itemInFirstColumn.data(Qt.UserRole)
    
    def _handleItemChanged(self, item):
        """Handle changes to the name or private state of a tag."""
        if item.column() == self._getColumnIndex("name"):
            tag = self.getTag(item.row())
            oldName = tag.name
            newName = item.text()
            if oldName == newName:
                return
            allowChanges = self.getElementCount(tag) == 0
            # Perform different tests via a for-loop
            for check, message in (
                    (not allowChanges, self.tr("Cannot change a tag that appears in elements.")),
                    (tags.isInDb(newName), self.tr("A tag named '{}' already exists.").format(newName)),
                    (not tags.isValidTagName(newName),self.tr("'{}' is not a valid tagname.").format(newName))
                 ):
                if check:
                    dialogs.warning(self.tr("Cannot change tag"), message, self)
                    item.setText(oldName) # Reset
                    return
            type, title, iconPath, private = tag.type, tag.rawTitle, tag.iconPath, tag.private
            index = tags.tagList.index(tag)
            # Because tag instances are unique, the tag module does not allow to change the name of a tag.
            # But we can add the new tag to the database and remove the old one.
            stack.beginMacro(self.tr("Change tag name"))
            tags.removeTagType(tag)
            try:
                tags.addTagType(newName, type=type, title=title, iconPath=iconPath,
                                private=private, index=index)
            except tags.TagValueError:
                dialogs.warning(self.tr("Cannot change tag name"),
                                self.tr("The new tag name already appears in some elements with values that"
                                        " cannot be converted to the type of this tag."),
                                self)
                stack.abortMacro()
                return
            stack.endMacro()
        
        elif item.column() == self._getColumnIndex('title'):
            tag = self.getTag(item.row())
            itemText = item.text() if item.text() != '' else None
            if itemText != tag.rawTitle:
                if not tags.titleAllowed(itemText, tag):
                    dialogs.warning(self.tr("Cannot change title"),
                                    self.tr("A tag with this title exists already."),
                                    self)
                    item.setText(tag.rawTitle) # Reset
                    return
                tags.changeTagType(tag, title=itemText)
            
        elif item.column() == self._getColumnIndex('private'): 
            tag = self.getTag(item.row())
            newPrivate = item.checkState() == Qt.Checked
            if newPrivate == tag.private:
                return
            if self.getElementCount(tag) != 0:
                # Reset. Unfortunately it is not possible to deactivate the Checkboxes without disabling
                # the item (which would cause problems with Drag&Drop).
                item.setCheckState(Qt.Checked if tag.private else Qt.Unchecked)
                return
            tags.changeTagType(tag, private=newPrivate)
        
    def _handleValueTypeChanged(self, tag, type):
        """Handle changes to the comboboxes containing valuetypes."""
        if self.getElementCount(tag) != 0:
            dialogs.warning(self.tr("Cannot change tag"),
                            self.tr("Cannot change a tag that appears in elements."),
                            self)
        else:
            try:
                tags.changeTagType(tag, type=type)
                return
            except tags.TagValueError:
                dialogs.warning(self.tr("Cannot change tag type"),
                                self.tr("The tag appears in some elements with values that cannot be converted"
                                        " to the new type."),
                                self)
        # Reset
        for row in range(self.rowCount()):
            if tag == self.getTag(row):
                column = self._getColumnIndex("type")
                combo = self.cellWidget(row, column)
                combo.setType(tag.type)
            
    
    def _handleCellDoubleClicked(self, row, column):
        """Handle double clicks on the first column containing icons. A click will open a file dialog to
        change the icon."""
        if column == self._getColumnIndex("icon"):
            self._openIconDialog(row, self.getTag(row))
    
    def _handleCustomContextMenuRequested(self, pos):
        """React to customContextMenuRequested signals."""
        row = self.rowAt(pos.y())
        column = self.columnAt(pos.x())
        if column == self._getColumnIndex("icon") and row != -1:
            tag = self.getTag(row)
            menu = QtWidgets.QMenu(self)
            if tag.iconPath is None:
                changeAction = QtWidgets.QAction(self.tr("Add icon..."), menu)
            else: changeAction = QtWidgets.QAction(self.tr("Change icon..."), menu)
            changeAction.triggered.connect(lambda: self._openIconDialog(row, tag))
            menu.addAction(changeAction)
            removeAction = QtWidgets.QAction(self.tr("Remove icon"), menu)
            removeAction.setEnabled(tag.iconPath is not None)
            removeAction.triggered.connect(lambda: self._setIcon(row, tag, None))
            menu.addAction(removeAction)
            menu.exec_(self.viewport().mapToGlobal(pos))
    
    def _openIconDialog(self, row, tag):
        """Open a file dialog so that the user may choose an icon for the given tag. Assume that the tag
        is in the given *row* (depends on current sorting)."""
        # Choose a sensible directory as starting point
        from ..misc import iconchooser
        result = iconchooser.IconChooser.getIcon([':maestro/tags', ':maestro/flags'], tag.iconPath, self)
        
        if result and result[1] != tag.iconPath:
            self._setIcon(row, tag, result[1])
            
    def _setIcon(self, row, tag, iconPath):
        """Set the icon(-path) of *tag* to *iconPath* and update the GUI. Assume that the tag is in the
        given *row* (depends on current sorting)."""
        tags.changeTagType(tag, iconPath=iconPath)
        # Update the widget
        label = self.cellWidget(row, self._getColumnIndex('icon'))
        if tag.icon is not None:
            label.setPixmap(tag.icon.pixmap(32, 32))
            label.setToolTip(tag.iconPath)
        else:
            label.setPixmap(QtGui.QPixmap())
            label.setToolTip(None)
            
    def mimeTypes(self):
        return [CUSTOM_MIME]
    
    def mimeData(self, items):
        return TagTypeMimeData(self.getTag(items[0].row()))
    
    def dropMimeData(self, row, column, mimeData, action):
        if isinstance(mimeData, TagTypeMimeData) and mimeData.tagType in tags.tagList:
            if (self.horizontalHeader().sortIndicatorSection() != self._getColumnIndex('sort')):
                QtWidgets.QMessageBox.warning(self, self.tr("Move not possible"),
                     self.tr("Changing the order of tagtypes is only possible, if the tagtypes are sorted "
                             " in the sort order (i.e. by the first column)."))
                return False
            
            oldPos = tags.tagList.index(mimeData.tagType)
            
            if self.horizontalHeader().sortIndicatorOrder() == Qt.AscendingOrder:
                insertPos = row
            else: insertPos = len(tags.tagList) - row
            if insertPos in (oldPos, oldPos+1):
                return True # Nothing to move
            
            newPos = insertPos if insertPos < oldPos else insertPos-1
            tags.moveTagType(mimeData.tagType, newPos)
            return True
        return False   
    
    def getElementCount(self, tag):
        """Return the number of internal elements in which the tag appears."""
        return db.query("SELECT COUNT(DISTINCT element_id) FROM {}tags WHERE tag_id = ?"
                               .format(db.prefix), tag.id).getSingle()
        
    def _getColumnIndex(self, columnKey):
        """Return the index of the column with the given key (i.e. the first part of the corresponding tuple
        in self.columns."""
        for i in range(len(self.columns)):
            if self.columns[i][0] == columnKey:
                return i
        raise ValueError("Invalid key {}".format(columnKey))
    
    
class TagTypeMimeData(QtCore.QMimeData):
    """Specialized MimeData for moves within the TagManager. It stores a single tagtype."""
    def __init__(self, tagType):
        super().__init__()
        self.tagType = tagType
        
    def hasFormat(self, format):
        return format in self.formats()
    
    def formats(self):
        return ['text/plain', CUSTOM_MIME]
        
    def retrieveData(self, mimeType, type=None):
        if mimeType == 'text/plain':
            return self.tagType.title
        elif mimeType == CUSTOM_MIME:
            return self.tagType
        else:
            # return a null variant of the given type (confer the documentation of retrieveData)
            return QtCore.QVariant(type) if type is not None else QtCore.QVariant()
