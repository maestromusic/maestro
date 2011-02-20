#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#
from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from omg import constants, tags, getIcon, strutils
from omg.models import tageditormodel, simplelistmodel
from omg.gui import formatter, singletageditor, dialogs, tagwidgets
from omg.gui.misc import widgetlist, editorwidget, dynamicgridlayout


class TagEditorDialog(QtGui.QDialog):
    def __init__(self, parent, elements):
        QtGui.QDialog.__init__(self,parent)
        self.setLayout(QtGui.QVBoxLayout())
        self.tagedit = TagEditorWidget(elements,dialog=self)
        self.layout().addWidget(self.tagedit)
        self.setWindowTitle(self.tr("Edit tags"))
        self.resize(600,450) #TODO: klüger
        self.tagedit.saved.connect(self.accept)
        
        
class TagEditorWidget(QtGui.QWidget):
    
    saved = QtCore.pyqtSignal()
    
    def __init__(self,elements = [],parent = None,dialog=None):
        QtGui.QWidget.__init__(self,parent)
        style = QtGui.QApplication.style()
        
        self.model = tageditormodel.TagEditorModel(elements)
        self.model.tagInserted.connect(self._handleTagInserted)
        self.model.tagRemoved.connect(self._handleTagRemoved)
        self.model.tagChanged.connect(self._handleTagChanged)
        self.model.resetted.connect(self._handleReset)

        self.undoAction = self.model.undoStack.createUndoAction(self,self.tr("Undo"))
        self.redoAction = self.model.undoStack.createRedoAction(self,self.tr("Redo"))

        self.selectionManager = widgetlist.SelectionManager()
        # Do not allow the user to select ExpandLines
        self.selectionManager.isSelectable = lambda wList,widget: not isinstance(widget,singletageditor.ExpandLine)
        
        self.setLayout(QtGui.QVBoxLayout())
        label = QtGui.QLabel(self.tr("Edit tags of %n element(s).","",len(elements)))
        self.layout().addWidget(label)
        self.scrollArea = QtGui.QScrollArea()
        self.scrollArea.setWidgetResizable(True)
        self.layout().addWidget(self.scrollArea)
        buttonBarLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(buttonBarLayout,0)

        addButton = QtGui.QPushButton(QtGui.QIcon(getIcon("add.png")),self.tr("Add tag"))
        addButton.clicked.connect(self._handleAddRecord)
        buttonBarLayout.addWidget(addButton)
        removeButton = QtGui.QPushButton(QtGui.QIcon(getIcon("remove.png")),self.tr("Remove selected"))
        removeButton.clicked.connect(self._handleRemoveSelected)
        buttonBarLayout.addWidget(removeButton)
        buttonBarLayout.addStretch(1)
        if dialog is not None:
            resetButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogResetButton),self.tr("Reset"))
            resetButton.clicked.connect(self.model.reset)
            buttonBarLayout.addWidget(resetButton)
            cancelButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogCancelButton),self.tr("Cancel"))
            cancelButton.clicked.connect(dialog.reject)
            buttonBarLayout.addWidget(cancelButton)
            saveButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogSaveButton),self.tr("Save"))
            saveButton.clicked.connect(self._handleSave)
            buttonBarLayout.addWidget(saveButton)

        self.viewport = QtGui.QWidget()
        self.viewport.setLayout(QtGui.QVBoxLayout())
        self.tagEditorLayout = dynamicgridlayout.DynamicGridLayout()
        self.tagEditorLayout.setColumnStretch(1,1) # Stretch the column holding the values
        self.viewport.layout().addLayout(self.tagEditorLayout)
        self.viewport.layout().addStretch(1)
        self.scrollArea.setWidget(self.viewport)

        self.singleTagEditors = {}
        self.editorWidgets = {}
        for tag in self.model.getTags():
            self._insertSingleTagEditor(len(self.singleTagEditors),tag)
         
    def _insertSingleTagEditor(self,row,tag):
        self.tagEditorLayout.insertRow(row)

        # Create and fill the EditorWidget
        label = tagwidgets.TagLabel(tag)
        label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        tagBox = tagwidgets.TagTypeBox(tag)
        self.editorWidgets[tag] = editorwidget.EditorWidget(editor=tagBox,label=label)
        self.editorWidgets[tag].valueChanged.connect(self._handleTagChangedByUser)
        self.tagEditorLayout.addWidget(self.editorWidgets[tag],row,0)
        
        # Create the Tag-Editor
        self.singleTagEditors[tag] = singletageditor.SingleTagEditor(self,tag,self.model)
        self.singleTagEditors[tag].widgetList.setSelectionManager(self.selectionManager)
        self.tagEditorLayout.addWidget(self.singleTagEditors[tag],row,1)

    def _removeSingleTagEditor(self,tag):
        # Simply removing the items would leave an empty row. Thus we use DynamicGridLayout.removeRow.
        # First we have to find the row
        row = None
        for r in range(self.tagEditorLayout.rowCount()):
            if self.tagEditorLayout.itemAtPosition(r,0).widget() == self.editorWidgets[tag]:
                row = r
                break
        assert row is not None
        self.tagEditorLayout.removeRow(row)

        # Tidy up
        self.editorWidgets[tag].setParent(None)
        del self.editorWidgets[tag]
        tagEditor = self.singleTagEditors[tag]
        tagEditor.widgetList.setSelectionManager(None)
        tagEditor.setParent(None)
        del self.singleTagEditors[tag]

    def _handleReset(self):
        for tag in list(self.singleTagEditors.keys()): # dict will change
            self._removeSingleTagEditor(tag)
        for tag in self.model.getTags():
            self._insertSingleTagEditor(len(self.singleTagEditors),tag)
        
    def _handleAddRecord(self,tag=None):
        dialog = TagDialog(self,self.model.getElements(),tag)
        if dialog.exec_() == QtGui.QDialog.Accepted:
            self.model.addRecord(dialog.getRecord())

    def _handleRemoveSelected(self):
        records = [re.getRecord() for re in self.selectionManager.getSelectedWidgets() if re.isVisible()]
        if len(records) > 0:
            self.model.removeRecords(records)

    # Note that the following _handle-functions only add new SingleTagEditors or remove SingleTagEditors which have become empty. Unless they are newly created or removed, the editors are updated in their own _handle-functions.
    def _handleTagInserted(self,pos,tag):
        self._insertSingleTagEditor(pos,tag)
        
    def _handleTagRemoved(self,tag):
        self._removeSingleTagEditor(tag)

    def _handleTagChanged(self,oldTag,newTag):
        for adict in (self.editorWidgets,self.singleTagEditors):
            # Change key from oldTag to newTag
            widget = adict[oldTag]
            del adict[oldTag]
            assert newTag not in adict
            adict[newTag] = widget
        self.editorWidgets[newTag].setValue(newTag.translated())

    def _handleTagChangedByUser(self):
        # First we have to get the editorWidget responsible for this event and its tag
        editorWidget = self.sender()
        oldTag = None
        for tag,widget in self.editorWidgets.items():
            if widget == editorWidget:
                oldTag = tag
                break
        assert oldTag is not None
        newTag = editorWidget.getEditor().getTag()

        # If it's a new tag query the type and write to the tagids-table
        if not newTag.isIndexed():
            tagType = dialogs.NewTagDialog.queryTagType(newTag.name)
            if tagType:
                newTag = tags.addIndexedTag(newTag.name,tagType)
            else: newTag = None

        # In other words: If either newTag is None or changeTag fails, then reset the editor
        if newTag is None or not self.model.changeTag(oldTag,newTag):
            QtGui.QMessageBox.warning(self,self.tr("Invalid value"),self.tr("At least one value is invalid for the new type."))
            # reset the editor...unfortunately this emits valueChanged again
            editorWidget.valueChanged.disconnect(self._handleTagChangedByUser)
            self.editorWidgets[oldTag].setValue(oldTag.translated())
            editorWidget.valueChanged.connect(self._handleTagChangedByUser)
        
    def _handleSave(self):
        if not all(singleTagEditor.isValid() for singleTagEditor in self.singleTagEditors.values()):
            QtGui.QMessageBox.warning(self,self.tr("Invalid value"),self.tr("At least one value is invalid."))
        else:
            self.model.save()
            self.saved.emit()
        
    def contextMenuEvent(self,contextMenuEvent,tag=None):
        menu = QtGui.QMenu(self)

        menu.addAction(self.undoAction)
        menu.addAction(self.redoAction)
        menu.addSeparator()
        
        addRecordAction = QtGui.QAction(self.tr("Add tag..."),self)
        addRecordAction.triggered.connect(lambda: self._handleAddRecord(tag))
        menu.addAction(addRecordAction)
        
        removeSelectedAction = QtGui.QAction(self.tr("Remove selected"),self)
        removeSelectedAction.triggered.connect(self._handleRemoveSelected)
        menu.addAction(removeSelectedAction)

        selectedRecords = [editor.getRecord() for editor in self.selectionManager.getSelectedWidgets()]

        if len(selectedRecords) > 0 and len(strutils.commonPrefix(str(record.value) for record in selectedRecords)) > 0:
            action = menu.addAction(self.tr("Edit common start..."))
            action.triggered.connect(self._editCommonStart)

        for separator in self.model.getPossibleSeparators(selectedRecords):
            action = menu.addAction(self.tr("Separate at '{}'").format(separator))
            action.triggered.connect(lambda: self.model.splitMany(selectedRecords,separator))

        menu.popup(contextMenuEvent.globalPos())

    def _editCommonStart(self):
        selectedRecords = [editor.getRecord() for editor in self.selectionManager.getSelectedWidgets()]
        commonStart = strutils.commonPrefix(str(record.value) for record in selectedRecords)
        text,ok = QtGui.QInputDialog.getText (self,self.tr("Edit common start"),
                                              self.tr("Insert a new text will replace the common start of all selected records:"),text=commonStart)
        if ok:
            self.model.replaceCommonStart(selectedRecords,text)
        

