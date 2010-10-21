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
from omg.gui import formatter, singletageditor
from omg.gui.misc import widgetlist, editorwidget

class TagEditorWidget(QtGui.QDialog):
    def __init__(self,parent,elements):
        QtGui.QDialog.__init__(self,parent)
        self.setWindowTitle("Tags editieren")
        
        self.model = tageditormodel.TagEditorModel(elements)
        self.model.tagRemoved.connect(self._handleTagRemoved)
        self.model.recordAdded.connect(self._handleRecordAdded)
        self.model.recordChanged.connect(self._handleRecordChanged)
        self.model.recordRemoved.connect(self._handleRecordRemoved)
        self.model.resetted.connect(self._handleReset)
        
        self.selectionManager = widgetlist.SelectionManager()
        
        self.addRecordAction = QtGui.QAction("Tag hinzufügen...",self)
        self.addRecordAction.triggered.connect(self._handleAddRecord)
        self.removeSelectedAction = QtGui.QAction("Ausgewählte entfernen",self)
        self.removeSelectedAction.triggered.connect(self._handleRemoveSelected)
        
        self.setLayout(QtGui.QVBoxLayout())
        self.tagEditorLayout = QtGui.QGridLayout()
        self.layout().addLayout(self.tagEditorLayout)
        self.layout().addStretch(1)
        buttonBarLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(buttonBarLayout,0)
        
        addButton = QtGui.QPushButton("Tag hinzufügen")
        addButton.clicked.connect(self._handleAddRecord)
        buttonBarLayout.addWidget(addButton)
        removeButton = QtGui.QPushButton("Ausgewählte entfernen")
        removeButton.clicked.connect(self._handleRemoveSelected)
        buttonBarLayout.addWidget(removeButton)
        buttonBarLayout.addStretch(1)
        resetButton = QtGui.QPushButton("Zurücksetzen")
        resetButton.clicked.connect(self.model.reset)
        buttonBarLayout.addWidget(resetButton)
        saveButton = QtGui.QPushButton("Speichern")
        buttonBarLayout.addWidget(saveButton)
        
        self.singleTagEditors = {}
        self.editorWidgets = {}
        for tag in self.model.getTags():
            self._addSingleTagEditor(tag)
    
    def _addSingleTagEditor(self,tag):
        row = self.tagEditorLayout.rowCount() # Count the empty rows, too (confer _removeSingleTagEditor)
        
        # Create the label (and the TagTypeBox beneath)
        # Create and fill the EditorWidget
        self.editorWidgets[tag] = QtGui.QLabel(tag.name)  #TODO use a TagTypeBox
        #self.editorWidgets[tag] = editorwidget.EditorWidget()
        #tagTypeLabel = QtGui.QLabel(tag.name)
        #self.editorWidgets[tag].setLabel(tagTypeLabel)
        #tagTypeBox = TagTypeBox(tag)
        #self.editorWidgets[tag].setEditor(tagTypeBox)
        
        # Create the Tag-Editor
        self.singleTagEditors[tag] = singletageditor.SingleTagEditor(tag,self.model)
        self.singleTagEditors[tag].widgetList.setSelectionManager(self.selectionManager)
        self.tagEditorLayout.addWidget(self.editorWidgets[tag],row,0)
        self.tagEditorLayout.addWidget(self.singleTagEditors[tag],row,1)

    def _removeSingleTagEditor(self,tag):
        # Warning: Removing items from a QGridLayout does not move the other items. Thus, after this method there is an empty row in the layout.
        editorWidget = self.editorWidgets[tag]
        self.tagEditorLayout.removeWidget(editorWidget)
        editorWidget.setParent(None)
        del self.editorWidgets[tag]
        tagEditor = self.singleTagEditors[tag]
        self.tagEditorLayout.removeWidget(tagEditor)
        tagEditor.widgetList.setSelectionManager(None)
        tagEditor.setParent(None)
        del self.singleTagEditors[tag]

    def _handleReset(self):
        for tag in list(self.singleTagEditors.keys()): # dict will change
            self._removeSingleTagEditor(tag)
        for tag in self.model.getTags():
            self._addSingleTagEditor(tag)
        
    def _handleAddRecord(self):
        dialog = TagDialog(self,self.model.elements)
        if dialog.exec_() == QtGui.QDialog.Accepted:
            self.model.addRecord(dialog.getRecord())
            self.updateGeometry()

    def _handleRemoveSelected(self):
        for tagValueEditor in self.selectionManager.getSelectedWidgets():
            self.model.removeRecord(tagValueEditor.getRecord())
        
    # Note that the following _handle-functions only add new SingleTagEditors or remove SingleTagEditors which have become empty. Unless they are newly created or removed, the editors are updated in their own _handle-functions.
    def _handleTagRemoved(self,tag):
        self._removeSingleTagEditor(tag)
        
    def _handleRecordAdded(self,record):
        if record.tag not in self.singleTagEditors:
            self._addSingleTagEditor(record.tag)
        else: pass # The already existing SingleTagEditor will deal with it
    
    def _handleRecordChanged(self,oldRecord,newRecord):
        if oldRecord.tag != newRecord.tag:
            self._handleRecordRemoved(oldRecord)
            self._handleRecordAdded(newRecord)
        else: pass # The SingleTagEditor will deal with it
        
    def _handleRecordRemoved(self,record):
        if record.tag not in self.model.getTags():
            self._removeSingleTagEditor(record.tag)
        else: pass # The SingleTagEditor will deal with it
            
    def contextMenuEvent(self, event):
        menu = QtGui.QMenu(self)
        menu.addAction(self.addRecordAction)
        menu.addAction(self.removeSelectedAction)
        selectedRecords = [editor.getRecord() for editor in self.selectionManager.getSelectedWidgets()]
        for separator in self.model.getPossibleSeparators(selectedRecords):
            action = menu.addAction("Bei '{}' trennen".format(separator))
            action.triggered.connect(lambda: self.model.splitMany(selectedRecords,separator))
        menu.popup(event.globalPos())
        
        
