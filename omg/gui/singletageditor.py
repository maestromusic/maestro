# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os, datetime

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg import models, constants, tags, utils
from omg.models import simplelistmodel
from omg.gui import tagwidgets
from omg.gui.misc import listview, widgetlist

EXPAND_LIMIT = 2


class SingleTagEditor(QtGui.QWidget):
    """A SingleTagEditor is the part of an editor used to edit the values of a single tag. It consists of a 
    misc.widgetlist.WidgetList that displays foreach record one RecordEditor wrapped in an
    misc.hiddeneditor.HiddenEditor. Additionally it may contain a ExpandLine that allows to expand/hide the
    records which are not common (i.e. those whose value is not contained in all currently edited elements).
    
    Constructor parameters:
    
        - *tagEditor*: The tageditor that contains this SingleTagEditor
        - *tag*: the tag whose records are managed by this SingleTagEditor
        - *model*: the inner model of the tageditor
        - *parent*: the parent widget 
        
    \ """
    EXPAND_LINE_LIMIT = 3

    def __init__(self,tagEditor,tag,model,parent=None):
        QtGui.QWidget.__init__(self,parent)
        self.tagEditor = tagEditor
        self.tag = tag
        self.model = model
        model.recordInserted.connect(self._handleRecordInserted)
        model.recordRemoved.connect(self._handleRecordRemoved)
        model.recordMoved.connect(self._handleRecordMoved)
        model.commonChanged.connect(self._handleCommonChanged)
        
        self.setLayout(QtGui.QHBoxLayout())
        self.layout().setSpacing(0)
        self.layout().setMargin(0)
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Window,QtGui.QColor(255,255,255))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self.widgetList = widgetlist.WidgetList(QtGui.QBoxLayout.TopToBottom)
        self.layout().addWidget(self.widgetList,1)

        self.expandLine = None
        self.expanded = None
        
        pos = 0
        for record in model.getRecords(tag):
            self._insertRecord(pos,record)
            pos = pos + 1
            
        if self._isExLineNecessary():
            self.setExpanded(False) # Collapse for the start

    def setTag(self,tag):
        """Set the tag this SingleTagEditor feels responsible for. This does not change the appearance of the editor or the value in the editor but simply the set of recordAdded-, recordRemoved,...-signals this SingleTagEditor will react to."""
        self.tag = tag

    def isValid(self):
        """Return whether all values in the RecordEditors are valid (as values of self.tag)."""
        return all(widget.isValid() for widget in self.widgetList if isinstance(widget,RecordEditor))

    def _insertRecord(self,pos,record):
        """Helper method that inserts *record* at position *pos*."""
        recordEditor = RecordEditor(self.model,record)
        if self.expandLine is not None:
            # Calculate the correct position, taking the ExpandLine into account
            if pos > self.widgetList.index(self.expandLine):
                pos = pos + 1
            elif pos == self.widgetList.index(self.expandLine):
                # The record should be inserted exactly at the position of the ExpandLine
                # Should we insert it before or after that line?
                if not record.isCommon():
                    pos = pos + 1
        self.widgetList.insertWidget(pos,recordEditor)
        self._checkExpandLine()
    
    def _handleRecordInserted(self,pos,record):
        if record.tag == self.tag:
            self._insertRecord(pos,record)
            
    def _handleRecordRemoved(self,record):
        if record.tag == self.tag:
            for widget in self.widgetList:
                if isinstance(widget,RecordEditor) and widget.getRecord() == record:
                    self.widgetList.removeWidget(widget)
                    self._checkExpandLine()
                    return
            raise ValueError("Record '{}' was not found.".format(record))

    def _correctPosition(self,pos):
        if self.expandLine is None:
            return pos
        elif pos >= self.widgetList.index(self.expandLine):
            return pos + 1
                
    def _handleRecordMoved(self,tag,oldPos,newPos):
        if tag == self.tag and oldPos != newPos:
            oldPos = self._correctPosition(oldPos)
            newPos = self._correctPosition(newPos)
            self.widgetList.moveWidget(self.widgetList[oldPos],newPos)

    def _handleCommonChanged(self,tag):
        if tag == self.tag:
            self._checkExpandLine()
            
    def _isExLineNecessary(self):
        """Return whether a ExpandLine is necessary given the records in this RecordEditorList."""
        return self._uncommonCount() > self.EXPAND_LINE_LIMIT

    def _checkExpandLine(self):
        if self.expandLine is None:
            if self._isExLineNecessary():
                self.expandLine = ExpandLine(self._uncommonCount())
                self.expandLine.expandButton.triggered.connect(self.setExpanded)
                self.widgetList.insertWidget(self._commonCount(),self.expandLine)
        else:
            if not self._isExLineNecessary():
                self.widgetList.removeWidget(self.expandLine)
                self.expandLine.setParent(None)
                self.expandLine = None
                self.setExpanded(True)
            else:
                # We have an ExpandLine and we need it...fine. But maybe the text or position must be updated
                exPos = self.widgetList.index(self.expandLine)
                if exPos != self._commonCount():
                    self.widgetList.moveWidget(self.expandLine,self._commonCount())
                self.expandLine.setNumber(self._uncommonCount())
                
    def setExpanded(self,expanded):
        """Set whether the uncommon records in this list should be visible (expanded) or not (collapsed)."""
        if expanded == self.expanded:
            return
        if not expanded: # Will collapse now
            for widget in self.widgetList:
                if isinstance(widget,RecordEditor) and not widget.record.isCommon():
                    widget.hide()
            self.expanded = False
            if self.expandLine is not None: # should be always true
                self.expandLine.expandButton.setExpanded(False)
        else: # Will expand now
            for widget in self.widgetList:
                if not widget.isVisible():
                    widget.show()
            self.expanded = True
            if self.expandLine is not None: # should be always true
                self.expandLine.expandButton.setExpanded(True)
                
    def _commonCount(self):
        """Return the number of common records in this SingleTagEditor."""
        return sum(isinstance(widget,RecordEditor) and widget.getRecord().isCommon()
                   for widget in self.widgetList)
        
    def _uncommonCount(self):
        """Return the number of uncommon records in this SingleTagEditor."""
        return sum(isinstance(widget,RecordEditor) and not widget.getRecord().isCommon()
                   for widget in self.widgetList)

    def contextMenuEvent(self,contextMenuEvent):
        record = None
        # Figure out on what record editor the event did happen
        pos = self.widgetList.mapTo(self,contextMenuEvent.pos())
        for widget in self.widgetList:
            if widget.geometry().contains(pos):
                if isinstance(widget,RecordEditor):
                    record = widget.getRecord()
                break;
        self.tagEditor.contextMenuEvent(contextMenuEvent,record)


