#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#
import logging

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

logger = logging.getLogger("gui")

class WidgetList(QtGui.QWidget):
    """A WidgetList sort of a list-view for widgets: It is a widget containing a list of child-widgets, which are either laid out horizontically or vertically. Using a SelectionManager a WidgetList can have a selection and will highlight selected children."""
    
    # This signal is emitted when a widget is inserted into this WidgetList and contains the WidgetList and the position of the inserted widget as parameters.
    widgetInserted = QtCore.pyqtSignal(QtGui.QWidget,int) # Actually the first parameter is a WidgetList
    
    # This signal is emitted when a widget is removed from this WidgetList and contains the WidgetList, the position of the removed widget and that widget itself as parameters.
    widgetRemoved = QtCore.pyqtSignal(QtGui.QWidget,int,QtGui.QWidget)

    # This signal is emitted when a widget is moved in the WidgetList. The parameters are the WidgetList and the old and new position of the moved widget.
    widgetMoved = QtCore.pyqtSignal(QtGui.QWidget,int,int)
    
    def __init__(self,direction,parent=None):
        """Create a new WidgetList laying out children in the specified direction (confer the QBoxLayout::Direction-enum) and using the given parent."""
        QtGui.QWidget.__init__(self,parent)
        self.setLayout(QtGui.QBoxLayout(direction))
        self.children = []
        self.selectionManager = None
        self.layout().setSpacing(0)
        self.layout().setMargin(0)
    
    def getDirection(self):
        """Set the direction in which the children of this WidgetList are laid out (confer the QBoxLayout::Direction-enum)."""
        return self.layout().direction()

    def setDirection(self,direction):
        """Return the direction in which the children of this WidgetList are laid out (confer the QBoxLayout::Direction-enum)."""
        self.layout().setDirection(direction)
    
    def index(self,widget):
        """Return the index of <widget> among this WidgetList's children. Raise an IndexError if the widget cannot be found."""
        return self.children.index(widget)
    
    def __len__(self):
        return self.children.__len__()
        
    def __iter__(self):
        return self.children.__iter__()
        
    def __getitem__(self,key):
        return self.children.__getitem__(key)
    
    def __setitem__(self,key):
        raise NotImplementedError() # Use insertWidget or addWidget
        
    def __delitem__(self,key):
        raise NotImpelementedError() # Use removeWidget
    
    def insertWidget(self,index,widget):
        """Insert <widget> into this WidgetList's children at position <index>."""
        self.children[index:index] = [widget]
        self.layout().insertWidget(index,widget)
        self.widgetInserted.emit(self,index)
    
    def addWidget(self,widget):
        """Add <widget> to the end of this WidgetList's children."""
        index = len(self.children)
        self.insertWidget(index,widget)
    
    def removeWidget(self,widget):
        """Remove <widget> from this WidgetList's children."""
        index = self.children.index(widget)
        self.layout().removeWidget(widget)
        del self.children[index]
        widget.setParent(None)
        self.widgetRemoved.emit(self,index,widget)

    def moveWidget(self,widget,pos):
        """Move <widget> to the index <pos>."""
        oldPos = self.children.index(widget)
        self.children.remove(widget)
        self.layout().removeWidget(widget)
        self.children.insert(pos,widget)
        self.layout().insertWidget(pos,widget)
        self.widgetMoved.emit(self,oldPos,pos)
        
    def getSelectionManager(self):
        """Return the SelectionManager in charge of this WidgetList or None if there is no such SelectionManager."""
        return self.selectionManager
    
    def setSelectionManager(self,selectionManager):
        """Set the SelectionManager in charge of this WidgetList. The previous SelectionManager (if any) is removed. If <selectionManager> is None, this WidgetList won't be able to have a selection afterwards."""
        if self.selectionManager is not None:
            self.selectionManager.removeWidgetList(self)
            self.update() # Repaint as no widgets are selected anymore
        if selectionManager is not None:
            selectionManager.addWidgetList(self)
        self.selectionManager = selectionManager
        
    def paintEvent(self,event):
        if self.selectionManager is not None:
            # Fill the background of selected children
            selectionStatus = self.selectionManager.getSelectionStatus(self)
            if any(selectionStatus):
                painter = QtGui.QPainter(self)
                for i in range(len(self.children)):
                    if selectionStatus[i]:
                        c = self.children[i]
                        painter.fillRect(c.x(),c.y(),c.width(),c.height(),QtGui.QColor.fromRgb(89,166,230))
        QtGui.QWidget.paintEvent(self,event)

    def selectionChanged(self,index):
        """Update the widget at <index> because its selection status has changed. This method is called by the selection manager."""
        child = self.children[index]
        self.update(child.x(),child.y(),child.width(),child.height())


