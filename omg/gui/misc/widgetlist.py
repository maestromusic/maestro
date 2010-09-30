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
    widgetInserted = QtCore.pyqtSignal(QtGui.QWidget,int) # Actually the first parameter is a WidgetList
    widgetRemoved = QtCore.pyqtSignal(QtGui.QWidget,int,QtGui.QWidget)  #   "
    
    def __init__(self,direction,parent=None):
        QtGui.QWidget.__init__(self,parent)
        self.setLayout(QtGui.QBoxLayout(direction))
        self.children = []
        self.selectionManager = None
        self.layout().setSpacing(0)
        self.layout().setMargin(0)
    
    def setDirection(self,direction):
        self.layout().setDirection(direction)
    
    def index(self,widget):
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
        self.children[index:index] = [widget]
        self.layout().insertWidget(index,widget)
        self.widgetInserted.emit(self,index)
    
    def addWidget(self,widget):
        index = len(self.children)
        self.insertWidget(index,widget)
        self.widgetInserted.emit(self,index)
    
    def removeWidget(self,widget):
        index = self.children.index(widget)
        self.layout().removeWidget(widget)
        self.widgetRemoved.emit(self,index,widget)
    
    def getSelectionManager(self):
        return self.selectionManager
    
    def setSelectionManager(self,selectionManager):
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
        child = self.children[index]
        self.update(child.x(),child.y(),child.width(),child.height())


class SelectionManager(QtCore.QObject):
    def __init__(self,widgetLists=None):
        QtCore.QObject.__init__(self)
        self.widgetLists = []
        self.selected = []
        if widgetLists is not None:
            self.setWidgetLists(widgetLists)
    
    def setWidgetLists(self,widgetLists):
        for widgetList in self.widgetLists:
            self.removeWidgetList(widgetList)
        for widgetList in widgetLists:
            self.addWidgetList(widgetList)
        
    def addWidgetList(self,widgetList):
        self.widgetLists.append(widgetList)
        self.selected.append([False] * len(widgetList))
        widgetList.widgetInserted.connect(self._handleWidgetInserted)
        widgetList.widgetRemoved.connect(self._handleWidgetRemoved)
        for widget in widgetList:
            widget.installEventFilter(self)
        
    def removeWidgetList(self,widgetList):
        index = self.widgetLists.index(widgetList)
        for widget in widgetList:
            widget.removeEventFilter(self)
        #TODO: deconnect widgetInserted and widgetRemoved
        del self.selected[index]
        del self.widgetLists[index]
    
    def getSelectionStatus(self,widgetList):
        return self.selected[self.widgetLists.index(widgetList)]
        
    def clear(self):
        for i in range(len(self.widgetLists)):
            for j in range(len(self.widgetLists[i])):
                if self.selected[i][j]:
                    self.selected[i][j] = False
                    self.widgetLists[i].selectionChanged(j)
            
    def eventFilter(self,object,event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            widgetList = object.parent()
            #~ try:
            listIndex = self.widgetLists.index(widgetList)
            widgetIndex = widgetList.index(object)
            if Qt.ControlModifier & event.modifiers():
                self.selected[listIndex][widgetIndex] = not self.selected[listIndex][widgetIndex]
                widgetList.selectionChanged(widgetIndex)
            else:
                self.clear()
                self.selected[listIndex][widgetIndex] = True
                widgetList.selectionChanged(widgetIndex)
            #~ except IndexError as e:
                #~ logger.warning("Something's wrong with the SelectionManager's indices: {} {}".format(listIndex,widgetIndex))

        return False # Don't stop the event
        
    def _handleWidgetInserted(self,widgetList,index):
        listIndex = self.widgetLists.index(widgetList)
        widgetList[index].installEventFilter(self)
        self.selected[listIndex].insert(index,False) # Newly inserted widgets are not selected
        
    def _handleWidgetRemoved(self,widgetList,index,widget):
        listIndex = self.widgetLists.index(widgetList)
        widget.removeEventFilter(self)
        del self.selected[listIndex][index]