class RecordEditor(QtGui.QWidget):
    """A RecordEditor is used to edit a single record. It consist of a HiddenEditor to edit the value, a
     label which is empty for common records and contains something like "in 4/8 pieces" for other records
     and a listview showing the titles of the elements in record.elementsWithValue."""
    def __init__(self,model,record,parent=None):
        QtGui.QWidget.__init__(self,parent)
        self.model = model
        self.model.recordChanged.connect(self._handleRecordChanged)
        self.record = record
        
        self.expanded = None # Will be initialized at the end of setRecord
        self.listView = None # Might be created in setRecord
        
        # Create layouts
        self.setLayout(QtGui.QVBoxLayout())
        self.layout().setSpacing(0)
        self.layout().setMargin(0)
        firstLineLayout = QtGui.QHBoxLayout()
        self.secondLineLayout = QtGui.QHBoxLayout()
        self.secondLineLayout.addSpacing(20)
        self.layout().addLayout(firstLineLayout)
        self.layout().addLayout(self.secondLineLayout)
        
        # Create the editor
        self.valueEditor = tagwidgets.TagValueEditor(record.tag,hideEditor=True)
        self.valueEditor.valueChanged.connect(self._handleValueChanged)
        firstLineLayout.addWidget(self.valueEditor)
        
        self.elementsLabel = QtGui.QLabel()
        firstLineLayout.addWidget(self.elementsLabel)
        self.expandButton = ExpandButton()
        self.expandButton.triggered.connect(self.setExpanded)
        firstLineLayout.addWidget(self.expandButton)

        self.setRecord(record)
    
    def getRecord(self):
        """Return the record that can be edited in this RecordEditor."""
        return self.record
        
    def setRecord(self,record):
        """Set the record that can be edited in this RecordEditor."""
        self.record = record
        if record.tag != self.valueEditor.getTag():
            # Do not change the value when changing the tag since it may be invalid for the new tag
            self.valueEditor.setTag(record.tag,setValue=False)
        self.valueEditor.setValue(record.value)
        self._updateElementsLabel()
        if record.isCommon():
            self.expandButton.setVisible(False)
            if self.listView is not None:
                self.secondLineLayout.removeWidget(self.listView)
                self.listView = None
        else:
            elements = record.getExceptions() if record.isUsual() else record.elementsWithValue
            if len(elements) == 1:
                self.expandButton.setVisible(False)
                if self.listView is not None:
                    self.secondLineLayout.removeWidget(self.listView)
                    self.listView = None
            else:
                self.expandButton.setVisible(True)
                if self.listView is None:
                    self.listView = listview.ListView()
                    self.secondLineLayout.addWidget(self.listView)
                self.listView.setModel(simplelistmodel.SimpleListModel(elements,lambda el: el.title))
                self.setExpanded(len(elements) <= EXPAND_LIMIT)

    def _updateElementsLabel(self):
        """Set the correct text in the label, e.g. "in 4/8 pieces"."""
        if self.record.isCommon():
            self.elementsLabel.clear()
            self.elementsLabel.setVisible(False)
        else:
            if self.record.isUsual():
                elements = self.record.getExceptions()
                if len(elements) == 1:
                    self.elementsLabel.setText(self.tr("except in {}").format(elements[0].title))
                else: self.elementsLabel.setText(
                           self.tr("except in {}/%n pieces","",len(self.record.allElements))
                                    .format(len(elements)))
            else:
                elements = self.record.elementsWithValue
                if len(elements) == 1 and self.record.tag != tags.TITLE:
                    # displaying the title is not necessary if the tag is TITLE
                    self.elementsLabel.setText(self.tr("in {}").format(elements[0].title))
                else: self.elementsLabel.setText(
                            self.tr("in {}/%n pieces","",len(self.record.allElements)).format(len(elements)))
        
    def isExpanded(self):
        """Return whether this RecordEditor is expanded, i.e. the list of elements with the record's value
        is visible."""
        return self.expanded
        
    def setExpanded(self,expanded):
        """Set whether this RecordEditor is expanded, i.e. the list of elements with the record's value
        is visible."""
        if expanded != self.expanded:
            self.expanded = expanded
            self.expandButton.setExpanded(expanded)
            if self.listView is not None: # should be always true
                self.listView.setVisible(expanded)

    def isValid(self):
        """Return whether this RecordEditor contains a value that is valid for the record's tag."""
        return self.valueEditor.getValue() is not None
        
    def _handleValueChanged(self):
        """Handle valueChanged signals from the editor."""
        value = self.valueEditor.getValue()
        assert self.record.tag.isValid(value) # the tagwidget only emits this signal if the value is valid
        if self.record.value != value:
            newRecord = self.record.copy()
            newRecord.value = value
            self.model.changeRecord(self.record,newRecord)

    def _handleRecordChanged(self,tag,oldRecord,newRecord):
        """Handle recordChanged signals from the model."""
        if oldRecord is self.record:
            self.setRecord(newRecord)


