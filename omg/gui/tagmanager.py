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


class TagManager(QtGui.QDialog):
    """The TagManager allows to add, edit and remove tagtypes (like artist, composer,...). To make things
    easy it only allows changing tagtypes which do not appear in any element."""
    def __init__(self,parent=None):
        QtGui.QDialog.__init__(self,parent)
        self.setWindowTitle(self.tr("TagManager - OMG {}").format(constants.VERSION))
        self.setLayout(QtGui.QVBoxLayout())
        
        self.layout().addWidget(QtGui.QLabel(self.tr("Note that you cannot change or remove tags that already appear in elements.")))
        
        self.scrollArea = QtGui.QScrollArea()
        self._loadTags()
        self.layout().addWidget(self.scrollArea)
        
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
        
    def _loadTags(self):
        """Load tag information from tags-module to GUI."""
        self.scrollView = QtGui.QWidget()
        layout = QtGui.QGridLayout()
        self.scrollView.setLayout(layout)
        
        # Header row
        for column,text in enumerate(
                    [self.tr("Name"),self.tr("Value-Type"),self.tr("Private?"),
                     self.tr("Sort-Tags"),self.tr("# of elements"),self.tr("Delete")]):
            label = QtGui.QLabel(text)
            layout.addWidget(label,0,column)
        
        # Data rows
        for row,tag in enumerate(tags.tagList):
            row += 1 # Due to the header row
            column = 0
            
            number = self._elementNumber(tag)
            
            layout.addWidget(tagwidgets.TagLabel(tag),row,column)
            
            column += 1
            combo = tagwidgets.ValueTypeBox(tag.type)
            combo.disableMouseWheel = True
            combo.typeChanged.connect(functools.partial(self._handleValueTypeChanged,tag))
            if number > 0:
                combo.setEnabled(False)
            layout.addWidget(combo,row,column)
            
            column += 1
            check = QtGui.QCheckBox()
            check.setCheckState(Qt.Checked if tag.private else Qt.Unchecked)
            check.stateChanged.connect(functools.partial(self._handlePrivateChanged,tag))
            if number > 0:
                check.setEnabled(False)
            layout.addWidget(check,row,column)
        
            column += 1
            layout.addWidget(QtGui.QLabel(', '.join(t.name for t in tag.sortTags)),row,column)
            
            column += 1
            layout.addWidget(QtGui.QLabel(str(number)))
            
            column += 1
            if number == 0:
                removeButton = QtGui.QToolButton()
                removeButton.setIcon(utils.getIcon('delete.png'))
                removeButton.clicked.connect(functools.partial(self._handleRemoveButton,tag))
                layout.addWidget(removeButton,row,column)
                
        self.scrollArea.setWidget(self.scrollView)
    
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
                                      QtGui.QMessageBox.No) \
                == QtGui.QMessageBox.Yes:
            tags.removeTagType(tag)
            self._loadTags()

    def _handlePrivateChanged(self,tag,state):
        if self._elementNumber(tag) > 0:
            QtGui.QMessageBox.warning(self,self.tr("Cannot change tag"),
                                      self.tr("Cannot change a tag that appears in elements."))
            return
        tags.changeTagType(tag,private= state == Qt.Checked)
    
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
    