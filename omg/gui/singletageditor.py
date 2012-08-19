# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import tagwidgets
from .misc import listview, widgetlist
from .. import utils
from ..core import tags
from ..models import simplelistmodel

EXPAND_LIMIT = 2


class SingleTagEditor(QtGui.QWidget):
    """A SingleTagEditor is the part of an editor used to edit the values of a single tag. It consists of a 
    two misc.widgetlist.WidgetList-instances that display the common records and the uncommon ones,
    respectively. They are separated by a ExpandLine that can be used to expand/hide the second list.
    For each record the corresponding list contains a RecordEditor.
    
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
        self.expanded = False
        model.recordInserted.connect(self._handleRecordInserted)
        model.recordRemoved.connect(self._handleRecordRemoved)
        model.recordChanged.connect(self._handleRecordChanged)
        
        self.setLayout(QtGui.QVBoxLayout())
        self.layout().setSpacing(0)
        self.layout().setContentsMargins(0,0,0,0)
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Window,QtGui.QColor(255,255,255))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self.commonList = widgetlist.WidgetList(QtGui.QBoxLayout.TopToBottom)
        self.layout().addWidget(self.commonList,1)
        
        self.expandLine = ExpandLine()
        self.expandLine.triggered.connect(self.setExpanded)
        self.layout().addWidget(self.expandLine)
        
        self.uncommonList = widgetlist.WidgetList(QtGui.QBoxLayout.TopToBottom)
        self.layout().addWidget(self.uncommonList,1)
        
        pos = 0
        for record in model.getRecords(tag):
            self._insertRecord(pos,record)
            pos = pos + 1
    
        self._updateUncommonDisplay()

    def setTag(self,tag):
        """Set the tag this SingleTagEditor feels responsible for. This does not change the appearance of
        the editor or the value in the editor but simply the set of recordAdded-, recordRemoved,...-signals
        this SingleTagEditor will react to.
        """
        self.tag = tag

    def isValid(self):
        """Return whether all values in the RecordEditors are valid (as values of self.tag)."""
        return all(widget.isValid() for widget in self.widgetList if isinstance(widget,RecordEditor))

    def _computePosition(self,common,pos):
        """Translate the position *pos* from a position in the model's list of records to a position in
        either the list of common records or the list of uncommon records, depending on *common*.""" 
        return pos - sum(record.isCommon() != common for record in self.model.getRecords(self.tag)[:pos])
        
    def _insertRecord(self,pos,record):
        """Helper method: Insert *record* at position *pos*."""
        recordEditor = RecordEditor(self.model,record)
        pos = self._computePosition(record.isCommon(),pos)
        (self.commonList if record.isCommon() else self.uncommonList).insertWidget(pos,recordEditor)
        self._updateUncommonDisplay()
    
    def _removeRecord(self,record):
        """Helper method: Remove *record*."""
        widgetList = (self.commonList if record.isCommon() else self.uncommonList)
        for widget in widgetList:
            if widget.getRecord() == record:
                widgetList.removeWidget(widget)
                self._updateUncommonDisplay()
                return
        else: raise ValueError("Record '{}' was not found.".format(record))
        
    def _handleRecordInserted(self,pos,record):
        """React to recordInserted-signals from the model."""
        if record.tag == self.tag:
            self._insertRecord(pos,record)
            
    def _handleRecordRemoved(self,record):
        """React to recordRemoved-signals from the model."""
        if record.tag == self.tag:
            self._removeRecord(record)

    def _handleRecordChanged(self,tag,oldRecord,newRecord):
        """React to recordChanged-signals from the model."""
        if tag == self.tag and oldRecord.isCommon() != newRecord.isCommon():
            # Change the list in which the record is displayed
            self._removeRecord(oldRecord)
            self._insertRecord(self.model.getRecords(self.tag).index(newRecord),newRecord)

    def _updateUncommonDisplay(self):
        """Update the expand line and list of uncommon records. Check whether they should be visible."""
        self.commonList.setVisible(len(self.commonList) > 0)
        uncommonCount = len(self.uncommonList)
        expandLineNecessary = uncommonCount > self.EXPAND_LINE_LIMIT
        self.expandLine.setVisible(expandLineNecessary)
        self.uncommonList.setVisible(uncommonCount > 0 and (self.expanded or not expandLineNecessary))
        self.uncommonList.setContentsMargins(20 if expandLineNecessary else 0,0,0,0)
        self.expandLine.setText("<i>"+self.tr("{} different").format(uncommonCount)+"</i>")
                
    def setExpanded(self,expanded):
        """Set whether the uncommon records in this list should be visible (expanded) or not (collapsed)."""
        if expanded == self.expanded:
            return
        self.expanded = expanded
        self._updateUncommonDisplay()
                
    def contextMenuEvent(self,contextMenuEvent):
        # Figure out on what record editor the event did happen
        for widgetList in (self.commonList,self.uncommonList):
            if not widgetList.isVisible():
                continue
            pos = widgetList.mapTo(self,contextMenuEvent.pos())
            for widget in widgetList:
                if widget.geometry().contains(pos):
                    self.tagEditor.contextMenuEvent(contextMenuEvent,widget.getRecord())
                    return;
        else: self.tagEditor.contextMenuEvent(contextMenuEvent,None)


class RecordEditor(QtGui.QWidget):
    """A RecordEditor is used to edit a single record. It consist of a TagValueEditor to edit the value, an
     ExpandLine which is invisible for common records and contains something like "in 4/8 elements" for other
     records and a listview showing the titles of the elements in record.elementsWithValue. The listview can
     be expanded/hidden using the ExpandLine.
     """
    def __init__(self,model,record,parent=None):
        QtGui.QWidget.__init__(self,parent)
        self.model = model
        self.model.recordChanged.connect(self._handleRecordChanged)
        self.record = record
        
        self.expanded = None # Will be initialized at the end of setRecord
        self.listView = None # Might be created in setRecord
        
        self.setLayout(QtGui.QVBoxLayout())
        self.layout().setSpacing(0)
        self.layout().setContentsMargins(0,0,0,0)
        
        # Create the editor
        self.valueEditor = tagwidgets.TagValueEditor(record.tag,hideEditor=True)
        self.valueEditor.valueChanged.connect(self._handleValueChanged)
        self.layout().addWidget(self.valueEditor)
        
        self.expandLine = ExpandLine()
        self.layout().addWidget(self.expandLine)
        font = self.font()
        font.setPointSize(font.pointSize()-2)
        self.expandLine.setFont(font)
        
        # Using an extra layout for the list view seems to be the only method to indent it by 20px
        listViewLayout = QtGui.QHBoxLayout()
        listViewLayout.setContentsMargins(20,0,0,0)
        self.listView = listview.ListView()
        self.listView.setModel(simplelistmodel.SimpleListModel([],lambda el: el.getTitle()))
        self.listView.setFont(font)
        listViewLayout.addWidget(self.listView)
        self.layout().addLayout(listViewLayout)
        
        self.setRecord(record)
        self.expandLine.triggered.connect(self.listView.setVisible)
        self._updateElementDisplay()
    
    def _updateElementDisplay(self):
        """Update the expandline and the listview and check whether they should be visible."""
        record = self.record
        if record.isCommon():
            self.expandLine.setVisible(False)
            self.listView.setVisible(False)
        else:
            elements = record.elementsWithValue if not record.isUsual() else record.getExceptions()
            if len(elements) == 1:
                if record.tag == tags.TITLE:
                    # No need to display the title in the expandline when it is the record's value itself
                    self.expandLine.setVisible(False)
                    self.listView.setVisible(False)
                else:
                    self.expandLine.setVisible(True)
                    text = self.tr("in {}") if not record.isUsual() else self.tr("except in {}")
                    self.expandLine.setText(text.format(elements[0].getTitle()))
                    self.expandLine.setExpanderVisible(False)
                    self.listView.setVisible(False)
            else:
                self.expandLine.setVisible(True)
                text = self.tr("in {}/{} elements") if not record.isUsual() \
                                                    else self.tr("except in {}/{} elements")
                self.expandLine.setText(text.format(len(elements),len(record.allElements)))
                if record.tag == tags.TITLE:
                    self.expandLine.setExpanderVisible(False)
                    self.listView.setVisible(False)
                else:
                    self.expandLine.setExpanderVisible(True)
                    self.listView.model().setItems(elements)
                    self.expandLine.setExpanded(len(elements) <= EXPAND_LIMIT)
                    self.listView.setVisible(len(elements) <= EXPAND_LIMIT)
    
    def getRecord(self):
        """Return the record that can be edited in this RecordEditor."""
        return self.record
        
    def setRecord(self,record):
        """Set the record that can be edited in this RecordEditor."""
        self.record = record
        if record.tag != self.valueEditor.getTag():
            self.valueEditor.setTag(record.tag)
        self.valueEditor.setValue(record.value)
        self._updateElementDisplay()

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


class ExpandLine(QtGui.QLabel):
    """An ExpandLine is used by SingleTagEditors which contain a lot of uncommon records. It is inserted into
    the list of RecordEditors and allows the user to collapse the uncommon records and expand them again."""
    
    # Emitted when the button is clicked. The parameter will be True if the button is in expanded-state
    # _after_ changing its state due to the click.
    triggered = QtCore.pyqtSignal(bool)
    
    def __init__(self,text=''):
        super().__init__(text)
        self.setIndent(20)
        self._expanded = False
        self._expanderVisible = True
    
    def setExpanded(self,expanded):
        """Set whether this line is expanded. When the expand-state is changed by this method, emit the
        triggered-signal."""  
        if expanded != self._expanded:
            self._expanded = expanded
            self.update()
            self.triggered.emit(expanded)
            
    def setExpanderVisible(self,expanderVisible):
        """Set whether the expand-icon is visible (and reacts to mouse clicks)."""
        if expanderVisible != self._expanderVisible:
            self._expanderVisible = expanderVisible
            self.update()
          
    def paintEvent(self,event):
        super().paintEvent(event)
        painter = QtGui.QStylePainter(self)
        if self._expanderVisible:
            option = QtGui.QStyleOption()
            option.initFrom(self)
            option.rect = QtCore.QRect(0,0,self.indent(),self.height())
            # State_Children is necessary to draw an arrow at all, State_Open draws the expanded arro
            option.state |= QtGui.QStyle.State_Children
            if self._expanded:
                option.state |= QtGui.QStyle.State_Open
            painter.drawPrimitive(QtGui.QStyle.PE_IndicatorBranch,option)
        event.accept()
    
    def mousePressEvent(self,event):
        if event.button() == Qt.LeftButton and self._expanderVisible and event.pos().y() < self.indent():
            self.setExpanded(not self._expanded)
            event.accept()
        else: event.ignore() # let parent widget handle it (otherwise it is not possible to select records)
