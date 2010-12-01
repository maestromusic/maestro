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
from omg.gui import formatter, singletageditor, dialogs
from omg.gui.misc import widgetlist, editorwidget, tagwidgets

class TagEditorWidget(QtGui.QDialog):
    def __init__(self,parent,elements):
        QtGui.QDialog.__init__(self,parent)
        self.setWindowTitle("Tags editieren")
        
        self.model = tageditormodel.TagEditorModel(elements)
        self.model.tagChanged.connect(self._handleTagChanged)
        self.model.tagRemoved.connect(self._handleTagRemoved)
        self.model.recordAdded.connect(self._handleRecordAdded)
        self.model.recordChanged.connect(self._handleRecordChanged)
        self.model.recordRemoved.connect(self._handleRecordRemoved)
        self.model.resetted.connect(self._handleReset)
        
        self.selectionManager = widgetlist.SelectionManager()
        # Do not allow the user to select VariousLines
        self.selectionManager.isSelectable = lambda wList,widget: not isinstance(widget,singletageditor.VariousLine)
        
        self.addRecordAction = QtGui.QAction("Tag hinzufügen...",self)
        self.addRecordAction.triggered.connect(self._handleAddRecord)
        self.removeSelectedAction = QtGui.QAction("Ausgewählte entfernen",self)
        self.removeSelectedAction.triggered.connect(self._handleRemoveSelected)
        
        self.recursiveBox = QtGui.QCheckBox("Änderungen rekursive auf Unterelemente anwenden")
        self.recursiveBox.setChecked(True)
        
        self.setLayout(QtGui.QVBoxLayout())
        self.layout().addWidget(self.recursiveBox)
        self.tagEditorLayout = QtGui.QGridLayout()
        self.tagEditorLayout.setColumnStretch(1,1) # Stretch the column holding the values
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
        saveButton.clicked.connect(self._handleSave)
        buttonBarLayout.addWidget(saveButton)
        
        self.singleTagEditors = {}
        self.editorWidgets = {}
        for tag in self.model.getTags():
            self._addSingleTagEditor(tag)
    
    def _addSingleTagEditor(self,tag):
        row = self.tagEditorLayout.rowCount() # Count the empty rows, too (confer _removeSingleTagEditor)
        
        # Create and fill the EditorWidget
        label = tagwidgets.TagLabel(tag)
        label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.editorWidgets[tag] = editorwidget.EditorWidget(label=label)
        tagBox = tagwidgets.TagTypeBox(tag)
        self.editorWidgets[tag].setEditor(tagBox)
        #~ self.editorWidgets[tag].setLabel(tagwidgets.TagLabel(tag))
        self.editorWidgets[tag].valueChanged.connect(self._handleTagChangedByUser)
        
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
            if tagValueEditor.isVisible():
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

    def _handleTagChanged(self,oldTag,newTag):
        for adict in (self.editorWidgets,self.singleTagEditors):
            # Change key from oldTag to newTag
            widget = adict[oldTag]
            del adict[oldTag]
            assert newTag not in adict
            adict[newTag] = widget

    def _handleTagChangedByUser(self,value):
        # First we have to get the editorWidget responsible for this event and its tag
        editorWidget = self.sender()
        oldTag = None
        for tag,widget in self.editorWidgets.items():
            if widget == editorWidget:
                oldTag = tag
                break
        assert oldTag is not None
        newTag = editorWidget.getEditor().getTag()
        if not newTag.isIndexed():
            tagType = dialogs.NewTagDialog.queryTagType(newTag.name)
            if tagType:
                newTag = tags.addIndexedTag(newTag.name,tagType)
            else: newTag = None

        # In other words: If either newTag is None or changeTag fails, then reset the editor
        if newTag is None or not self.model.changeTag(oldTag,newTag):
            QtGui.QMessageBox.warning(self,"Ungültiger Wert","Mindestens ein Wert ist ungültig.")
            # reset the editor...unfortunately this emits valueChanged again
            editorWidget.valueChanged.disconnect(self._handleTagChangedByUser)
            self.editorWidgets[oldTag].setValue(oldTag.translated())
            editorWidget.valueChanged.connect(self._handleTagChangedByUser)
        
    def _handleSave(self):
        self.model.save(self.recursiveBox.isChecked())
        self.accept()
        
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
        
        self.typeEditor =  tagwidgets.TagTypeBox(self)
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
                if not tag.isIndexed():
                    tagType = dialogs.NewTagDialog.queryTagType(tag.name)
                    if tagType:
                        tag = tags.addIndexedTag(tag.name,tagType)
                    else: return # Do nothing (in particular do not close the dialog)
                if tag.isValid(self.valueEditor.text()):
                    self.accept()
                else: QtGui.QMessageBox.warning(self,"Ungültiger Wert","Der eingegebene Wert ist ungültig.")
        else: QtGui.QMessageBox.warning(self,"Kein Stück ausgewählt.","Du musst mindestens ein Stück auswählen.")
        
    def getRecord(self):
        allElements = self.elementsBox.model().getItems()
        selectedElements = [allElements[i] for i in range(len(allElements))
                                if self.elementsBox.selectionModel().isRowSelected(i,QtCore.QModelIndex())]
        return tageditormodel.Record(self.typeEditor.getTag(),self.valueEditor.text(),allElements,selectedElements)
