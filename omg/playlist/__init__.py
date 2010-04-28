#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import SIGNAL
from omg import constants, mpclient, tags
from . import playlistmodel, delegate

    
class Playlist(QtGui.QWidget):
    listView = None
    model = None
    
    def __init__(self,parent=None):
        QtGui.QWidget.__init__(self,parent)
        self.model = playlistmodel.PlaylistModel([playlistmodel.DataColumn('title'),playlistmodel.TagColumn(tags.ALBUM),playlistmodel.DataColumn('path'),playlistmodel.DataColumn('length')])
        
        # listView
        self.treeView = QtGui.QTreeView(self)
        self.treeView.setModel(self.model)
        self.treeView.setItemDelegate(delegate.Delegate(self,self.model))
        self.treeView.setRootIsDecorated(False)
        
        # ControlLine
        controlLineLayout = QtGui.QHBoxLayout()
        self.previousButton = QtGui.QPushButton(QtGui.QIcon(constants.IMAGES+"icons/previous.png"),'',self)
        self.ppButton = PPButton(self)
        self.stopButton = QtGui.QPushButton(QtGui.QIcon(constants.IMAGES+"icons/stop.png"),'',self)
        self.nextButton = QtGui.QPushButton(QtGui.QIcon(constants.IMAGES+"icons/next.png"),'',self)
        
        self.previousButton.clicked.connect(self._handlePrevious)
        self.ppButton.play.connect(mpclient.play)
        self.ppButton.pause.connect(mpclient.pause)
        self.stopButton.clicked.connect(self._handleStop)
        self.nextButton.clicked.connect(self._handleNext)
        
        controlLineLayout.addWidget(self.previousButton)
        controlLineLayout.addWidget(self.ppButton)
        controlLineLayout.addWidget(self.stopButton)
        controlLineLayout.addWidget(self.nextButton)
    
        layout = QtGui.QVBoxLayout(self)
        layout.addLayout(controlLineLayout)
        layout.addWidget(self.treeView)
        
    def addNode(self,node):
        elementList = node.retrieveElementList()
        self.model.setRoots([playlistmodel.ContainerNode(element) for element in elementList])
    
    def _handlePrevious(self,checked=False):
        mpclient.previous()
        
    def _handleNext(self,checked=False):
        mpclient.next()
        
    def _handleStop(self,checked=False):
        mpclient.stop()
        
        
class PPButton(QtGui.QPushButton):
    play = QtCore.pyqtSignal()
    pause = QtCore.pyqtSignal()
    playIcon = QtGui.QIcon(constants.IMAGES+"icons/play.png")
    pauseIcon = QtGui.QIcon(constants.IMAGES+"icons/pause.png")
    
    def __init__(self,parent):
        QtGui.QPushButton.__init__(self,self.playIcon,'',parent)
        self.playing = False
        self.clicked.connect(self._handleClicked)
    
    def _handleClicked(self,checked = False):
        if self.playing:
            self.setIcon(self.playIcon)
            self.pause.emit()
        else:
            self.setIcon(self.pauseIcon)
            self.play.emit()
        self.playing = not self.playing