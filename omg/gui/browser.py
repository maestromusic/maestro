#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from omg import database, search, tags, config, constants, models, strutils, control
from omg.models import browser as browsermodel

from . import delegates, browserdialog, formatter

# Temporary tables used for search results (have to appear before the imports as they will be imported in some imports)
TT_BIG_RESULT = 'tmp_browser_bigres'
TT_SMALL_RESULT = 'tmp_browser_smallres'

class Browser(QtGui.QWidget):
    """Browser-widget to search the music collection. The browser contains a searchbox, a button to open the configuration-dialog and one or more views. Depending on whether a search value is entered or not, the browser displayes results from TT_BIG_RESULT or 'elements' (the correct table is stored in self.table). Each view has a list of tag-sets ('layers') and will group the contents of self.table according to the layers."""
    
    views = None # List of BrowserTreeViews
    searchBox = None
    
    table = "elements" # The MySQL-table whose contents are currently displayed
    
    def __init__(self,parent = None):
        """Initialize a new Browser with the given parent."""
        QtGui.QWidget.__init__(self,parent)

        search.createResultTempTable(TT_BIG_RESULT,True)
        search.createResultTempTable(TT_SMALL_RESULT,True)
        
        # Layout
        layout = QtGui.QVBoxLayout(self)
        self.setLayout(layout)    
        
        # ControlLine (containing searchBox and optionButton)
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
            self.table = TT_BIG_RESULT
        else:
            self.table = "elements"
            database.get().query("TRUNCATE TABLE {0}".format(TT_BIG_RESULT))
        
        for view in self.views:
            view.model().setTable(self.table)
    
    def createViews(self,layersList):
        """Destroy all existing views and create views according to <layersList>: For each entry of <layersList> a BrowserTreeView using the entry as layers is created. Therefore each entry of <layersList> must be a list of tag-lists (confer BrowserTreeView.__init__)."""
        for view in self.views:
            view.setParent(None)
        self.views = []
        for layers in layersList:
            newView = BrowserTreeView(self,layers)
            self.views.append(newView)
            self.splitter.addWidget(newView)


class BrowserTreeView(QtGui.QTreeView):
    """TreeView for the Browser."""
    
    def __init__(self,parent,layers):
        """Initialize this TreeView with the given parent (which must be the browser-widget) and the given layers. This also will create a BrowserModel for this treeview (Note that each view of the browser uses its own model). <layers> must be a list of tag-lists. For each entry in <layers> a tag-layer using the entry's tags is created. A BrowserTreeView initialized with [[tags.get('genre')],[tags.get('artist'),tags.get('composer')]] will group result first into differen genres and then into different artist/composer-values, before finally displaying the elements itself."""
        QtGui.QTreeView.__init__(self,parent)
        self.setModel(browsermodel.BrowserModel(parent.table,layers,TT_SMALL_RESULT))
        
        self.setHeaderHidden(True)
        self.setItemDelegate(delegates.BrowserDelegate(self,self.model()))
        self.setExpandsOnDoubleClick(False)
        self.doubleClicked.connect(self._handleDoubleClicked)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Base,QtGui.QColor(0xE9,0xE9,0xE9))
        palette.setColor(QtGui.QPalette.AlternateBase,QtGui.QColor(0xD9,0xD9,0xD9))
        self.setPalette(palette)
        
        self.delAction = QtGui.QAction("delete", self)
        self.addAction(self.delAction)
        self.delAction.triggered.connect(self._deleteSelected)
            
    def _handleDoubleClicked(self,index):
        node = self.model().data(index)
        if isinstance(node,models.Element):
            control.playlist.insertElements([node],-1)
        elif isinstance(node,browsermodel.CriterionNode):
            control.playlist.insertElements(control.playlist.importElements(node.getElements()),-1)
    
    def _deleteSelected(self):
        """Non-recursively deletes the selected elements from the database."""
        sel = self.selectionModel().selection()
        for i in sel:
            parentIndex = i.topLeft().parent()
            parentElem = parentIndex.internalPointer()
            print(i.topLeft().internalPointer(), "-", i.bottomRight().internalPointer())
            self.model().beginRemoveRows(parentIndex, i.topLeft().row(), i.bottomRight().row())
            elems = (index.internalPointer() for index in i.indexes() if isinstance(index.internalPointer(), models.Element))
            for elem in elems:
                elem.delete(recursive = True)
            self.model().endRemoveRows()
            if isinstance(parentElem, models.Container):
                parentElem.updateElementCounter()
        
    def contextMenuEvent(self, event):
        menu = QtGui.QMenu(self)
        menu.addAction(self.delAction)
        menu.popup(event.globalPos())
        event.accept()
