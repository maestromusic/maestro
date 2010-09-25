#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#
import os.path
import functools

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from omg import constants, tags
from omg.models import tageditormodel, simplelistmodel
from . import formatter, singletageditor

class TagEditorWidget(QtGui.QDialog):
    def __init__(self,parent,elements):
        QtGui.QDialog.__init__(self,parent)
        self.setWindowTitle("Tags editieren")
        
        self.originalElements = elements
        self.model = tageditormodel.TagEditorModel(elements)
        
        self.setLayout(QtGui.QVBoxLayout())
        self.tagEditorLayout = QtGui.QFormLayout()
        self.layout().addLayout(self.tagEditorLayout,1)
        buttonBarLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(buttonBarLayout,0)
        
        addButton = QtGui.QPushButton("Tag hinzufügen")
        addButton.clicked.connect(self._handleAddButton)
        buttonBarLayout.addWidget(addButton)
        removeButton = QtGui.QPushButton("Tag entfernen")
        buttonBarLayout.addWidget(removeButton)
        buttonBarLayout.addStretch(1)
        resetButton = QtGui.QPushButton("Zurücksetzen")
        buttonBarLayout.addWidget(resetButton)
        saveButton = QtGui.QPushButton("Speichern")
        buttonBarLayout.addWidget(saveButton)

        for tag in self.model.getTags():
            self.tagEditorLayout.addRow("{0}:".format(str(tag)),singletageditor.SingleTagEditor(tag,self.model))

    def _handleAddButton(self):
        dialog = TagDialog(self,self.model.elements)
        if dialog.exec_() == QtGui.QDialog.Accepted:
            self.model.addRecords(dialog.getRecords())
            self.updateGeometry()


class TagDialog(QtGui.QDialog):
    def __init__(self,parent,elements):
        QtGui.QDialog.__init__(self,parent)
        self.setWindowTitle("Tag-Wert hinzufügen")
        
        self.typeEditor = TagTypeBox(self)
        self.valueEditor = QtGui.QLineEdit(self)
        self.elementsBox = QtGui.QListView(self)
        # Use a formatter to print the title of the elements
        self.elementsBox.setModel(simplelistmodel.SimpleListModel(elements,lambda el: formatter.Formatter(el).title()))
        self.elementsBox.setSelectionMode(QtGui.QAbstractItemView.MultiSelection)
        for i in range(len(elements)):
            self.elementsBox.selectionModel().select(self.elementsBox.model().index(i,0),QtGui.QItemSelectionModel.Select)
        abortButton = QtGui.QPushButton("Abbrechen",self)
        abortButton.clicked.connect(self.reject)
        okButton = QtGui.QPushButton("OK",self)
        okButton.clicked.connect(self.accept)
        
        layout = QtGui.QVBoxLayout()
        self.setLayout(layout)
        firstLineLayout = QtGui.QHBoxLayout()
        secondLineLayout = QtGui.QHBoxLayout()
        layout.addLayout(firstLineLayout)
        layout.addLayout(secondLineLayout)
        firstLineLayout.addWidget(QtGui.QLabel("Typ: ",self))
        firstLineLayout.addWidget(self.typeEditor)
        firstLineLayout.addStretch(1)
        secondLineLayout.addWidget(QtGui.QLabel("Wert: ",self))
        secondLineLayout.addWidget(self.valueEditor)
        layout.addWidget(QtGui.QLabel("Elemente: ",self))
        layout.addWidget(self.elementsBox)
        lastLineLayout = QtGui.QHBoxLayout()
        lastLineLayout.addStretch(1)
        lastLineLayout.addWidget(abortButton,0)
        lastLineLayout.addWidget(okButton,0)
        layout.addLayout(lastLineLayout)
        
    def getRecords(self):
        # TODO: Don't ignore the selection in self.elementsBox
        return [tageditormodel.Record(self.typeEditor.getTag(),self.valueEditor.text(),self.elementsBox.model().getItems(),self.elementsBox.model().getItems())]
                            

class TagTypeBox(QtGui.QComboBox):
    def __init__(self,defaultTag = None,parent=None):
        QtGui.QComboBox.__init__(self,parent)
        self.setEditable(True)
        if defaultTag is None:
            self.setEditText('')
        
        for tag in tags.tagList:
            self.addItem(str(tag))
            if tag == defaultTag:
                self.setCurrentIndex(self.count()-1)
                
    def getTag(self):
        return tags.get("album") # TODO: Didn't know how the function to get the text is called