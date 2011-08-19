#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

 
class IconButtonBar(QtGui.QWidget):
    def __init__(self,parent = None):
        QtGui.QWidget.__init__(self,parent)
        self.setSizePolicy(
                QtGui.QSizePolicy(QtGui.QSizePolicy.MinimumExpanding,QtGui.QSizePolicy.MinimumExpanding))
        self.setLayout(QtGui.QHBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)
        self.layout().setSpacing(0)
        self.layout().addStretch(1)
        
    def addIcon(self,icon,slot = None,toolTip = None):
        button = QtGui.QToolButton()
        button.setContentsMargins(0,0,0,0)
        button.setIcon(icon)
        if slot is not None:
            button.clicked.connect(slot)
        if toolTip is not None:
            button.setToolTip(toolTip)
        self.layout().insertWidget(self.layout().count()-1,button,0)