class SelectionManager(QtCore.QObject):
    """A SelectionManager handles the selection of one or more WidgetLists. Using a common SelectionManager for several WidgetLists makes it possible to have one selection for all those WidgetLists (that is, a click on one widget will clear the selection in all WidgetLists and select only this widget.). Usually there is no need to use any method of SelectionManager directly, with the exception of the constructor: Create a SelectionManager and pass the WidgetLists to the constructor or use WidgetList.setSelectionManager."""
    def __init__(self):
        """Creates a SelectionManager."""
        QtCore.QObject.__init__(self)
        self.widgetLists = []
        self.selected = []
        self.anchor = None
    
    #~ def setWidgetLists(self,widgetLists):
        #~ """Set the WidgetList on which this SelectionManager operates. Usually you won't call this method directly, but use WidgetList.setSelectionManager."""
        #~ for widgetList in self.widgetLists:
            #~ self.removeWidgetList(widgetList)
        #~ for widgetList in widgetLists:
            #~ self.addWidgetList(widgetList)
        
    def addWidgetList(self,widgetList):
        """Add a WidgetList to the lists of this SelectionManager. Usually you won't call this method directly, but use WidgetList.setSelectionManager."""
        self.widgetLists.append(widgetList)
        self.selected.append([False] * len(widgetList))
        widgetList.widgetInserted.connect(self._handleWidgetInserted)
        widgetList.widgetRemoved.connect(self._handleWidgetRemoved)
        widgetList.widgetMoved.connect(self._handleWidgetMoved)
        for widget in widgetList:
            widget.installEventFilter(self)
        
    def removeWidgetList(self,widgetList):
        """Remove a WidgetList from the lists of this SelectionManager. Usually you won't call this method directly, but use WidgetList.setSelectionManager."""
        index = self.widgetLists.index(widgetList)
        for widget in widgetList:
            widget.removeEventFilter(self)
        widgetList.widgetInserted.disconnect(self._handleWidgetInserted)
        widgetList.widgetRemoved.disconnect(self._handleWidgetRemoved)
        widgetList.widgetMoved.disconnect(self._handleWidgetMoved)
        del self.selected[index]
        del self.widgetLists[index]
    
    def hasSelection(self):
        """Return whether at least one widget is selected currently."""
        return any(any(s) for s in self.selected)

    def getSelectedWidgets(self):
        """Return a list of all currently selected widgets in the WidgetLists whose selection is managed by this SelectionManager."""
        result = []
        for i in range(len(self.widgetLists)):
            for j in range(len(self.widgetLists[i])):
                if self.selected[i][j]:
                    result.append(self.widgetLists[i][j])
        return result

    def getSelectionStatus(self,widgetList):
        """Return a list of booleans to encode the selection of <widgetList>: The i-th booleans stores whether the i-th widget of <widgetList> is selected."""
        return self.selected[self.widgetLists.index(widgetList)]

    def isSelected(self,widgetList,widget):
        return self.selected[self.widgetLists.index(widgetList)][widgetList.index(widget)]

    def setSelected(self,widgetList,widget,selected):
        listIndex = self.widgetLists.index(widgetList)
        widgetIndex = widgetList.index(widget)
        if self.selected[listIndex][widgetIndex] != selected:
            self.selected[listIndex][widgetIndex] = selected
            widgetList.selectionChanged(widgetIndex)

    def clear(self):
        """Clear the selection."""
        for i in range(len(self.widgetLists)):
            for j in range(len(self.widgetLists[i])):
                if self.selected[i][j]:
                    self.selected[i][j] = False
                    self.widgetLists[i].selectionChanged(j)

    def isSelectable(self,widgetList,widget):
        """Return whether a widget in the specified widgetList is selectable. The default implementation always returns True, so you have to overwrite it, to get non-selectable widgets."""
        return True

    def eventFilter(self,object,event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            widgetList = object.parent()
            if self.isSelectable(widgetList,object):
                listIndex = self.widgetLists.index(widgetList)
                widgetIndex = widgetList.index(object)
                if Qt.ShiftModifier & event.modifiers() and self.anchor is not None:
                    if self.anchor[0] == listIndex:
                        for i in range(min(widgetIndex,self.anchor[1]),max(widgetIndex,self.anchor[1])+1):
                            if not self.selected[listIndex][i]:
                                self.selected[listIndex][i] = True
                                widgetList.selectionChanged(i)
                elif Qt.ControlModifier & event.modifiers():
                    self.selected[listIndex][widgetIndex] = not self.selected[listIndex][widgetIndex]
                    self.anchor = (listIndex,widgetIndex)
                    widgetList.selectionChanged(widgetIndex)
                elif event.button() == Qt.LeftButton: # Clear and select a single widget
                    self.clear()
                    self.selected[listIndex][widgetIndex] = True
                    self.anchor = (listIndex,widgetIndex)
                    widgetList.selectionChanged(widgetIndex)
                #else: Do nothing on the right button, so that the selection won't be changed by opening a context menu

        return False # Don't stop the event
        
    def _handleWidgetInserted(self,widgetList,index):
        """Handle widgetInserted-signal from <widgetList>. <index> is the position of the inserted widget."""
        listIndex = self.widgetLists.index(widgetList)
        widgetList[index].installEventFilter(self)
        self.selected[listIndex].insert(index,False) # Newly inserted widgets are not selected
        
    def _handleWidgetRemoved(self,widgetList,index,widget):
        """Handle widgetRemoved-signal from <widgetList>. <index> is the position of the removed widget, <widget> is that widget itself."""
        listIndex = self.widgetLists.index(widgetList)
        widget.removeEventFilter(self)
        del self.selected[listIndex][index]

    def _handleWidgetMoved(self,widgetList,oldPos,newPos):
        """Handle the widgetMoved-signal from <widgetList> after a widget has been moved from <oldPos> to <newPos>"""
        if oldPos != newPos:
            listIndex = self.widgetLists.index(widgetList)
            self.selected[listIndex].insert(newPos,self.selected[listIndex][oldPos])
            if oldPos < newPos:
                del self.selected[listIndex][oldPos]
            else: del self.selected[listIndex][oldPos + 1] # Take the inserted value into account
