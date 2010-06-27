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
from PyQt4.QtCore import SIGNAL

from omg import search, tags, constants, models, control
from . import rootedtreemodel, nodes, layers, delegate, layouter

class Browser(QtGui.QWidget):
    # Maximal number of tag layers
    MAX_TAG_LAYER_NUMBER = 3
    
    # Tagsets which can be selected for a tag layer
    SELECTABLE_TAG_SETS = [(tags.ARTIST,tags.COMPOSER),(tags.ALBUM,),(tags.GENRE,)]
    
    # This list specifies the default tag layers: for each number n in this list a
    # tag layer with the tag-set SELECTABLE_TAG_SETS[n] will be generated.
    DEFAULT_TAG_LAYERS = [2,0]
    
    # The components of this browser
    browser = None # QTreeView
    searchBox = None
    optionButton = None
    
    # A list containing the actionGroups in the optionMenu which are used to specify the layers.
    actionGroups = None
    
    # The TreeModel used to store the nodes in this browser.
    model = None
    
    # Root node
    root = None
    
    # This signal is emitted when the user double-clicks on a node. The
    nodeDoubleClicked = QtCore.pyqtSignal(nodes.Node)
    containerDoubleClicked = QtCore.pyqtSignal(nodes.Node)

    def __init__(self,parent=None,model=None):
        QtGui.QWidget.__init__(self,parent)
        self.model = model if model is not None else rootedtreemodel.RootedTreeModel() #forestmodel.ForestModel()
        
        search.createResultTempTable(TT_BIG_RESULT,True)
        search.createResultTempTable(TT_SMALL_RESULT,True)
        
        # Browser
        self.browser = QtGui.QTreeView(self)
        self.browser.setHeaderHidden(True)
        self.browser.setModel(self.model)
        self.browser.setItemDelegate(delegate.Delegate(self,self.model,layouter.Layouter()))
        self.browser.setExpandsOnDoubleClick(False)
        self.browser.setDragEnabled(True)
        self.browser.setAcceptDrops(True)
        self.browser.setDropIndicatorShown(True)
        self.browser.doubleClicked.connect(self._handleDoubleClicked)
        self.model.browser = self.browser
        
        # OptionMenu
        optionMenu = QtGui.QMenu(self)
        self.actionGroups = []
        for i in range(self.MAX_TAG_LAYER_NUMBER):
            actionGroup = QtGui.QActionGroup(self)
            self.actionGroups.append(actionGroup)
            actionGroup.setExclusive(True)
            actionGroup.triggered.connect(self.updateLayers)
            subMenu = optionMenu.addMenu("Ebene {0}".format(i+1))
            action = QtGui.QAction("Keine",self)
            action.setCheckable(True)
            action.setActionGroup(actionGroup)
            subMenu.addAction(action)
            for tagSet in self.SELECTABLE_TAG_SETS:
                action = QtGui.QAction(", ".join([str(tag) for tag in tagSet]),self)
                action.setCheckable(True)
                action.setActionGroup(actionGroup)
                action.setData(tagSet)
                subMenu.addAction(action)
                
            if i < len(self.DEFAULT_TAG_LAYERS):
                # The +1 in the following line skips the "None" entry
                subMenu.actions()[self.DEFAULT_TAG_LAYERS[i]+1].setChecked(True)
            else: subMenu.actions()[0].setChecked(True) # Check the "None" entry
        
        # ControlLine
        self.searchBox = QtGui.QLineEdit(self)
        self.searchBox.returnPressed.connect(self.search)
        self.optionButton = QtGui.QToolButton(self)
        self.optionButton.setIcon(QtGui.QIcon(constants.IMAGES+"icons/options.png"))
        self.optionButton.setPopupMode(QtGui.QToolButton.InstantPopup)
        self.optionButton.setMenu(optionMenu)
        
        # Layout
        layout = QtGui.QVBoxLayout(self)
        controlLineLayout = QtGui.QHBoxLayout()
        layout.addLayout(controlLineLayout)
        layout.addWidget(self.browser)
        self.setLayout(layout)
        controlLineLayout.addWidget(QtGui.QLabel("Suche:",self))
        controlLineLayout.addWidget(self.searchBox)
        controlLineLayout.addWidget(self.optionButton)
        
        # Initialize
        self.updateLayers() # Create layers and content
    
    def updateLayers(self,action=None):
        self.layers = []
        for actionGroup in self.actionGroups:
            tagSet = actionGroup.checkedAction().data()
            if tagSet is not None:
                self.layers.append(layers.TagLayer(tagSet))
        self.layers.append(layers.ContainerLayer())
        # Each layer has a pointer to the next one
        previousLayer = self.layers[0]
        for layer in self.layers[1:]:
            previousLayer.nextLayer = layer
            previousLayer = layer
        oldTable = self.root.table if self.root is not None else "containers"
        self.root = nodes.RootNode(oldTable,self.model)
        self.root.nextLayer = self.layers[0]
        self.model.setRoot(self.root)
        self.model.reset()
        self.root.update()
        #printNode(self.root,0)
        
    def search(self):
        """Search for the value in the search-box. If it is empty, display all values."""
        if self.searchBox.text():
            search.stdTextSearch(self.searchBox.text(),TT_BIG_RESULT)
            self.root.table = TT_BIG_RESULT
        else:
            database.get().query("TRUNCATE TABLE ?",TT_BIG_RESULT)
            self.root.table = "containers"
        self.model.reset()
        self.root.update()
    
    def _handleDoubleClicked(self,index):
        node = self.model.data(index)
        self.nodeDoubleClicked.emit(node)
        if isinstance(node,nodes.ElementNode):
            control.playlist.insertElements(control.playlist.importElements([node]),-1)
            self.containerDoubleClicked.emit(models.Element(node.id))
        


def printNode(node,level):
    """Debugging method to print a node together with all of its children."""
    print(level*"    "+str(node))
    for element in node.getElements():
        printNode(element,level+1)