class ExpandLine(QtGui.QWidget):
    """An ExpandLine is used by SingleTagEditors which contain a lot of uncommon records. It is inserted into
    the list of RecordEditors and allows the user to collapse the uncommon records and expand them again."""
    def __init__(self,number,parent=None):
        QtGui.QWidget.__init__(self,parent)
        self.setLayout(QtGui.QHBoxLayout())
        self.label = QtGui.QLabel()
        self.expandButton = ExpandButton()
        self.layout().addWidget(self.label)
        self.layout().addWidget(self.expandButton)
        self.layout().addStretch()
        self.setNumber(number)
        
    def setNumber(self,number):
        """Set the number of non-common records which is displayed in this ExpandLine."""
        self.label.setText("<i>"+self.tr("{} different").format(number)+"</i>")


class ExpandButton(QtGui.QPushButton):
    """Special button that displays an arrow pointing up (expanded-state) or down (not expanded). After it
    has been clicked by the user it will change its state and emit the triggered-signal with the new state.
    """
    expandIcon = utils.getIcon("expand.png")
    collapseIcon = utils.getIcon("collapse.png")

    # Emitted when the button is clicked. The parameter will be True if the button is in expanded-state
    # _after_ changing its state due to the click.
    triggered = QtCore.pyqtSignal(bool)
    
    def __init__(self,expanded = False,parent=None):
        """Initialize this button with the given parent. If expanded is True, the button will be in
        expanded-state, i.e. show the collapse-icon."""
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
