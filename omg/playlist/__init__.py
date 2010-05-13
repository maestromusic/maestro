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
        self.view = QtGui.QTableView(self)
        self.view.setModel(self.model)
        self.view.setItemDelegate(delegate.Delegate(self,self.model))
        #self.treeView.setRootIsDecorated(False)
        
        layout = QtGui.QHBoxLayout(self)
        self.setLayout(layout)
        layout.addWidget(self.view)
        
    def getModel(self):
        return self.model