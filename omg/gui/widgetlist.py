#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

class WidgetList(QtGui.QWidget):
    def __init__(self,direction,parent=None):
        QtGui.QWidget.__init__(self,parent)
        self.setLayout(QtGui.QBoxLayout(direction))
        self.children = []
        self.selectedChild = None
        self.layout().setSpacing(0)
        self.layout().setMargin(0)
    
    def setDirection(self,direction):
        self.layout().setDirection(direction)
    
    def getWidgets(self):
        return self.children
        
    def insertWidget(self,index,widget):
        self.children[index:index] = [widget]
        self.layout().insertWidget(index,widget)
    
    def addWidget(self,widget):
        self.insertWidget(len(self.children),widget)
    
    def removeWidget(self,widget):
        self.layout().removeWidget(widget)
    
    def mousePressEvent(self,event):
        for child in self.children:
            if child.underMouse():
                if child == self.selectedChild:
                    self.selectedChild = None
                else: self.selectedChild = child
                self.update(child.x(),child.y(),child.width(),child.height())
        QtGui.QWidget.mousePressEvent(self,event)
        
    def paintEvent(self,event):
        if self.selectedChild is not None:
            painter = QtGui.QPainter(self)
            c = self.selectedChild
            painter.fillRect(c.x(),c.y(),c.width(),c.height(),QtGui.QColor.fromRgb(89,166,230))
        QtGui.QWidget.paintEvent(self,event)