#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#

import functools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import tags, utils, database as db, constants
from . import tagwidgets
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
        self.tableWidget.setColumnCount(6)
        self.tableWidget.verticalHeader().hide()
        # TODO: Does not work
        #self.tableWidget.setSortingEnabled(True)
        self.tableWidget.horizontalHeader().setResizeMode(QtGui.QHeaderView.ResizeToContents)
        self.tableWidget.itemChanged.connect(self._handleItemChanged)
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
                    [self.tr("Name"),self.tr("Value-Type"),self.tr("Private?"),
                     self.tr("Sort-Tags"),self.tr("# of elements"),self.tr("Actions")])
        self.tableWidget.setRowCount(len(tags.tagList))
        
        for row,tag in enumerate(tags.tagList):
            column = 0
            number = self._elementNumber(tag)
            
            item = QtGui.QTableWidgetItem(tag.name)
            item.setData(Qt.UserRole,tag)
            if tag.iconPath() is not None:
                item.setIcon(QtGui.QIcon(tag.iconPath()))
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
            item.setData(Qt.UserRole,tag)
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
    
    def _handleAddButton(self):
        """Open a NewTagTypeDialog and create a new tag."""
        from . import dialogs
        tag = tagwidgets.NewTagTypeDialog.createTagType(tagname='',tagnameEditable=True,privateEditable=True)
        if tag is not None:
            self._loadTags()
    
    def _handleRemoveButton(self,tag):
        """Ask the user if he really wants this and if so, remove the tag."""
        if self._elementNumber(tag) > 0:
            QtGui.QMessageBox.warning(self,self.tr("Cannot remove tag"),
                                      self.tr("Cannot remove a tag that appears in elements."))
            return
        
        if QtGui.QMessageBox.question(self,self.tr("Remove tag?"),
                                      self.tr("Do you really want to remove the tag '{}'?").format(tag.name),
                                      QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
                                      QtGui.QMessageBox.Yes) \
                == QtGui.QMessageBox.Yes:
            tags.removeTagType(tag)
            self._loadTags()

    def _handleItemChanged(self,item):
        if item.column() == 0:
            tag = item.data(Qt.UserRole)
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
                    QtGui.QMessageBox.warning(self,self.tr("Cannot change tag"),message)
                    item.setText(oldName) # Reset
                    return
            tags.changeTagType(tag,name=newName)
            self._loadTags()
                
        elif item.column() == 2: 
            tag = item.data(Qt.UserRole)
            newPrivate = item.checkState() == Qt.Checked
            if newPrivate == tag.private:
                return
            if self._elementNumber(tag) > 0:
                QtGui.QMessageBox.warning(self,self.tr("Cannot change tag"),
                                          self.tr("Cannot change a tag that appears in elements."))
                item.setText(oldName)
                return
            tags.changeTagType(tag,private=newPrivate)
            self._loadTags()
    
    def _handleValueTypeChanged(self,tag,type):
        if self._elementNumber(tag) > 0:
            QtGui.QMessageBox.warning(self,self.tr("Cannot change tag"),
                                      self.tr("Cannot change a tag that appears in elements."))
            return
        tags.changeTagType(tag,valueType=type)
        
    def _elementNumber(self,tag):
        """Return the number of elements that contain a tag of the given type."""
        return db.query("SELECT COUNT(DISTINCT element_id) FROM {}tags WHERE tag_id = ?"
                               .format(db.prefix),tag.id).getSingle()
    