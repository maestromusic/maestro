#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import SIGNAL

from omg.models import playlist as playlistmodel
from . import delegate,layouter

class Playlist(QtGui.QWidget):
    model = None
    view = None
    
    def __init__(self,parent=None,model=None):
        QtGui.QWidget.__init__(self,parent)
        
        if model is not None:
            self.model = model
        else: self.model = playlistmodel.Playlist()
        
        # Create Gui
        layout = QtGui.QVBoxLayout()
        self.setLayout(layout)
        
        controlLineLayout = QtGui.QHBoxLayout()
        layout.addLayout(controlLineLayout)
        
        self.view = QtGui.QTreeView(self)
        self.view.setHeaderHidden(True)
        self.view.setModel(self.model)
        self.view.setItemDelegate(delegate.Delegate(self,self.model,layouter.PlaylistLayouter(),self.font()))
        self.view.setExpandsOnDoubleClick(False)
        self.view.setAlternatingRowColors(True)
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Base,QtGui.QColor(0xE9,0xE9,0xE9))
        palette.setColor(QtGui.QPalette.AlternateBase,QtGui.QColor(0xD9,0xD9,0xD9))
        self.view.setPalette(palette)
        self.model.modelReset.connect(self._handleReset)
        
        layout.addWidget(self.view)
        
    def getModel(self):
        return self.model
        
    def _handleReset(self):
        self.view.expandAll()