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

from .. import tags, utils, database as db, constants
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
        
        self.tableWidget = QtGui.QTableWidget()
        self.tableWidget.setColumnCount(7)
        self.tableWidget.verticalHeader().hide()
        # TODO: Does not work
        #self.tableWidget.setSortingEnabled(True)
        self.tableWidget.horizontalHeader().setResizeMode(QtGui.QHeaderView.ResizeToContents)
        self.tableWidget.itemChanged.connect(self._handleItemChanged)
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
        
    def _loadTags(self):
        """Load tag information from tags-module to GUI."""
        self.tableWidget.clear()
        self.tableWidget.setHorizontalHeaderLabels(
                    [self.tr("Icon"),self.tr("Name"),self.tr("Value-Type"),self.tr("Private?"),
                     self.tr("Sort-Tags"),self.tr("# of elements"),self.tr("Actions")])
        self.tableWidget.setRowCount(len(tags.tagList))
        
        for row,tag in enumerate(tags.tagList):
            number = self._elementNumber(tag)
            
            column = 0
            label = QtGui.QLabel()       
            label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            index = self.tableWidget.model().index(row,column)   
            self.tableWidget.setIndexWidget(index,label)
            if tag.iconPath is not None:
                label.setPixmap(tag.icon.pixmap(32,32))
                label.setToolTip(tag.iconPath)     
            
            column += 1
            item = QtGui.QTableWidgetItem(tag.name)
            if number == 0:
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable)
            else: item.setFlags(Qt.ItemIsEnabled)
            self.tableWidget.setItem(row,column,item)
            
            column += 1
            if number == 0:
                combo = tagwidgets.ValueTypeBox(tag.type)
                combo.disableMouseWheel = True
                combo.typeChanged.connect(functools.partial(self._handleValueTypeChanged,tag))
                index = self.tableWidget.model().index(row,column)  
                self.tableWidget.setIndexWidget(index,combo)
            else:
                item = QtGui.QTableWidgetItem(tag.type.name)
                item.setFlags(Qt.ItemIsEnabled)
                self.tableWidget.setItem(row,column,item)
            
            column += 1
            item = QtGui.QTableWidgetItem()
            if number == 0:
                item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            else: item.setFlags(Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if tag.private else Qt.Unchecked)
            #check.stateChanged.connect(functools.partial(self._handlePrivateChanged,tag))
            self.tableWidget.setItem(row,column,item)
        
            column += 1
            item = QtGui.QTableWidgetItem(', '.join(t.name for t in tag.sortTags))
            item.setFlags(Qt.ItemIsEnabled)
            self.tableWidget.setItem(row,column,item)
            
            column += 1
            item = QtGui.QTableWidgetItem('{}    '.format(number))
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
            item.setFlags(Qt.ItemIsEnabled)
            self.tableWidget.setItem(row,column,item)
            
            column += 1
            if number == 0:
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
        if self._elementNumber(tag) > 0:
            dialogs.warning(self.tr("Cannot remove tag"),
                            self.tr("Cannot remove a tag that appears in elements."))
            return
        
        if dialogs.question(self.tr("Remove tag?"),
                            self.tr("Do you really want to remove the tag '{}'?").format(tag.name)):
            tags.removeTagType(tag)
            self._loadTags()

    def _handleItemChanged(self,item):
        """Handle changes to the name or private state of a tag."""
        if item.column() == 1:
            tag = tags.tagList[item.row()]
            oldName = tag.name
            newName = item.text()
            if oldName == newName:
                return
            number = self._elementNumber(tag)
            for check,message in (
                    (number > 0,self.tr("Cannot change a tag that appears in elements.")),
                    (tags.exists(newName),self.tr("A tag named '{}' already exists.").format(newName)),
                    (not tags.isValidTagname(newName),self.tr("'{}' is not a valid tagname.").format(newName))
                 ):
                 if check:
                    dialogs.warning(self.tr("Cannot change tag"),message)
                    item.setText(oldName) # Reset
                    return
            tags.changeTagType(tag,name=newName)
            self._loadTags()
                
        elif item.column() == 2: 
            tag = tags.tagList[item.row()]
            newPrivate = item.checkState() == Qt.Checked
            if newPrivate == tag.private:
                return
            if self._elementNumber(tag) > 0:
                dialogs.warning(self.tr("Cannot change tag"),
                                self.tr("Cannot change a tag that appears in elements."))
                item.setText(oldName)
                return
            tags.changeTagType(tag,private=newPrivate)
            self._loadTags()
                
    def _handleValueTypeChanged(self,tag,type):
        """Handle changes to the comboboxes containing valuetypes."""
        if self._elementNumber(tag) > 0:
            dialogs.warning(self.tr("Cannot change tag"),
                            self.tr("Cannot change a tag that appears in elements."))
            return
        tags.changeTagType(tag,valueType=type)
    
    def _handleCellDoubleClicked(self,row,column):
        """Handle double clicks on the first column containing icons. A click will open a file dialog to
        change the icon."""
        if column == 0:
            tagType = tags.tagList[row]
            self._openIconDialog(tagType)
    
    def _handleCustomContextMenuRequested(self,pos):
        """React to customContextMenuRequested signals."""
        row = self.tableWidget.rowAt(pos.y())
        column = self.tableWidget.columnAt(pos.x())
        if column == 0 and row != -1:
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
        tags.changeTagType(tagType,iconPath=iconPath)
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
            
    def _elementNumber(self,tag):
        """Return the number of elements that contain a tag of the given type."""
        return db.query("SELECT COUNT(DISTINCT element_id) FROM {}tags WHERE tag_id = ?"
                               .format(db.prefix),tag.id).getSingle()
    