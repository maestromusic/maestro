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

import functools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import tags, utils, database as db, constants, modify
from . import tagwidgets, dialogs
from .misc import iconbuttonbar


class TagManager(QtGui.QDialog):
    """The TagManager allows to add, edit and remove tagtypes (like artist, composer,...). To make things
    easy it only allows changing tagtypes which do not appear in any element."""
    def __init__(self,parent=None):
        QtGui.QDialog.__init__(self,parent)
        self.setWindowTitle(self.tr("TagManager - OMG {}").format(constants.VERSION))
        self.resize(650,600)
        self.setLayout(QtGui.QVBoxLayout())
        
        self.layout().addWidget(QtGui.QLabel(
                    self.tr("Note that you cannot change or remove tags that already appear in elements.")))
        
        self.columns = [
                ("icon",   self.tr("Icon")),
                ("name",   self.tr("Name")),
                ("type",   self.tr("Value-Type")),
                ("private",self.tr("Private?")),
                ("sort",   self.tr("Sort-Tags")),
                ("number", self.tr("# of elements")),
                ("actions",self.tr("Actions"))
                ]
        
        self.tableWidget = QtGui.QTableWidget()
        self.tableWidget.setColumnCount(len(self.columns))
        self.tableWidget.verticalHeader().hide()
        # TODO: Does not work
        #self.tableWidget.setSortingEnabled(True)
        self.tableWidget.horizontalHeader().setResizeMode(QtGui.QHeaderView.ResizeToContents)
        self.tableWidget.cellDoubleClicked.connect(self._handleCellDoubleClicked)
        self.tableWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tableWidget.customContextMenuRequested.connect(self._handleCustomContextMenuRequested)
        self.layout().addWidget(self.tableWidget)
        
        buttonBarLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(buttonBarLayout)
        
        addButton = QtGui.QPushButton(utils.getIcon("add.png"),self.tr("Add tag"))
        addButton.clicked.connect(self._handleAddButton)
        buttonBarLayout.addWidget(addButton)
        
        buttonBarLayout.addStretch(1)
        
        style = QtGui.QApplication.style()
        closeButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogCloseButton),
                                        self.tr("Close"))
        closeButton.clicked.connect(self.accept)
        buttonBarLayout.addWidget(closeButton)
        
        self._loadTags()
        self.tableWidget.itemChanged.connect(self._handleItemChanged)
        
    def _loadTags(self):
        """Load tag information from tags-module to GUI."""
        self.tableWidget.clear()
        self.tableWidget.setHorizontalHeaderLabels([column[1] for column in self.columns])
        self.tableWidget.setRowCount(len(tags.tagList))
        
        for row,tag in enumerate(tags.tagList):
            number,allowChanges = self._appearsInElements(tag)
            
            column = self._getColumnIndex("icon")
            label = QtGui.QLabel()       
            label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            index = self.tableWidget.model().index(row,column)   
            self.tableWidget.setIndexWidget(index,label)
            if tag.iconPath is not None:
                label.setPixmap(tag.icon.pixmap(32,32))
                label.setToolTip(tag.iconPath)     
            
            column = self._getColumnIndex("name")
            item = QtGui.QTableWidgetItem(tag.name)
            if allowChanges:
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable)
            else: item.setFlags(Qt.ItemIsEnabled)
            self.tableWidget.setItem(row,column,item)
            
            column = self._getColumnIndex("type")
            if allowChanges:
                combo = tagwidgets.ValueTypeBox(tag.type)
                combo.disableMouseWheel = True
                combo.typeChanged.connect(functools.partial(self._handleValueTypeChanged,tag))
                index = self.tableWidget.model().index(row,column)  
                self.tableWidget.setIndexWidget(index,combo)
            else:
                item = QtGui.QTableWidgetItem(tag.type.name)
                item.setFlags(Qt.ItemIsEnabled)
                self.tableWidget.setItem(row,column,item)
            
            column = self._getColumnIndex("private")
            item = QtGui.QTableWidgetItem()
            if allowChanges:
                item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            else: item.setFlags(Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if tag.private else Qt.Unchecked)
            #check.stateChanged.connect(functools.partial(self._handlePrivateChanged,tag))
            self.tableWidget.setItem(row,column,item)
        
            column = self._getColumnIndex("sort")
            item = QtGui.QTableWidgetItem(', '.join(t.name for t in tag.sortTags))
            item.setFlags(Qt.ItemIsEnabled)
            self.tableWidget.setItem(row,column,item)
            
            column = self._getColumnIndex("number")
            if not allowChanges and number == 0:
                text = self.tr("0, appears in editor")
            else: text = number
            item = QtGui.QTableWidgetItem("{}    ".format(text))
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
            item.setFlags(Qt.ItemIsEnabled)
            self.tableWidget.setItem(row,column,item)
            
            column = self._getColumnIndex("actions")
            if allowChanges:
                self.buttons = iconbuttonbar.IconButtonBar()
                self.buttons.addIcon(utils.getIcon('delete.png'),
                                     functools.partial(self._handleRemoveButton,tag),
                                     self.tr("Delete tag"))
                self.buttons.addIcon(utils.getIcon('goto.png'),
                                     toolTip=self.tr("Show in browser"))
                index = self.tableWidget.model().index(row,column)                     
                self.tableWidget.setIndexWidget(index,self.buttons)
                
        for i in range(len(tags.tagList)):
            self.tableWidget.setRowHeight(i,36)
    
    def _handleAddButton(self):
        """Open a NewTagTypeDialog and create a new tag."""
        from . import dialogs
        tag = tagwidgets.NewTagTypeDialog.createTagType(tagname='',tagnameEditable=True,privateEditable=True)
        if tag is not None:
            self._loadTags()
    
    def _handleRemoveButton(self,tag):
        """Ask the user if he really wants this and if so, remove the tag."""
        number,allowChanges = self._appearsInElements(tag)
        if not allowChanges:
            dialogs.warning(self.tr("Cannot remove tag"),
                            self.tr("Cannot remove a tag that appears in elements."))
            return
        
        if dialogs.question(self.tr("Remove tag?"),
                            self.tr("Do you really want to remove the tag '{}'?").format(tag.name)):
            tags.removeTagType(tag)
            self._loadTags()

    def _handleItemChanged(self,item):
        """Handle changes to the name or private state of a tag."""
        if item.column() == self._getColumnIndex("name"):
            tag = tags.tagList[item.row()]
            oldName = tag.name
            newName = item.text()
            if oldName == newName:
                return
            number,allowChanges = self._appearsInElements(tag)
            # Perform different tests via a for-loop
            for check,message in (
                    (not allowChanges,self.tr("Cannot change a tag that appears in elements.")),
                    (tags.exists(newName),self.tr("A tag named '{}' already exists.").format(newName)),
                    (not tags.isValidTagname(newName),self.tr("'{}' is not a valid tagname.").format(newName))
                 ):
                 if check:
                    dialogs.warning(self.tr("Cannot change tag"),message)
                    item.setText(oldName) # Reset
                    return
            modify.push(modify.commands.TagTypeUndoCommand(tag,name=newName))
            self._loadTags()
                
        elif item.column() == self._getColumnIndex("private"): 
            tag = tags.tagList[item.row()]
            number,allowChanges = self._appearsInElements(tag)
            newPrivate = item.checkState() == Qt.Checked
            if newPrivate == tag.private:
                return
            if not allowChanges:
                dialogs.warning(self.tr("Cannot change tag"),
                                self.tr("Cannot change a tag that appears in elements."))
                item.setText(oldName)
                return
            modify.push(modify.commands.TagTypeUndoCommand(tag,private=newPrivate))
            self._loadTags()
                
    def _handleValueTypeChanged(self,tag,type):
        """Handle changes to the comboboxes containing valuetypes."""
        number,allowChanges = self._appearsInElements(tag)
        if not allowChanges:
            dialogs.warning(self.tr("Cannot change tag"),
                            self.tr("Cannot change a tag that appears in elements."))
            return
        modify.push(modify.commands.TagTypeUndoCommand(tag,valueType=type))
    
    def _handleCellDoubleClicked(self,row,column):
        """Handle double clicks on the first column containing icons. A click will open a file dialog to
        change the icon."""
        if column == self._getColumnIndex("icon"):
            tagType = tags.tagList[row]
            self._openIconDialog(tagType)
    
    def _handleCustomContextMenuRequested(self,pos):
        """React to customContextMenuRequested signals."""
        row = self.tableWidget.rowAt(pos.y())
        column = self.tableWidget.columnAt(pos.x())
        if column == self._getColumnIndex("icon") and row != -1:
            tagType = tags.tagList[row]
            menu = QtGui.QMenu(self.tableWidget)
            if tagType.iconPath is None:
                changeAction = QtGui.QAction(self.tr("Add icon..."),menu)
            else: changeAction = QtGui.QAction(self.tr("Change icon..."),menu)
            changeAction.triggered.connect(lambda: self._openIconDialog(tagType))
            menu.addAction(changeAction)
            removeAction = QtGui.QAction(self.tr("Remove icon"),menu)
            removeAction.triggered.connect(lambda: self._setIcon(tagType,None))
            menu.addAction(removeAction)
            menu.exec_(self.tableWidget.viewport().mapToGlobal(pos))
    
    def _openIconDialog(self,tagType):
        """Open a file dialog so that the user may choose an icon for the given tag."""
        # Choose a sensible directory as starting point
        if tagType.iconPath is None:
            dir = 'images/tags/'
        else: dir = tagType.iconPath
        fileName = QtGui.QFileDialog.getOpenFileName(self,self.tr("Choose tag icon"),dir,
                                                     self.tr("Images (*.png *.xpm *.jpg)"))
        if fileName:
            self._setIcon(tagType,fileName)
            
    def _setIcon(self,tagType,iconPath):
        """Set the icon(-path) of *tagType* to *iconPath* and update the GUI."""
        modify.push(modify.commands.TagTypeUndoCommand(tagType,iconPath=iconPath))
        # Update the widget
        row = tags.tagList.index(tagType)
        index = self.tableWidget.model().index(row,0)                     
        label = self.tableWidget.indexWidget(index)
        if tagType.icon is not None:
            label.setPixmap(tagType.icon.pixmap(32,32))
            label.setToolTip(tagType.iconPath)
        else:
            label.setPixmap(QtGui.QPixmap())
            label.setToolTip(None)
            
    def _appearsInElements(self,tag):
        """Return the number of db-elements that contain a tag of the given type in the database. As second 
        result return whether the user should be allowed to change the tag, i.e. whether the tag does not
        appear in any element in the database nor in the editor.
        """
        number = db.query("SELECT COUNT(DISTINCT element_id) FROM {}tags WHERE tag_id = ?"
                               .format(db.prefix),tag.id).getSingle()
        if number > 0:
            return number,False
        else:
            from omg.gui import editor
            for model in editor.activeEditorModels():
                if any(tag in node.tags for node in model.getRoot().getAllNodes(skipSelf=True)):
                    return 0,False
            return 0,True
        
    def _getColumnIndex(self,columnKey):
        """Return the index of the column with the given key (i.e. the first part of the corresponding tuple
        in self.columns."""
        for i in range(len(self.columns)):
            if self.columns[i][0] == columnKey:
                return i
        raise ValueError("Invalid key {}".format(columnKey))
    