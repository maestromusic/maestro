#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt,SIGNAL

from omg import mpclient
from omg.models import playlist as playlistmodel
from . import delegates

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
        
        self.view = PlaylistTreeView(self)
        self.view.doubleClicked.connect(self._handleDoubleClick)
        
        self.model.modelReset.connect(self._handleReset)
        
        layout.addWidget(self.view)
        
    def getModel(self):
        return self.model
        
    def _handleReset(self):
        self.view.expandAll()
        
    def _handleDoubleClick(self,index):
        element = self.model.data(index)
        mpclient.play(element.getOffset())

class PlaylistTreeView(QtGui.QTreeView):
    """Specialized QTreeView, which draws the currently playing track highlighted."""
    def __init__(self,parent):
        QtGui.QTreeView.__init__(self,parent)
        self.setHeaderHidden(True)
        self.setModel(parent.model)
        self.setItemDelegate(delegates.PlaylistDelegate(self,parent.model))
        self.setExpandsOnDoubleClick(False)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Base,QtGui.QColor(0xE9,0xE9,0xE9))
        palette.setColor(QtGui.QPalette.AlternateBase,QtGui.QColor(0xD9,0xD9,0xD9))
        self.setPalette(palette)

    def keyReleaseEvent(self,keyEvent):
        if keyEvent.key() == Qt.Key_Delete:
            # It may happen that an element and its parent element are selected. When removing the parent, the element will also be removed and will disappear from selectedIndexes(). An easy solution like 
            # for i in selectedIndexes(): removeByQtIndex(i)
            # would try to remove the child a second time.
            while len(self.selectedIndexes()) > 0:
                self.parent().model.removeByQtIndex(self.selectedIndexes()[0])