class TagDialog(QtGui.QDialog):
    def __init__(self,parent,elements,tag=None):
        QtGui.QDialog.__init__(self,parent)
        self.setWindowTitle(self.tr("Add tag value"))
        assert len(elements) > 0
        
        self.typeEditor =  tagwidgets.TagTypeBox(defaultTag=tag)
        self.typeEditor.currentIndexChanged.connect(self._handleTagChanged)
        self.valueEditor = tagwidgets.TagValueEditor(self.typeEditor.getTag())
        self.elementsBox = QtGui.QListView(self)
        # Use a formatter to print the title of the elements
        self.elementsBox.setModel(simplelistmodel.SimpleListModel(elements,lambda el: formatter.Formatter(el).title()))
        self.elementsBox.setSelectionMode(QtGui.QAbstractItemView.MultiSelection)
        for i in range(len(elements)):
            self.elementsBox.selectionModel().select(self.elementsBox.model().index(i,0),
                                                     QtGui.QItemSelectionModel.Select)
        abortButton = QtGui.QPushButton(self.tr("Cancel"),self)
        abortButton.clicked.connect(self.reject)
        okButton = QtGui.QPushButton(self.tr("OK"),self)
        okButton.clicked.connect(self._handleOkButton)
        
        layout = QtGui.QVBoxLayout()
        self.setLayout(layout)
        firstLineLayout = QtGui.QHBoxLayout()
        secondLineLayout = QtGui.QHBoxLayout()
        layout.addLayout(firstLineLayout)
        layout.addLayout(secondLineLayout)
        firstLineLayout.addWidget(QtGui.QLabel(self.tr("Type: "),self))
        firstLineLayout.addWidget(self.typeEditor)
        firstLineLayout.addStretch(1)
        secondLineLayout.addWidget(QtGui.QLabel(self.tr("Value: "),self))
        secondLineLayout.addWidget(self.valueEditor)
        layout.addWidget(QtGui.QLabel(self.tr("Elements: "),self))
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
                QtGui.QMessageBox.warning(self,self.tr("Invalid tag name"),
                                          self.tr("Invalid tag name. Tag name must contain only letters and digits."))
            else:
                if not tag.isIndexed():
                    tagType = dialogs.NewTagDialog.queryTagType(tag.name)
                    if tagType:
                        tag = tags.addIndexedTag(tag.name,tagType)
                    else: return # Do nothing (in particular do not close the dialog)
                if self.valueEditor.getValue() is not None:
                    self.accept()
                else: QtGui.QMessageBox.warning(self,self.tr("Invalid value"),self.tr("The given value is invalid."))
        else: QtGui.QMessageBox.warning(self,self.tr("No element selected"),
                                        self.tr("You must select at lest one element."))
        
    def getRecord(self):
        allElements = self.elementsBox.model().getItems()
        selectedElements = [allElements[i] for i in range(len(allElements))
                                if self.elementsBox.selectionModel().isRowSelected(i,QtCore.QModelIndex())]
        return tageditormodel.Record(self.typeEditor.getTag(),self.valueEditor.getValue(),allElements,selectedElements)

    def _handleTagChanged(self,value):
        self.valueEditor.setTag(self.typeEditor.getTag())
