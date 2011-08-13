#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

import itertools, os.path

from .. import constants, tags, strutils, utils, config, logging, modify
from ..models import tageditormodel, simplelistmodel, File
from ..gui import formatter, singletageditor, dialogs, tagwidgets, mainwindow, editor
from ..gui.misc import widgetlist, dynamicgridlayout

translate = QtCore.QCoreApplication.translate

logger = logging.getLogger(__name__)


class TagEditorDock(QtGui.QDockWidget):
    """DockWidget containing the Browser."""
    def __init__(self,parent=None,state=None):
        QtGui.QDockWidget.__init__(self,parent)
        self.setWindowTitle(self.tr("Tageditor"))
        self.tabWidget = QtGui.QTabWidget()
        self.setWidget(self.tabWidget)
        self.tabWidget.setTabPosition(QtGui.QTabWidget.East)
        self.realEditorWidget = TagEditorWidget(modify.REAL)
        self.editorEditorWidget = TagEditorWidget(modify.EDITOR)
        self.tabWidget.addTab(self.realEditorWidget,self.tr("Real"))
        self.tabWidget.addTab(self.editorEditorWidget,self.tr("Editor"))
        self.setAcceptDrops(True)
        
        mainwindow.mainWindow.globalSelectionChanged.connect(self._handleSelectionChanged)
        
    def _handleSelectionChanged(self,elements,source):
        if isinstance(source,editor.EditorTreeView):
            self.editorEditorWidget.model.setElements(elements)
            self.tabWidget.setCurrentWidget(self.editorEditorWidget)
        elif self.tabWidget.currentWidget() != self.editorEditorWidget:
            self.realEditorWidget.model.setElements(elements)
        # else do nothing (if the user works in the editor, it would be annoying if each click e.g. in the 
        # browser would switch the tageditor to REAL-level.
        
    def dragEnterEvent(self,event):
        if event.mimeData().hasFormat(config.options.gui.mime) or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self,event):
        mimeData = event.mimeData()
        if isinstance(event.source(),editor.EditorTreeView):
            editorWidget = self.editorEditorWidget
        else: editorWidget = self.realEditorWidget
        
        if mimeData.hasFormat(config.options.gui.mime):
            editorWidget.model.setElements(mimeData.getElements())
            event.acceptProposedAction()
        elif mimeData.hasUrls():
            elements = [File.fromFilesystem(url.toLocalFile()) for url in event.mimeData().urls()
                           if url.isValid() and url.scheme() == 'file' and os.path.exists(url.toLocalFile())]
            editorWidget.model.setElements(elements)
            event.acceptProposedAction()
        else:
            logger.warning("Invalid drop event (supports only {})".format(", ".join(mimeData.formats())))
        self.tabWidget.setCurrentWidget(editorWidget)
        
        
mainwindow.addWidgetData(mainwindow.WidgetData(
        id="tageditor",
        name=translate("Tageditor","Tageditor"),
        theClass = TagEditorDock,
        central=False,
        dock=True,
        default=True,
        unique=True,
        preferredDockArea=Qt.BottomDockWidgetArea))
    
    
class TagEditorDialog(QtGui.QDialog):
    def __init__(self,level,elements,parent=None):
        QtGui.QDialog.__init__(self,parent)
        self.setLayout(QtGui.QVBoxLayout())
        self.tagedit = TagEditorWidget(level,elements,dialog=self)
        self.layout().addWidget(self.tagedit)
        self.setWindowTitle(self.tr("Edit tags"))
        self.resize(600,450) #TODO: klüger
        self.tagedit.saved.connect(self.accept)
        
        
