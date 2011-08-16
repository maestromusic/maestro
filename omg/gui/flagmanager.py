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

from .. import database as db, constants, utils, flags


class FlagManager(QtGui.QDialog):
    def __init__(self,parent=None):
        QtGui.QDialog.__init__(self,parent)
        self.setWindowTitle(self.tr("FlagManager - OMG {}").format(constants.VERSION))
        self.setLayout(QtGui.QVBoxLayout())
        
        self.scrollArea = QtGui.QScrollArea()
        self._loadFlags()
        self.layout().addWidget(self.scrollArea)
        
        buttonBarLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(buttonBarLayout)
        
        addButton = QtGui.QPushButton(utils.getIcon("add.png"),self.tr("Add flag"))
        addButton.clicked.connect(self._handleAddButton)
        buttonBarLayout.addWidget(addButton)
        
        buttonBarLayout.addStretch(1)
        
        style = QtGui.QApplication.style()
        closeButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogCloseButton),
                                        self.tr("Close"))
        closeButton.clicked.connect(self.accept)
        buttonBarLayout.addWidget(closeButton)
        
    def _loadFlags(self):
        scrollView = QtGui.QWidget()
        layout = QtGui.QGridLayout()
        layout.setHorizontalSpacing(20)
        scrollView.setLayout(layout)
        
        result = db.query("""
                SELECT id,name,COUNT(element_id)
                FROM {0}flag_names LEFT JOIN {0}flags ON id = flag_id
                GROUP BY id
                """.format(db.prefix))
    
        # Header row
        for column,text in enumerate(
                    [self.tr("Name"),self.tr("# of elements"),self.tr("Delete")]):
            label = QtGui.QLabel(text)
            layout.addWidget(label,0,column)
            
        for i,row in enumerate(result):
            i += 1 # Due to the header row above
            id,name,count = row
            flagType = flags.FlagType(id,name)
            
            column = 0
            label = QtGui.QLabel(name)
            layout.addWidget(label,i,column)
            
            column += 1
            label = QtGui.QLabel(str(count))
            layout.addWidget(label,i,column)
            
            column += 1
            removeButton = QtGui.QToolButton()
            removeButton.setIcon(utils.getIcon('delete.png'))
            removeButton.clicked.connect(functools.partial(self._handleRemoveButton,flagType))
            layout.addWidget(removeButton,i,column)
            
        self.scrollArea.setWidget(scrollView)
    
    def _handleAddButton(self):
        name,ok = QtGui.QInputDialog.getText(self,self.tr("New Flag"),
                                             self.tr("Please enter the name of the new flag"))
        if not ok:
            return
        
        if flags.exists(name):
            QtGui.QMessageBox.warning(self,self.tr("Cannot create flag"),
                                      self.tr("This flag does already exist."))
        elif not flags.isValidFlagname(name):
            QtGui.QMessageBox.warning(self,self.tr("Invalid flagname"),
                                      self.tr("This is no a valid flagname."))
        else:
            flags.addFlagType(name)
            self._loadFlags()
    
    def _handleRemoveButton(self,flagType):
        """Ask the user if he really wants this and if so, remove the flag."""
        number = self._elementNumber(flagType)
        if number > 0:
            question = self.tr("Do you really want to remove the flag '{}'? It will be removed from %n element(s).",number)
        else: question = self.tr("Do you really want to remove the flag '{}'?")
        if (QtGui.QMessageBox.question(self,self.tr("Remove flag?"),
                                       question.format(flagType.name),
                                       QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
                                       QtGui.QMessageBox.No)
                == QtGui.QMessageBox.Yes):
            if number > 0:
                # TODO
                pass
            flags.removeFlagType(flagType)
            self._loadFlags()

    def _elementNumber(self,flagType):
        """Return the number of elements that contain a flag of the given type."""
        return db.query("SELECT COUNT(element_id) FROM {}flags WHERE flag_id = ?"
                            .format(db.prefix),flagType.id).getSingle()