#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

# Temporary tables used for search results (have to appear before the imports as they will be imported in some imports)
TT_BIG_RESULT = 'tmp_browser_bigres'
TT_SMALL_RESULT = 'tmp_browser_smallres'

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt,SIGNAL

from omg import search, tags, config, constants, models, control, strutils
from omg.models import rootedtreemodel
from . import delegates, browserdialog

class Browser(QtGui.QWidget):
    # The components of this browser
    views = None # QTreeViews
    searchBox = None
    
    # The TreeModel used to store the nodes in this browser.
    model = None
    
    # Root node
    root = None
    
    def __init__(self,parent,model=None):
        QtGui.QWidget.__init__(self,parent)
        self.model = model if model is not None else rootedtreemodel.RootedTreeModel() #forestmodel.ForestModel()
        
        search.createResultTempTable(TT_BIG_RESULT,True)
        search.createResultTempTable(TT_SMALL_RESULT,True)
        
        # Layout
        layout = QtGui.QVBoxLayout(self)
        self.setLayout(layout)    
        
        # ControlLine
        controlLineLayout = QtGui.QHBoxLayout()
        layout.addLayout(controlLineLayout)
        controlLineLayout.addWidget(QtGui.QLabel("Suche:",self))
        self.searchBox = QtGui.QLineEdit(self)
        self.searchBox.returnPressed.connect(self.search)
        controlLineLayout.addWidget(self.searchBox)
        optionButton = QtGui.QPushButton(self)
        optionButton.setIcon(QtGui.QIcon(constants.IMAGES+"icons/options.png"))
        optionButton.clicked.connect(lambda: browserdialog.BrowserDialog(self).exec_())
        controlLineLayout.addWidget(optionButton)
        
        self.splitter = QtGui.QSplitter(Qt.Vertical,self)
        layout.addWidget(self.splitter)
        
        self.views = []
        self.createViews(strutils.mapRecursively(tags.get,config.shelve['browser_views']))
    
    def search(self):
        """Search for the value in the search-box. If it is empty, display all values."""
        if self.searchBox.text():
            search.stdTextSearch(self.searchBox.text(),TT_BIG_RESULT)
            self.root.table = TT_BIG_RESULT
        else:
            database.get().query("TRUNCATE TABLE ?",TT_BIG_RESULT)
            self.root.table = "containers"
        self.model.reset()
    
    def createViews(self,layerList):
        for view in self.views:
            view.setParent(None)
        
        self.views = []
        for layers in layerList:
            newView = BrowserTreeView(self)
            newView.setLayers(layers)
            self.views.append(newView)
            self.splitter.addWidget(newView)
        
class BrowserTreeView(QtGui.QTreeView):
    def __init__(self,parent):
        QtGui.QTreeView.__init__(self,parent)
        self.setModel(parent.model)
        
        self.setHeaderHidden(True)
        self.setItemDelegate(delegates.BrowserDelegate(self,self.model()))
        self.setExpandsOnDoubleClick(False)
        self.doubleClicked.connect(self._handleDoubleClicked)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Base,QtGui.QColor(0xE9,0xE9,0xE9))
        palette.setColor(QtGui.QPalette.AlternateBase,QtGui.QColor(0xD9,0xD9,0xD9))
        self.setPalette(palette)
    
    def setLayers(self,layers):
        self.layers = layers
    
    def getLayers(self):
        return self.layers
        
    def _handleDoubleClicked(self,index):
        pass
        #~ node = self.model.data(index)
        #~ self.getParent().nodeDoubleClicked.emit(node)
        #~ if isinstance(node,nodes.ElementNode):
            #~ control.playlist.insertElements(control.playlist.importElements([node]),-1)
            #~ self.getParent().containerDoubleClicked.emit(models.Element(node.id))