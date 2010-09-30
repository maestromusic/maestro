#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#
import os, datetime

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg import models, constants, FlexiDate, getIcon
from omg.models import simplelistmodel, tageditormodel
from omg.gui import formatter
from omg.gui.misc import editorwidget, listview, widgetlist

EXPAND_LIMIT = 2

class SingleTagEditor(QtGui.QWidget):
    def __init__(self,tag,model,parent=None):
        QtGui.QWidget.__init__(self,parent)
        self.tag = tag
        self.model = model
        model.recordAdded.connect(self._handleRecordAdded)
        model.recordChanged.connect(self._handleRecordChanged)
        model.recordRemoved.connect(self._handleRecordRemoved)
        self.setLayout(QtGui.QHBoxLayout())
        self.layout().setSpacing(0)
        self.layout().setMargin(0)
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Window,QtGui.QColor(255,255,255))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        
        self.widgetList = widgetlist.WidgetList(QtGui.QBoxLayout.TopToBottom)
        self.layout().addWidget(self.widgetList,1)
        
        self.buttonBarLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(self.buttonBarLayout)
        
        # Create buttons
        #~ addButton = QtGui.QPushButton(QtGui.QIcon(getIcon("add.png")),"")
        #~ self.buttonBarLayout.addWidget(addButton)
        #~ removeButton = QtGui.QPushButton(QtGui.QIcon(getIcon("remove.png")),"")
        #~ self.buttonBarLayout.addWidget(removeButton)
        #~ editButton = QtGui.QPushButton(QtGui.QIcon(getIcon("edit.png")),"Edit")
        #~ self.buttonBarLayout.addWidget(editButton)
        #~ self.hideDiverseButton = QtGui.QPushButton(QtGui.QIcon(getIcon("foldin.png")),"")
        #~ self.hideDiverseButton.setVisible(False)
        #~ self.buttonBarLayout.addWidget(self.hideDiverseButton)
        
        # Fill the widget list
        for record in model.getRecords(tag):
            self.widgetList.addWidget(TagValueEditor(record,self.model))

    def _handleRecordAdded(self,record):
        if record.tag == self.tag:
            self.widgetList.addWidget(TagValueEditor(record,self.model))
            
    def _handleRecordRemoved(self,record):
        if record.tag == self.tag:
            for valueEditor in self.widgetList.getWidgets():
                if valueEditor.getRecord() == record:
                    self.widgetList.removeWidget(valueEditor)
                    return
            
    def _handleRecordChanged(self,oldRecord,newRecord):
        if self.tag == oldRecord.tag == newRecord.tag:
            for valueEditor in self.widgetList.getWidgets():
                if valueEditor.getRecord() == oldRecord:
                    valueEditor.setRecord(newRecord)
                    return
        elif self.tag == oldRecord.tag:
            self._handleRecordRemoved(oldRecord)
        elif self.tag == newRecord.tag:
            self._handleRecordAdded(newRecord)