class TagEditorWidget(QtGui.QWidget):
    
    saved = QtCore.pyqtSignal()
    
    def __init__(self,level,elements = [],parent = None,dialog=None,saveDirectly=True):
        QtGui.QWidget.__init__(self,parent)
        self.level = level
        if dialog is not None:
            saveDirectly = False
        
        self.model = tageditormodel.TagEditorModel(level,elements,saveDirectly)
        self.model.tagInserted.connect(self._handleTagInserted)
        self.model.tagRemoved.connect(self._handleTagRemoved)
        self.model.tagChanged.connect(self._handleTagChanged)
        self.model.resetted.connect(self._handleReset)

        self.undoAction = modify.createUndoAction(level,self,self.tr("Undo"))
        self.redoAction = modify.createRedoAction(level,self,self.tr("Redo"))

        self.selectionManager = widgetlist.SelectionManager()
        # Do not allow the user to select ExpandLines
        self.selectionManager.isSelectable = \
            lambda wList,widget: not isinstance(widget,singletageditor.ExpandLine)
        
        self.setLayout(QtGui.QVBoxLayout())
        self.label = QtGui.QLabel()
        self.layout().addWidget(self.label)
        self.scrollArea = QtGui.QScrollArea()
        self.scrollArea.setWidgetResizable(True)
        self.layout().addWidget(self.scrollArea)
        self.buttonBarLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(self.buttonBarLayout,0)

        addButton = QtGui.QPushButton(utils.getIcon("add.png"),self.tr("Add tag"))
        addButton.clicked.connect(lambda: self._handleAddRecord(None))
        self.buttonBarLayout.addWidget(addButton)
        removeButton = QtGui.QPushButton(utils.getIcon("remove.png"),self.tr("Remove selected"))
        removeButton.clicked.connect(self._handleRemoveSelected)
        self.buttonBarLayout.addWidget(removeButton)
        self.buttonBarLayout.addStretch(1)
        
        style = QtGui.QApplication.style()
        if not saveDirectly:
            resetButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogResetButton),
                                            self.tr("Reset"))
            resetButton.clicked.connect(self.model.reset)
            self.buttonBarLayout.addWidget(resetButton)
            if dialog is not None:
                cancelButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogCancelButton),
                                                 self.tr("Cancel"))
                cancelButton.clicked.connect(dialog.reject)
            self.buttonBarLayout.addWidget(cancelButton)
            saveButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogSaveButton),
                                           self.tr("Save"))
            saveButton.clicked.connect(self._handleSave)
            self.buttonBarLayout.addWidget(saveButton)
            
        self.viewport = QtGui.QWidget()
        self.viewport.setLayout(QtGui.QVBoxLayout())
        self.tagEditorLayout = dynamicgridlayout.DynamicGridLayout()
        self.tagEditorLayout.setColumnStretch(1,1) # Stretch the column holding the values
        self.viewport.layout().addLayout(self.tagEditorLayout)
        self.viewport.layout().addStretch(1)
        self.scrollArea.setWidget(self.viewport)

        self.singleTagEditors = {}
        self.tagBoxes = {}
        self._handleReset()
         
    def _insertSingleTagEditor(self,row,tag):
        self.tagEditorLayout.insertRow(row)
        
        # Create the tagbox
        self.tagBoxes[tag] = tagwidgets.TagTypeBox(tag,useCoverLabel=True)
        self.tagBoxes[tag].tagChanged.connect(self._handleTagChangedByUser)
        self.tagEditorLayout.addWidget(self.tagBoxes[tag],row,0)
        
        # Create the Tag-Editor
        self.singleTagEditors[tag] = singletageditor.SingleTagEditor(self,tag,self.model)
        self.singleTagEditors[tag].widgetList.setSelectionManager(self.selectionManager)
        self.tagEditorLayout.addWidget(self.singleTagEditors[tag],row,1)

    def _removeSingleTagEditor(self,tag):
        # Simply removing the items would leave an empty row. Thus we use DynamicGridLayout.removeRow.
        # First we have to find the row
        row = None
        for r in range(self.tagEditorLayout.rowCount()):
            if self.tagEditorLayout.itemAtPosition(r,0).widget() == self.tagBoxes[tag]:
                row = r
                break
        assert row is not None
        self.tagEditorLayout.removeRow(row)

        # Tidy up
        # When changing a tag via the tagbox we are about to remove the widget having the current focus.
        # This leads to errors ('Underlying C++ object has been deleted' in focusOutEvent). Fortunately this
        # is fixed using deleteLater.
        self.tagBoxes[tag].deleteLater()
        del self.tagBoxes[tag]
        tagEditor = self.singleTagEditors[tag]
        tagEditor.widgetList.setSelectionManager(None)
        tagEditor.setParent(None)
        del self.singleTagEditors[tag]

    def _handleReset(self):
        for tag in list(self.singleTagEditors.keys()): # dict will change
            self._removeSingleTagEditor(tag)
        for tag in self.model.getTags():
            self._insertSingleTagEditor(len(self.singleTagEditors),tag)
        count = len(self.model.getElements())
        self.label.setText(self.tr("Edit tags of %n element(s).","",count))
        # Enable / disable buttons
        for i in range(self.buttonBarLayout.count()):
            widget = self.buttonBarLayout.itemAt(i).widget()
            if widget is not None:
                widget.setEnabled(count > 0)
        
    def _handleAddRecord(self,tag=None):
        dialog = RecordDialog(self,self.model.getElements(),defaultTag=tag)
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
        for adict in (self.tagBoxes,self.singleTagEditors):
            # Change key from oldTag to newTag
            widget = adict[oldTag]
            del adict[oldTag]
            assert newTag not in adict
            adict[newTag] = widget
            widget.setTag(newTag)

    def _handleTagChangedByUser(self,changedTag):
        # First we have to get the tagBox responsible for this event and its tag
        tagBox = self.sender()
        oldTag = None
        for tag,widget in self.tagBoxes.items():
            if widget == tagBox:
                oldTag = tag
                break
        assert oldTag is not None
        newTag = tagBox.getTag()

        # If changeTag fails, then reset the box
        if not self.model.changeTag(oldTag,newTag):
            QtGui.QMessageBox.warning(self,self.tr("Invalid value"),self.tr("At least one value is invalid for the new type."))
            # reset the editor...unfortunately this emits valueChanged again
            tagBox.tagChanged.disconnect(self._handleTagChangedByUser)
            tagBox.setTag(oldTag)
            tagBox.tagChanged.connect(self._handleTagChangedByUser)
        
    def _handleSave(self):
        if not all(singleTagEditor.isValid() for singleTagEditor in self.singleTagEditors.values()):
            QtGui.QMessageBox.warning(self,self.tr("Invalid value"),self.tr("At least one value is invalid."))
        else:
            self.model.save()
            self.saved.emit()
        
    def contextMenuEvent(self,contextMenuEvent,record=None):
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

        if record is not None:
            editRecordAction = QtGui.QAction(self.tr("Edit record..."),self)
            editRecordAction.triggered.connect(lambda: self._handleEditRecord(record))
            menu.addAction(editRecordAction)
            
        # Fancy stuff
        fancyMenu = menu.addMenu(self.tr("Fancy stuff"))
        selectedRecords = [editor.getRecord() for editor in self.selectionManager.getSelectedWidgets()]

        if len(selectedRecords) > 0:
            if not all(record.isCommon() for record in selectedRecords):
                action = fancyMenu.addAction(self.tr("Extend to all elements"))
                action.triggered.connect(lambda: self.model.extendRecords(selectedRecords))
            
            if len(selectedRecords) > 1 and all(r.tag().type == tags.TYPE_VARCHAR for r in selectedRecords):
                commonPrefix = strutils.commonPrefix(str(record.value) for record in selectedRecords)
                
                if len(commonPrefix) > 0:
                    action = fancyMenu.addAction(self.tr("Edit common start..."))
                    action.triggered.connect(self._editCommonStart)
                    
                    if commonPrefix[-1].upper() == "I":
                        # Bugfix: If up to four pieces using roman numbers are selected, the commonPrefix
                        # will contain an 'I'. Consequently the 'I' is missing in the rest and
                        # numberFromPrefix won't find a number in the first piece.
                        prefixLength = len(commonPrefix) - 1
                    else: prefixLength = len(commonPrefix)
                    rests = [str(record.value)[prefixLength:] for record in selectedRecords]
                    if any(strutils.numberFromPrefix(rest)[0] is not None for rest in rests):
                        action = fancyMenu.addAction(self.tr("Remove common start (including numbers)"))
                        newValues = []
                        for record,rest in zip(selectedRecords,rests):
                            number,prefix = strutils.numberFromPrefix(rest)
                            if number is not None:
                                newValues.append(record.value[prefixLength+len(prefix):])
                            else: newValues.append(record.value[prefixLength])
                        action.triggered.connect(lambda: self.model.editMany(selectedRecords,newValues))
                    else:
                        action = fancyMenu.addAction(self.tr("Remove common start"))
                        newValues = [record.value[len(commonPrefix):] for record in selectedRecords]
                        action.triggered.connect(lambda: self.model.editMany(selectedRecords,newValues))
                
            for separator in self.model.getPossibleSeparators(selectedRecords):
                action = fancyMenu.addAction(self.tr("Separate at '{}'").format(separator))
                action.triggered.connect(lambda: self.model.splitMany(selectedRecords,separator))

        menu.popup(contextMenuEvent.globalPos())

    def _editCommonStart(self):
        selectedRecords = [editor.getRecord() for editor in self.selectionManager.getSelectedWidgets()]
        commonStart = strutils.commonPrefix(str(record.value) for record in selectedRecords)
        text,ok = QtGui.QInputDialog.getText (self,self.tr("Edit common start"),
                                              self.tr("Insert a new text will replace the common start of all selected records:"),text=commonStart)
        if ok:
            newValues = [text+record.value[len(commonStart):] for record in selectedRecords]
            self.model.editMany(selectedRecords,newValues)
    
    def _handleEditRecord(self,record):
        dialog = RecordDialog(self,self.model.getElements(),record=record)
        if dialog.exec_() == QtGui.QDialog.Accepted:
            self.model.changeRecord(record,dialog.getRecord())


