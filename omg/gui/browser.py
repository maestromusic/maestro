#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from .. import database as db, config, search, constants, utils, tags
from ..search import searchbox
from . import mainwindow, treeview, browserdialog
from ..models import browser as browsermodel
                         
translate = QtCore.QCoreApplication.translate


class BrowserDock(QtGui.QDockWidget):
    def __init__(self,parent=None,state=None):
        QtGui.QDockWidget.__init__(self,parent)
        self.setWindowTitle(self.tr("Browser"))
        self.browser = Browser(self,state)
        self.setWidget(self.browser)
        
    def saveState(self):
        return self.browser.saveState()


mainwindow.addWidgetData(mainwindow.WidgetData(
        id="browser",
        name=translate("Browser","Browser"),
        theClass = BrowserDock,
        central=False,
        dock=True,
        default=True,
        unique=False,
        preferredDockArea=Qt.LeftDockWidgetArea))


class Browser(QtGui.QWidget):
    """Browser-widget to search the music collection. The browser contains a searchbox, a button to open the configuration-dialog and one or more views. Depending on whether a search value is entered or not, the browser displayes results from TT_BIG_RESULT or 'elements' (the correct table is stored in self.table). Each view has a list of tag-sets ('layers') and will group the contents of self.table according to the layers."""
    
    views = None # List of BrowserTreeViews
    
    table = db.prefix + "elements" # The MySQL-table whose contents are currently displayed
    
    showHiddenValues = False
    
    def __init__(self,parent = None,state = None):
        """Initialize a new Browser with the given parent."""
        QtGui.QWidget.__init__(self,parent)

        self.searchEngine = search.SearchEngine()
        self.searchEngine.searchFinished.connect(self._handleSearchFinished)
        self.bigResult = self.searchEngine.createResultTable("browser_big")
        self.smallResult = self.searchEngine.createResultTable("browser_small")
        
        # Layout
        layout = QtGui.QVBoxLayout(self)
        self.setLayout(layout)    
        
        # ControlLine (containing searchBox and optionButton)
        controlLineLayout = QtGui.QHBoxLayout()
        layout.addLayout(controlLineLayout)
        
        self.searchBox = searchbox.SearchBox(self)
        self.searchBox.criteriaChanged.connect(self.search)
        controlLineLayout.addWidget(self.searchBox)
        
        self.optionButton = QtGui.QPushButton(self)
        self.optionButton.setIcon(utils.getIcon('options.png'))
        self.optionButton.clicked.connect(self._handleOptionButton)
        controlLineLayout.addWidget(self.optionButton)
        
        self.splitter = QtGui.QSplitter(Qt.Vertical,self)
        layout.addWidget(self.splitter)
        
        # Restore state
        viewsToRestore = config.storage.browser.views
        if state is not None and isinstance(state,dict):
            if 'instant' in state:
                self.searchBox.setInstantSearch(state['instant'])
            if 'showHiddenValues' in state:
                self.showHiddenValues = state['showHiddenValues']
            if 'views' in state:
                viewsToRestore = state['views']
                
        self.views = []
        # Convert tag names to tags, leaving the nested list structure unchanged
        self.createViews(utils.mapRecursively(tags.get,viewsToRestore))
        self.search() # Start an empty search to display all elements  
          
    def saveState(self):
        return {
            'instant': self.searchBox.getInstantSearch(),
            'showHiddenValues': self.showHiddenValues,
            'views': utils.mapRecursively(lambda tag: tag.name,[view.model().getLayers() for view in self.views])
        }
        
    def search(self):
        """Search for the value in the search-box. If it is empty, display all values."""
        criteria = self.searchBox.getCriteria()
        if len(criteria) > 0:
            self.searchEngine.runSearch(db.prefix+"elements",self.bigResult,criteria)
            self.table = self.bigResult
        else:
            self.table = db.prefix + "elements"
            self._handleSearchFinished()
    
    def createViews(self,layersList):
        """Destroy all existing views and create views according to <layersList>: For each entry of <layersList> a BrowserTreeView using the entry as layers is created. Therefore each entry of <layersList> must be a list of tag-lists (confer BrowserTreeView.__init__)."""
        for view in self.views:
            view.setParent(None)
        self.views = []
        for layers in layersList:
            newView = BrowserTreeView(self,layers)
            self.views.append(newView)
            self.splitter.addWidget(newView)

    def getShowHiddenValues(self):
        return self.showHiddenValues
    
    def setShowHiddenValues(self,showHiddenValues):
        self.showHiddenValues = showHiddenValues
        for view in self.views:
            view.setShowHiddenValues(showHiddenValues)
        
    def _handleOptionButton(self):
        dialog = browserdialog.BrowserDialog(self)
        pos = QtCore.QPoint(self.optionButton.x(),
                            self.optionButton.y()+self.optionButton.frameGeometry().height())
        dialog.move(self.mapTo(self.window(),pos))
        dialog.show()
    
    def _handleSearchFinished(self):
        for view in self.views:
            view.model().setTable(self.table)


class BrowserTreeView(treeview.TreeView):
    """TreeView for the Browser."""
    
    def __init__(self,parent,layers):
        """Initialize this TreeView with the given parent (which must be the browser-widget) and the given layers. This also will create a BrowserModel for this treeview (Note that each view of the browser uses its own model). <layers> must be a list of tag-lists. For each entry in <layers> a tag-layer using the entry's tags is created. A BrowserTreeView initialized with [[tags.get('genre')],[tags.get('artist'),tags.get('composer')]] will group result first into differen genres and then into different artist/composer-values, before finally displaying the elements itself."""
        treeview.TreeView.__init__(self,parent)
        self.contextMenuProviderCategory = 'browser'
        self.setModel(browsermodel.BrowserModel(parent.table,layers,parent.smallResult))
        #self.setItemDelegate(delegates.BrowserDelegate(self,self.model()))
        #self.doubleClicked.connect(self._handleDoubleClicked)
