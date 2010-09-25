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
        self.selectedIndex = None
        self.layout().setSpacing(0)
        self.layout().setMargin(0)
    
    def setDirection(self,direction):
        self.layout().setDirection(direction)
        
    def insertWidget(self,index,widget):
        self.children[index:index] = [widget]
        self.layout().insertWidget(index,widget)
    
    def addWidget(self,widget):
        self.insertWidget(len(self.children),widget)