class RecordDialog(QtGui.QDialog):
    """Dialog to edit a single record. Parameters are:
    
        - *parent*: The parent widget
        - *elements*: The list of elements that can be selected in the dialog
        - *record*: If set the dialog will be initialized with the tag, value and selected elements from
          the record.
        - *tag*: If set and *record* is None, this tag will be displayed at the beginning.
    
    \ """
    def __init__(self,parent,elements,record=None,defaultTag=None):
        QtGui.QDialog.__init__(self,parent)
        self.setWindowTitle(self.tr("Add tag value"))
        assert len(elements) > 0
        
        if record is not None:
            defaultTag = record.tag
        self.typeEditor = tagwidgets.TagTypeBox(defaultTag=defaultTag)
        self.typeEditor.tagChanged.connect(self._handleTagChanged)
        
        self.valueEditor = tagwidgets.TagValueEditor(self.typeEditor.getTag())
        if record is not None:
            self.valueEditor.setValue(record.value)
            
        self.elementsBox = QtGui.QListView(self)
        # Use a formatter to print the title of the elements
        self.elementsBox.setModel(simplelistmodel.SimpleListModel(elements,
                                                    lambda el: formatter.Formatter(el).title()))
        self.elementsBox.setSelectionMode(QtGui.QAbstractItemView.MultiSelection)
        for i,element in enumerate(elements):
            if record is None or element in record.elementsWithValue:
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
        """Check whether at least one element is selected and the current value is valid and if so, exit."""
        if self.elementsBox.selectionModel().hasSelection():
            if self.valueEditor.getValue() is not None:
                self.accept()
            else: QtGui.QMessageBox.warning(self,self.tr("Invalid value"),self.tr("The given value is invalid."))
        else: QtGui.QMessageBox.warning(self,self.tr("No element selected"),
                                        self.tr("You must select at lest one element."))
        
    def getRecord(self):
        """Return a record with the data from the dialog."""
        allElements = self.elementsBox.model().getItems()
        selectedElements = [allElements[i] for i in range(len(allElements))
                                if self.elementsBox.selectionModel().isRowSelected(i,QtCore.QModelIndex())]
        return tageditormodel.Record(self.typeEditor.getTag(),self.valueEditor.getValue(),allElements,selectedElements)

    def _handleTagChanged(self,tag):
        """Change the tag of the ValueEditor."""
        self.valueEditor.setTag(tag)