class TagValueEditor(QtGui.QWidget):
    def __init__(self,record,model,parent=None):
        QtGui.QWidget.__init__(self,parent)
        self.record = record
        self.model = model
        self.editing = False
        self.expanded = None # Will be initialized at the end of setRecord
        
        self.listView = None # Might be created in setRecord
        
        # Create layouts
        self.setLayout(QtGui.QVBoxLayout())
        self.layout().setSpacing(0)
        self.layout().setMargin(0)
        firstLineLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(firstLineLayout)
        
        # Create and fill the EditorWidget
        self.editorWidget = editorwidget.EditorWidget()
        self.valueLabel = QtGui.QLabel()
        self.editorWidget.setLabel(self.valueLabel)
        self.editor = TagLineEdit()
        self.editorWidget.setEditor(self.editor)
        # The following connection resets the editor when it looses focus
        self.editorWidget.editorClosed.connect(self._updateEditorWidget)
        firstLineLayout.addWidget(self.editorWidget)
        
        self.elementsLabel = QtGui.QLabel()
        firstLineLayout.addWidget(self.elementsLabel)
        self.expandButton = ExpandButton(self)
        firstLineLayout.addWidget(self.expandButton)
        
        self.setRecord(record)
    
    def getRecord(self):
        return self.record
        
    def setRecord(self,record):
        self.record = record
        self._updateEditorWidget()
        self._updateElementsLabel()
        if record.isCommon():
            self.expandButton.setVisible(False)
            if self.listView is not None:
                self.layout().removeWidget(self.listView)
                self.listView = None
        else:
            elements = record.getExceptions() if record.isUsual() else record.elementsWithValue
            if len(elements) == 1:
                self.expandButton.setVisible(False)
                if self.listView is not None:
                    self.layout().removeWidget(self.listView)
                    self.listView = None
            else:
                self.expandButton.setVisible(True)
                if self.listView is None:
                    self.listView = listview.ListView()
                    self.layout().addWidget(self.listView)
                self.listView.setModel(simplelistmodel.SimpleListModel(elements,models.Element.getTitle))
                self.setExpanded(len(elements) <= EXPAND_LIMIT)
    
    def _updateEditorWidget(self):
        if isinstance(self.record.value,FlexiDate):
            value = self.record.value.strftime()
        else: value = self.record.value
        self.valueLabel.setText(value)
        self.editor.setText(value)
        
    def _updateElementsLabel(self):
        if self.record.isCommon():
            self.elementsLabel.clear()
            self.elementsLabel.setVisible(False)
        else:
            elements = self.record.getExceptions() if self.record.isUsual() else self.record.elementsWithValue
            preposition = "außer in" if self.record.isUsual() else "in"
            if len(elements) == 1:
                self.elementsLabel.setText(" {} {}".format(preposition,elements[0].getTitle()))
            else:
                self.elementsLabel.setText(" {} {}/{} Stücken{}".format(
                        preposition,len(elements),len(self.record.allElements),':' if self.isExpanded() else ''))
        
    def isExpanded(self):
        return self.expanded
        
    def setExpanded(self,expanded):
        if expanded != self.expanded:
            self.expanded = expanded
            self.expandButton.setExpanded(expanded)
            self._updateElementsLabel()
            if self.listView is not None:
                self.listView.setVisible(expanded)

    def keyPressEvent(self,event):
        if event.key() == Qt.Key_Escape:
            self.editorWidget.showLabel()
            event.accept()
        elif event.key() == Qt.Key_Return:
            if self.record.tag.isValid(self.editor.text()):
                newRecord = self.record.copy()
                newRecord.value = self.editor.text()
                self.model.changeRecord(self.record,newRecord)
                self.editorWidget.showLabel()
            else: QtGui.QMessageBox.warning(self,"Ungültiger Wert","Der eingegebene Wert ist ungültig.")
            event.accept()


class TagLineEdit(QtGui.QLineEdit):
    def __init__(self,parent=None):
        QtGui.QLineEdit.__init__(self,parent)


class ExpandButton(QtGui.QPushButton):
    expandIcon = QtGui.QIcon(getIcon("expand.png"))
    collapseIcon = QtGui.QIcon(getIcon("collapse.png"))
    
    def __init__(self,editor,parent=None):
        """Initialize this button with the given parent. The button will show the expand-icon."""
        QtGui.QPushButton.__init__(self,self.expandIcon,'',parent)
        self.expanded = False
        self.editor = editor
        self.clicked.connect(self._handleClicked)

    def _handleClicked(self,checked = False):
        """Handle a click on the button."""
        self.setExpanded(not self.expanded)
        self.editor.setExpanded(self.expanded)

    def setExpanded(self,expanded):
        if expanded != self.expanded:
            self.expanded = expanded
            self.setIcon(self.collapseIcon if expanded else self.expandIcon)