class TagDialog(QtGui.QDialog):
    def __init__(self,parent,elements):
        QtGui.QDialog.__init__(self,parent)
        self.setWindowTitle("Tag-Wert hinzufügen")
        assert len(elements) > 0
        
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
        okButton.clicked.connect(self._handleOkButton)
        
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
    
    def _handleOkButton(self):
        if self.elementsBox.selectionModel().hasSelection():
            try:
                tag = self.typeEditor.getTag()
            except ValueError:
                QtGui.QMessageBox.warning(self,"Ungültiger Tagname.",
                                          "Ungültiger Tagname. Tagnamen dürfen nur Zahlen und Buchstaben enthalten.")
            else:
                if tag.isValid(self.valueEditor.text()):
                    self.accept()
                else: QtGui.QMessageBox.warning(self,"Ungültiger Wert","Der eingegebene Wert ist ungültig.")
        else: QtGui.QMessageBox.warning(self,"Kein Stück ausgewählt.","Du musst mindestens ein Stück auswählen.")
        
    def getRecord(self):
        allElements = self.elementsBox.model().getItems()
        selectedElements = [allElements[i] for i in range(len(allElements))
                                if self.elementsBox.selectionModel().isRowSelected(i,QtCore.QModelIndex())]
        return tageditormodel.Record(self.typeEditor.getTag(),self.valueEditor.text(),allElements,selectedElements)


class TagTypeBox(QtGui.QComboBox):
    def __init__(self,defaultTag = None,parent=None):
        QtGui.QComboBox.__init__(self,parent)
        self.setEditable(True)
        self.setInsertPolicy(QtGui.QComboBox.NoInsert)
        if defaultTag is None:
            self.setEditText('')
        
        for tag in tags.tagList:
            if tag.iconPath() is not None:
                self.addItem(QtGui.QIcon(tag.iconPath()),tag.translated())
            else: self.addItem(tag.translated())
            if tag == defaultTag:
                self.setCurrentIndex(self.count()-1)
                
    def getTag(self):
        text = self.currentText().strip()
        if text[0] == text[-1] and text[0] in ['"',"'"]: # Don't translate if the text is quoted
            return tags.get(text[1:-1])
        else: return tags.fromTranslation(text)
        
