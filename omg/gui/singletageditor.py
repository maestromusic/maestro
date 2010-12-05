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

from omg import models, constants, FlexiDate, getIcon, tags
from omg.models import simplelistmodel, tageditormodel
from omg.gui import formatter
from omg.gui.misc import editorwidget, listview, widgetlist, tagwidgets

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

        tves = (TagValueEditor(record,self.model) for record in model.getRecords(tag))
        self.widgetList = TVEWidgetList(tves)
        self.layout().addWidget(self.widgetList,1)

    def _handleRecordAdded(self,record):
        if record.tag == self.tag:
            self.widgetList.insertRecord(self.model,record)
            
    def _handleRecordRemoved(self,record):
        if record.tag == self.tag:
            for valueEditor in (widget for widget in self.widgetList if isinstance(widget,TagValueEditor)):
                if valueEditor.getRecord() == record:
                    self.widgetList.removeWidget(valueEditor)
                    return
            
    def _handleRecordChanged(self,oldRecord,newRecord):
        if self.tag == oldRecord.tag == newRecord.tag:
            for valueEditor in (widget for widget in self.widgetList if isinstance(widget,TagValueEditor)):
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
        self.editor = tagwidgets.TagLineEdit(record.tag)
        self.editorWidget = editorwidget.EditorWidget(editor = self.editor)
        self.editorWidget.valueChanged.connect(self._handleValueChanged)
        firstLineLayout.addWidget(self.editorWidget)
        
        self.elementsLabel = QtGui.QLabel()
        firstLineLayout.addWidget(self.elementsLabel)
        self.expandButton = ExpandButton()
        self.expandButton.triggered.connect(self.setExpanded)
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
            self.editorWidget.setValue(self.record.value.strftime())
        else: self.editorWidget.setValue(self.record.value)
        
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
                self.elementsLabel.setText(" {} {}/{} Stücken"
                        .format(preposition,len(elements),len(self.record.allElements)))
        
    def isExpanded(self):
        return self.expanded
        
    def setExpanded(self,expanded):
        if expanded != self.expanded:
            self.expanded = expanded
            self.expandButton.setExpanded(expanded)
            self._updateElementsLabel()
            if self.listView is not None:
                self.listView.setVisible(expanded)

    def _handleValueChanged(self,value):
        if self.record.tag.isValid(value):
            if self.record.tag.type == tags.TYPE_DATE:
                value = FlexiDate(value)
            newRecord = self.record.copy()
            newRecord.value = value
            self.model.changeRecord(self.record,newRecord)
        else:
            self._updateEditorWidget() # Reset the editor
            QtGui.QMessageBox.warning(self,"Ungültiger Wert","Der eingegebene Wert ist ungültig.")


