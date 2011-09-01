#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt


class FlagEditor(QtGui.QWidget):
    def __init__(self,model,parent=None):
        super().__init__(parent)
        
        self.model = model
        self.model.resetted.connect(self._handleReset)
        
        self.setLayout(QtGui.QHBoxLayout())
        self._handleReset()
            
    def _handleReset(self):
        while self.layout().count() > 0:
            item = self.layout().takeAt(0)
            self.layout().removeItem(item)
            if item.widget() is not None:
                item.widget().setParent(None)
            if item.layout() is not None:
                item.layout().setParent(None)
        
        for record in self.model.records:
            self.layout().addWidget(QtGui.QLabel(record.flag.name))
            