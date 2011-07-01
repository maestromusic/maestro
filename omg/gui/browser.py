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
from . import mainwindow, treeview, browserdialog, delegates
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
    
    # The option dialog if it is open, and the index of the tab that was active when the dialog was closed
    _dialog = None
    _lastDialogTabIndex = 0
    
    # The current search request
    searchRequest = None
    
    def __init__(self,parent = None,state = None):
        """Initialize a new Browser with the given parent."""
        QtGui.QWidget.__init__(self,parent)
        self.browserKey = utils.getUniqueKey("browser")
        
        if browsermodel.searchEngine is None:
            browsermodel.initSearchEngine()
            
        browsermodel.searchEngine.searchFinished.connect(self._handleSearchFinished)
        self.bigResult = browsermodel.searchEngine.createResultTable("browser_big")
        
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
        
    def __del__(self):
        utils.freeUniqueKey(self.browserKey)

    def saveState(self):
        return {
            'instant': self.searchBox.getInstantSearch(),
            'showHiddenValues': self.showHiddenValues,
            'views': utils.mapRecursively(lambda tag: tag.name,[view.model().getLayers() for view in self.views])
        }
    
    def showElements(self):
        self.table = db.prefix + "elements"
        for view in self.views:
            view.model().setTable(self.table)
            view.model().reset()
            view.startAutoExpand()

    def search(self):
        """Search for the value in the search-box. If it is empty, display all values."""
        if self.searchRequest is not None:
            self.searchRequest.stop()
        criteria = self.searchBox.getCriteria()
        if len(criteria) > 0:
            self.table = self.bigResult
            self.searchRequest = browsermodel.searchEngine.search(
                                                        db.prefix+"elements",self.bigResult,criteria)
        else:
            self.showElements()
            self.searchRequest = None
    
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
        if self._dialog is None:
            self._dialog = browserdialog.BrowserDialog(self)
            self._dialog.tabWidget.setCurrentIndex(self._lastDialogTabIndex)
            pos = QtCore.QPoint(self.optionButton.x(),
                                self.optionButton.y()+self.optionButton.frameGeometry().height())
            self._dialog.move(self.mapTo(self.window(),pos))
            self._dialog.show()
    
    def _handleDialogClosed(self):
        # Note: This is called by the dialog and not by a signal
        self._lastDialogTabIndex = self._dialog.tabWidget.currentIndex()
        self._dialog = None
        
    def _handleSearchFinished(self,request):
        if request is self.searchRequest and not request.isStopped():
            for view in self.views:
                view.model().setTable(self.table)
                view.model().reset()
                view.startAutoExpand()


class BrowserTreeView(treeview.TreeView):
    """TreeView for the Browser."""
    _autoExpanding = False
    
    def __init__(self,parent,layers):
        """Initialize this TreeView with the given parent (which must be the browser-widget) and the given layers. This also will create a BrowserModel for this treeview (Note that each view of the browser uses its own model). <layers> must be a list of tag-lists. For each entry in <layers> a tag-layer using the entry's tags is created. A BrowserTreeView initialized with [[tags.get('genre')],[tags.get('artist'),tags.get('composer')]] will group result first into differen genres and then into different artist/composer-values, before finally displaying the elements itself."""
        treeview.TreeView.__init__(self,parent)
        self.contextMenuProviderCategory = 'browser'
        self.setModel(browsermodel.BrowserModel(parent.table,layers,parent))
        self.setItemDelegate(delegates.BrowserDelegate(self,self.model()))
        #self.doubleClicked.connect(self._handleDoubleClicked)
    
    def startAutoExpand(self):
        print("startAutoExpand")
        maxHeight = self.maximumViewportSize().height()
        # Calculate the height of the first level
        height = self._getHeightOfDepth(self.model().getRoot(),1,maxHeight)
        if height is None or height < maxHeight:
            self.depthHeights = [height]
            self._autoExpanding = True
            self.model().setAutoLoad(True)
            self.model().nodeLoaded.connect(self.autoExpand)
        else:
            self._autoExpanding = False
            self.model().setAutoLoad(False)
    
    def stopAutoExpand(self):
        self._autoExpanding = False
        self.model().setAutoLoad(False)
        
    def autoExpand(self):
        if not self._autoExpanding:
            return
        maxHeight = self.maximumViewportSize().height()
        while True:
            # this is at least 2, since depthHeights is initialized with the height of depth 1 in
            # startAutoExpand. 
            depth = len(self.depthHeights)+1
            height = self._getHeightOfDepth(self.model().getRoot(),depth,maxHeight-sum(self.depthHeights))
            if height is None:
                return # a node is not loaded yet, so wait for the next call
            if height == 0: # We have reached the last level
                self.stopAutoExpand()
                return
            self.depthHeights.append(height)
            if sum(self.depthHeights) <= maxHeight:
                # If two levels fit in the view, we want to expand up to depth 1. Qt counts from 0, thus -2.
                self.expandToDepth(depth-2)
            else:
                self.stopAutoExpand()
                return
    
    def _getHeightOfDepth(self,node,depth,maxHeight):
        if not node.hasContents():
            return 0
        if isinstance(node,browsermodel.CriterionNode) and not node.hasLoaded():
            return None
        height = 0
        for child in node.getContents():
            if depth == 1:
                height += self.itemDelegate().sizeHint(None,self.model().getIndex(child)).height()
            else:
                if node.hasContents():
                    newHeight = self._getHeightOfDepth(child, depth-1,maxHeight-height)
                    if newHeight is None:
                        return None # A node is not loaded yet
                    else: height += newHeight
            if height > maxHeight:
                break
        return height