class TVEWidgetList(widgetlist.WidgetList):
    """A TVEWidgetList is a WidgetList specialized for the TagEditor. It may contain only TagValueEditors (TVEs) as ordinary children. The common records will be sorted to the top and if many various (=non-common) records are present (confer _isVLineNecessary) a VariousLine is inserted into the WidgetList to enable the user to collapse those records and expand them again."""
    def __init__(self,tves,parent=None):
        """Create a new TVEWidgetList with the given parent and initialize it with the TVEs in the list <tves>."""
        widgetlist.WidgetList.__init__(self,QtGui.QBoxLayout.TopToBottom,parent)
        self.variousLine = None
        self.expanded = True
        for tve in tves:
            self.addWidget(tve)
        if self._isVLineNecessary():
            self.setExpanded(False) # Collapse for the start

    def insertRecord(self,model,record):
        """Insert a TVE for the given record in the given model at the position of the record in that model. Use this mehtod instead of insertWidget as it corrects the position accounting for the VariousLine."""
        widget = TagValueEditor(record,model)
        index = model.getRecords(record.tag).index(record)
        if self.variousLine is not None and index > self._commonCount():
            index = index + 1 # Account for the various line
        self.insertWidget(index,widget)
        
    def setExpanded(self,expanded):
        """Set whether the various records in this list should be visible (expanded) or not (collapsed)."""
        if expanded == self.expanded:
            return
        if self.expanded: # Will collapse now
            for widget in self.children:
                if isinstance(widget,TagValueEditor) and not widget.record.isCommon():
                    widget.hide()
            self.expanded = False
            if self.variousLine is not None: # should be always true
                self.variousLine.expandButton.setExpanded(False)
        else: # Will expand now
            for widget in self.children:
                if not widget.isVisible():
                    widget.show()
            self.expanded = True
            if self.variousLine is not None: # should be always true
                self.variousLine.expandButton.setExpanded(True)

    def insertWidget(self,index,widget):
        """Insert <widget> into this TVEWidgetList's children at position <index>. If necessary adjust <index> so that records are sorted in common ones and various ones. Create and insert a VariousLine if necessary."""
        assert isinstance(widget,TagValueEditor)
        if index < 0 or index > len(self.children):
            raise ValueError("Index must be between 0 and len(self.children).")
            
        if widget.record.isCommon():
            # Force the index to point into the common records
            index = min(index,self._commonCount())
            widgetlist.WidgetList.insertWidget(self,index,widget)
        else:
            widget.setVisible(self.expanded)
            # Force the index to point into the various records
            assert index == len(self.children)
            index = max(index,len(self.children) - self._variousCount())
            widgetlist.WidgetList.insertWidget(self,index,widget)
            if self.variousLine is not None:
                self.variousLine.setNumber(self._variousCount())
            elif self._isVLineNecessary():
                self.variousLine = VariousLine(self._variousCount())
                self.variousLine.expandButton.triggered.connect(self.setExpanded)
                widgetlist.WidgetList.insertWidget(self,self._commonCount(),self.variousLine)

    def removeWidget(self,widget):
        """Remove <widget> from this TVEWidgetList's children. Remove the VariousLine if it is not needed anymore."""
        assert isinstance(widget,TagValueEditor) # Do not remove the VariousLine from outside this class
        widgetlist.WidgetList.removeWidget(self,widget)
        if self.variousLine is not None and not widget.getRecord().isCommon():
            if not self._isVLineNecessary():
                self.setExpanded(True)
                widgetlist.WidgetList.removeWidget(self,self.variousLine)
                self.variousLine = None
            else: self.variousLine.setNumber(self._variousCount())
            
    def _commonCount(self):
        """Return the number of common records in this TVEWidgetList."""
        result = 0
        while (result < len(self.children)
                    and isinstance(self.children[result],TagValueEditor)
                    and self.children[result].record.isCommon()):
            result = result + 1
        return result
        
    def _variousCount(self):
        """Return the number of various records in this TVEWidgetList."""
        result = 0
        for widget in self.children:
            if isinstance(widget,TagValueEditor) and not widget.record.isCommon():
                result = result + 1
        return result
        
    def _isVLineNecessary(self):
        """Return whether a VariousLine is necessary given the records in this TVEWidgetList."""
        return self._variousCount() > 3


class VariousLine(QtGui.QWidget):
    """A VariousLine is used by TVEWidgetLists which contain a lot of non-common records. It is inserted into the list of TVEs (TagValueEditors) and allows the user to collapse the non-common records and expand them again."""
    def __init__(self,number,parent=None):
        QtGui.QWidget.__init__(self,parent)
        self.setLayout(QtGui.QHBoxLayout())
        self.label = QtGui.QLabel()
        self.expandButton = ExpandButton()
        self.layout().addWidget(self.label,1)
        self.layout().addWidget(self.expandButton)
        self.setNumber(number)
        
    def setNumber(self,number):
        """Set the number of non-common records which is displayed in this VariousLine."""
        self.label.setText("<i>({} verschiedene)</i>".format(number))


class ExpandButton(QtGui.QPushButton):
    """Special button that displays an arrow pointing up (expanded-state) or down (not expanded). After it has been clicked by the user it will change its state and emit the triggered-signal with the new state."""
    expandIcon = QtGui.QIcon(getIcon("expand.png"))
    collapseIcon = QtGui.QIcon(getIcon("collapse.png"))

    triggered = QtCore.pyqtSignal(bool) # Emitted when the button is clicked. The parameter will be True if the button is in expanded-state _after_ changing its state due to the click.
    
    def __init__(self,expanded = False,parent=None):
        """Initialize this button with the given parent. If expanded is True, the button will be in expanded-state, i.e. show the collapse-icon."""
        QtGui.QPushButton.__init__(self,self.collapseIcon if expanded else self.expandIcon,'',parent)
        self.setFlat(True)
        self.expanded = expanded
        self.clicked.connect(self._handleClicked)

    def _handleClicked(self,checked = False):
        """Handle a click on the button."""
        self.setExpanded(not self.expanded)
        self.triggered.emit(self.expanded)

    def setExpanded(self,expanded):
        """Set the expanded-state of the button to <expanded>."""
        if expanded != self.expanded:
            self.expanded = expanded
            self.setIcon(self.collapseIcon if expanded else self.expandIcon)
