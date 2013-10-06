# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import functools

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from .. import application, config, database as db, logging, utils, search as searchmodule
from ..core import tags, flags, levels
from ..core.elements import Element, Container
from ..search import searchbox, criteria
from . import mainwindow, treeactions, treeview, browserdialog, delegates, dockwidget
from .delegates import browser as browserdelegate
from ..models import browser as browsermodel


translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

defaultBrowser = None


class Browser(dockwidget.DockWidget):
    """Browser to search the music collection. The browser contains a searchbox, a button to open the
    configuration-dialog and one or more views. Depending on whether a search value is entered and/or a
    filterCriterion is set or not, the browser displays results from its search result table or from
    'elements' (the table currently used is stored in self.table).
    Each view has a list of layers that decide how to group the contents of the table. Typically each layer
    generates one level in the final tree structure. The contents of each node on this layer will then be
    grouped by the next layer. The last layer is always a ContainerLayer, that displays nodes in their tree
    structure.
    
    Usually layers create CriterionNodes to group elements (a CriterionNode contains those element of the
    set of elements displayed in the browser which match an additional search criterion). The contents of
    such a node will only be loaded when they are requested for the first time and to do so a search needs
    to be performed.
       
    Some of the more fancy features that only affect how nodes are displayed, include

         - Restore expanded: When the browser reloads its contents after a ChangeEvent it will try to restore
           previously expanded nodes.
         - Expand visible levels: The browser tries to expand as many full (tree structure) levels as
           possible. For this it will load (but not yet expand) nodes and compute their sizes until it is
           either clear, that the next level does not fit into the view or it can be expanded.
 
    """
    table = db.prefix + "elements" # The MySQL-table whose contents are currently displayed

    # Whether or not hidden values should be displayed.
    showHiddenValues = False
    
    # The current search request
    searchRequest = None
    
    # Called when the selection changes in any of the views
    selectionChanged = QtCore.pyqtSignal(QtGui.QItemSelectionModel,
                                         QtGui.QItemSelection, QtGui.QItemSelection)
    
    def __init__(self, parent=None, state=None, **args):
        """Initialize a new Browser with the given parent."""
        super().__init__(parent, **args)
        widget = QtGui.QWidget()
        self.setWidget(widget)
        
        self.views = [] # List of treeviews
        
        # These three criteria determine the set of elements displayed in the browser. They are combined
        # using AND.
        self.filterCriterion = None  # Used by the 'filter'-line edit in the option dialog 
        self.flagCriterion = None    # Used by the flags filter in the option dialog
        self.searchCriterion = None  # Used by the search box
                
        if browsermodel.searchEngine is None:
            browsermodel.initSearchEngine()
        
        # If one of above criteria is not None, this table contains the elements that should be displayed
        # and is used instead of 'elements'.
        self.resultTable = browsermodel.searchEngine.createResultTable('browser')
            
        browsermodel.searchEngine.searchFinished.connect(self._handleSearchFinished)
        
        # Layout
        layout = QtGui.QVBoxLayout(widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        
        controlLineLayout = QtGui.QHBoxLayout()
        self.searchBox = searchbox.SearchBox()
        self.searchBox.criterionChanged.connect(self.search)
        controlLineLayout.addWidget(self.searchBox)
        
        # This option button is only used when dock widget title bars are hidden (otherwise the dock widget
        # title bar contains an analogous button).
        self.optionButton = dockwidget.DockWidgetTitleButton('options')
        self.optionButton.clicked.connect(functools.partial(self.openOptionDialog, self.optionButton))
        controlLineLayout.addWidget(self.optionButton)
        self.optionButton.setVisible(mainwindow.mainWindow.hideTitleBarsAction.isChecked())
        layout.addLayout(controlLineLayout)
               
        self.splitter = QtGui.QSplitter(Qt.Vertical,self)
        layout.addWidget(self.splitter)
        
        # Restore state
        layersForViews = [self.defaultLayers()]
        self.delegateProfile = browserdelegate.BrowserDelegate.profileType.default()
        self.sortTags = {}
        if state is not None and isinstance(state, dict):
            if 'instant' in state:
                self.searchBox.setInstantSearch(state['instant'])
#            if 'showHiddenValues' in state:
#                self.showHiddenValues = state['showHiddenValues']
            if 'views' in state:
                layersForViews = []
                for layersConfig in state['views']:
                    layers = []
                    layersForViews.append(layers)
                    for layerConfig in layersConfig: 
                        try:
                            className, layerState = layerConfig
                            if className in browsermodel.layerClasses:
                                theClass = browsermodel.layerClasses[className][1]
                                layer = theClass(state=layerState)
                                layers.append(layer)
                        except Exception as e:
                            logger.warning("Could not parse a layer of the browser: {}".format(e))
                    viewsToRestore = state['views'] # TODO: unused variable?
            if 'flags' in state:
                flagList = [flags.get(name) for name in state['flags'] if flags.exists(name)]
                if len(flagList) > 0:
                    self.flagCriterion = criteria.FlagCriterion(flagList)
            if 'filter' in state:
                try:
                    self.filterCriterion = criteria.parse(state['filter'])
                except criteria.ParseException as e:
                    logger.warning("Could not parse the browser's filter criterion: {}".format(e))
            if 'delegate' in state:
                self.delegateProfile = delegates.profiles.category.getFromStorage(
                                                            state.get('delegate'),
                                                            browserdelegate.BrowserDelegate.profileType)
            
        application.dispatcher.connect(self._handleChangeEvent)
        levels.real.connect(self._handleChangeEvent)

        self.createViews(layersForViews)
        self.load()
        
        global defaultBrowser
        defaultBrowser = self

    def saveState(self):
        state = {
            'instant': self.searchBox.getInstantSearch(),
            #'showHiddenValues': self.showHiddenValues,
        }
        if len(self.views) > 0:
            state['views'] = [[(layer.className, layer.state()) for layer in view.model().layers]
                                 for view in self.views]
        if self.delegateProfile is not None:
            state['delegate'] = self.delegateProfile.name
        if self.filterCriterion is not None:
            state['filter'] = repr(self.filterCriterion)
        if self.flagCriterion is not None:
            state['flags'] = [flag.name for flag in self.flagCriterion.flags]
        return state
    
    def createViews(self, layersForViews):
        """Destroy all existing views and create views according to *layersForViews*: Each entry must be
        a list of layers for the corresponding view.
        """
        for view in self.views:
            view.setParent(None)
        self.views = []
        for layers in layersForViews:
            self.addView(layers, reset=False)
    
    def addView(self, layers=None, reset=True):
        """Add a view with the given layers."""
        if layers is None:
            layers = self.defaultLayers()
        return self.insertView(len(self.views), layers, reset)
    
    def insertView(self, index, layers, reset=True):
        """Insert a view with the given layers at position *index*."""
        newView = BrowserTreeView(self, layers, self.delegateProfile)
        self.views.insert(index, newView)
        newView.selectionModel().selectionChanged.connect(
                                functools.partial(self.selectionChanged.emit, newView.selectionModel()))
        self.splitter.insertWidget(index, newView)
        if reset:
            newView.resetToTable(self.table)
        return newView
        
    def removeView(self, index):
        """Remove the view with position *index* from the browser."""
        view = self.views[index]
        del self.views[index]
        view.setParent(None)
    
    def moveView(self, fromIndex, toIndex):
        """Move a view between two positions."""
        movingView = self.views[fromIndex]
        del self.views[fromIndex]
        self.views.insert(toIndex, movingView)
        self.splitter.insertWidget(toIndex, movingView) # will be removed from old position automatically
        
    def load(self):
        """Load contents into the browser, based on the current filterCriterion, flagCriterion and
        searchCriterion. If a search is necessary this will only start a search and actual loading will
        be done in _handleSearchFinished.
        """
        if self.searchRequest is not None:
            self.searchRequest.stop()
            self.searchRequest = None
            
        # Combine returns None if all input criteria are None
        criterion = criteria.combine('AND',
                            [c for c in (self.filterCriterion, self.flagCriterion, self.searchBox.criterion)
                             if c is not None])

        if criterion is not None:
            self.table = self.resultTable
            self.searchRequest = browsermodel.searchEngine.search(
                                                  fromTable = db.prefix+"elements",
                                                  resultTable = self.resultTable,
                                                  postProcessing = [searchmodule.findExtendedToplevel],
                                                  criterion = criterion)
            # view.resetToTable will be called when the search is finished
        else:
            self.table = db.prefix + "elements"
            for view in self.views:
                view.resetToTable(self.table)

    def search(self, searchString=None):
        """Search for the value in the searchbox. If it is empty, display all values. If *searchString*
        is given, write it into the searchbox and search for it.
        """
        #TODO: restoreExpanded if new criteria are narrower than the old ones?
        if searchString is not None:
            self.searchBox.setText(searchString)
        self.searchCriterion = self.searchBox.criterion
        self.load()
        
    def setFlagFilter(self, flags):
        """Set the browser's flag filter to the given list of flags."""
        if len(flags) == 0:
            if self.flagCriterion is not None:
                self.flagCriterion = None
                self.load()
        else:
            if self.flagCriterion is None or self.flagCriterion.flags != flags:
                self.flagCriterion = criteria.FlagCriterion(flags)
                self.load()
        
    def setFilterCriterion(self, criterion):
        """Set a single criterion that will be added to all other criteria from the searchbox (using AND)
        and thus form a permanent filter."""
        if criterion != self.filterCriterion:
            self.filterCriterion = criterion
            self.load()

    def getShowHiddenValues(self):
        """Return whether this browser should display ValueNodes where the hidden-flag in values_varchar is
        set."""
        return self.showHiddenValues
    
    def setShowHiddenValues(self,showHiddenValues):
        """Show or hide ValueNodes where the hidden-flag in values_varchar is set."""
        self.showHiddenValues = showHiddenValues
        for view in self.views:
            view.model().setShowHiddenValues(showHiddenValues)
        
    def _handleSearchFinished(self,request):
        """React to searchFinished signals: Set the table to self.resultTable and reset the model."""
        if request is self.searchRequest:
            self.searchRequest = None
            # Whether the view should restore expanded nodes after the search is stored in request.data.
            restore = request.data
            for view in self.views:
                view.expander = VisibleLevelsExpander(view)
                view.resetToTable(self.table)
                
    def _handleChangeEvent(self, event):
        """Handle a change event from the application's dispatcher or the real level."""
        #TODO: Optimize some cases in which we do not have to start a new search and reload everything.
        for view in self.views:
            view.expander = RestoreExpander(view)
        self.load()
    
    def createOptionDialog(self, parent):
        return browserdialog.BrowserDialog(parent, self)
    
    def _handleHideTitleBarAction(self, checked):
        super()._handleHideTitleBarAction(checked)
        if hasattr(self, 'optionButton'): # false during construction
            self.optionButton.setVisible(checked)
              
    @staticmethod
    def defaultLayers():
        """Return the default list of layers for a view."""
        tagList = browsermodel.TagLayer.defaultTagList()
        if len(tagList) > 0:
            return [browsermodel.TagLayer(tagList)]
        else: return []


mainwindow.addWidgetData(mainwindow.WidgetData(
        id = "browser",
        name = translate("Browser","Browser"),
        icon = utils.getIcon('widgets/browser.png'),
        theClass = Browser,
        central = False,
        preferredDockArea = Qt.LeftDockWidgetArea))


class BrowserTreeView(treeview.TreeView):
    """TreeView for the Browser. A browser may contain more than one view each using its own model. *parent*
    must be the browser-widget of this view. The *layers*-parameter determines how elements are grouped in
    this browser, see BrowserModel. *delegateProfile* is the profile passed to the BrowserDelegate instance.
    """
    actionConfig = treeview.TreeActionConfiguration()
    sect = translate("BrowserTreeView", "browser")
    actionConfig.addActionDefinition(((sect, 'value'),), treeactions.TagValueAction)
    sect = translate("BrowserTreeView", "elements")
    actionConfig.addActionDefinition(((sect, 'editTags'),), treeactions.EditTagsAction)
    actionConfig.addActionDefinition(((sect, 'rename'),), treeactions.RenameAction)
    actionConfig.addActionDefinition(((sect, 'delete'),), treeactions.DeleteAction,
                                     text=translate("BrowserTreeView", "Delete from OMG"))
    actionConfig.addActionDefinition(((sect, 'merge'),), treeactions.MergeAction)
    actionConfig.addActionDefinition(((sect, 'elementType'),), treeactions.ChangeElementTypeAction)
    actionConfig.addActionDefinition(((sect, 'position+'),), treeactions.ChangePositionAction, mode="+1")
    actionConfig.addActionDefinition(((sect, 'position-'),), treeactions.ChangePositionAction, mode="-1") 
    
    def __init__(self, browser, layers, delegateProfile):
        super().__init__(levels.real)
        self.browser = browser
        self.setModel(browsermodel.BrowserModel(self, layers))
        self.header().sectionResized.connect(self.model().layoutChanged)
        
        # If there are no contents, the browser model contains a help message (e.g. "no search results"),
        # which should not be decorated.
        self.setRootIsDecorated(self.model().hasContents())
        self.model().hasContentsChanged.connect(self.setRootIsDecorated)
        
        # Queued connection is necessary so that the model has really finished loading, when the view reacts.
        self.model().nodeLoaded.connect(self._handleNodeLoaded, Qt.QueuedConnection)
        
        self.setItemDelegate(browserdelegate.BrowserDelegate(self, delegateProfile))
        
        # The expander will decide which nodes to load/expand after the view is reset. Because each loading
        # might perform a search, Expanders work asynchronously.
        self.expander = None
        
    def focusInEvent(self, event):
        global defaultBrowser
        defaultBrowser = self.browser
        super().focusInEvent(event)
        
    def resetToTable(self, table):
        """Reset the view and its model so that it displays elements from *table*."""
        self.model().reset(table)
    
    def _handleNodeLoaded(self, node):
        """When a node has loaded in the model, allow the expander to expand it or load another node."""
        # Call the current expander so that it can decide what nodes should be loaded (or even expanded)
        if self.expander is not None:
            if not self.expander.next():
                self.expander = None
        # Always expand nodes with a single children (except RestoreExpander is active)
        if node.getContentsCount() == 1 and not isinstance(self.expander, RestoreExpander):
            self.expand(self.model().getIndex(node.contents[0]))
    
    def mouseDoubleClickEvent(self, event):
        # Because the must access modifiers, mouseDoubleClickEvent is used instead of the equivalent signal.
        index = self.indexAt(event.pos())
        if not index.isValid():
            return
        from . import playlist
        from .. import player
        if playlist.defaultPlaylist is None:
            return
        
        model = playlist.defaultPlaylist.model()
        if model.backend.connectionState != player.CONNECTED:
            return
        # TODO: this seems too complicated ...
        wrappers = [w.copy() for w in browsermodel.BrowserMimeData.fromIndexes(self.model(), [index]).wrappers()]
        if event.modifiers() & Qt.ControlModifier:
            model.stack.beginMacro(self.tr("Replace Playlist"))
            model.clear()
        insertOffset = model.root.fileCount()
        model.insert(model.root, len(model.root.contents), wrappers)
        if event.modifiers() & Qt.ControlModifier:
            model.backend.play()            
            model.stack.endMacro()
        elif model.backend.state() is player.STOP:
            model.backend.setCurrent(insertOffset)
            model.backend.play()
            

class RestoreExpander:
    """Expander that will store the current list of expanded nodes in *view* and expand them again bit by bit,
    whenever next is called (until next returns False). Expanded nodes will be stored by their data and not
    by reference/model index/persistent model index. Thus the expander also works if all nodes have been
    deleted and replaced by new instances with the same data.
    """ 
    def __init__(self, view):
        self.view = view
        self.expanded = self.getExpandedNodes(QtCore.QModelIndex())
        self.generator = self.expandedNodesGenerator()
                
    def getExpandedNodes(self, index):
        """Return all expanded nodes under the given model index in a dict mapping the key of an expanded
        node (see getKey) to a (recursive) dict of expanded nodes under that node.
        """
        model = self.view.model()
        result = {}
        for i in range(model.rowCount(index)):
            childIndex = model.index(i,0,index)
            if self.view.isExpanded(childIndex):
                child = model.data(childIndex,Qt.EditRole)
                result[self.getKey(child)] = self.getExpandedNodes(childIndex)
        return result
    
    def next(self):
        """Expand the next node and return True, or return False if all nodes have already been expanded."""
        try:
            next(self.generator)
            # Reaching this point means a node was expanded, that had not already loaded its contents.
            # Thus we have to wait until the search finishes and the signal is emitted again.
            return True
        except StopIteration:
            return False
        
    def getKey(self, node):
        """Get an identifier for *node*, which is unique among all siblings and will be the same for an
        equivalent node after reloading the model."""
        if isinstance(node, browsermodel.CriterionNode) and hasattr(node, 'getKey'):
            return node.getKey()
        elif isinstance(node, Element):
            return node.id    
        else: 
            # This works for nodeclasses of which not more than one instance has the same parent.
            # (e.g. HiddenValuesNode).
            return (node.__class__,)
        
    def expandedNodesGenerator(self):
        """Based on self.expanded, yield nodes that should be expanded."""
        model = self.view.model()
        #TODO: wtf is going on here
        listOfDicts = [self.expanded] # No need to copy although this will be modified below.
        listOfNodes = [model.getRoot()]
        while len(listOfDicts):
            currentDict = listOfDicts[-1]
            currentNode = listOfNodes[-1]
            if len(currentDict) == 0:
                listOfDicts.pop()
                listOfNodes.pop()
                continue
            key, expanded = currentDict.popitem()
            for child in currentNode.getContents():
                if key == self.getKey(child):
                    if len(expanded) > 0:
                        # After expanding this node, process expanded nodes below this one
                        listOfDicts.append(expanded)
                        listOfNodes.append(child)
                    # If this is a CriterionNode expanding the node will start a search and we have to wait.
                    mustSearch = isinstance(child, browsermodel.CriterionNode) and not child.hasLoaded()
                    self.view.expand(model.getIndex(child))
                    if mustSearch:
                        yield child
                    break
            

class VisibleLevelsExpander:
    """Expands whole (tree structure) levels at once as long as they fit into the view. Whenever the 'next'
    method is called, this expander will load (but not yet expand) a node on the next level that is not yet
    completely expanded. Then it computes the size of all contents. If they are too big to fit into the view,
    the expander stops. But if all contents have been loaded and fit, their parents will be expanded.
    """
    def __init__(self, view):
        self.view = view
        self._depthHeights = None
            
    def next(self):
        """Load the next node. Possibly expand a whole (tree structure) level."""
        maxHeight = self.view.maximumViewportSize().height()
        if self._depthHeights is None:
            # Calculate the height of the first level
            height = self._getHeightOfDepth(self.view.model().getRoot(), 1, maxHeight)
            if height is None or height < maxHeight:
                self._depthHeights = [height]
            else:
                # first level doesn't fit
                return False
        
        while True:
            # this is at least 2, since depthHeights is initialized with the height of depth 1 in
            # startAutoExpand. 
            depth = len(self._depthHeights)+1
            height = self._getHeightOfDepth(self.view.model().getRoot(),
                                            depth,
                                            maxHeight - sum(self._depthHeights))
            if height is None:
                return True # a node is not loaded yet, so wait for the next call
            if height == 0: # We have reached the last level
                return False
            self._depthHeights.append(height)
            if sum(self._depthHeights) <= maxHeight:
                # If two levels fit in the view, we want to expand up to depth 1.
                self.expandToDepth(depth-1)
            else:
                return False
    
    def _getHeightOfDepth(self, node, depth, maxHeight):
        """Caculate the height of all nodes of depth *depth* relative to their ancestor *node*. Stop when
        *maxHeight* is exceeded. If a node has not loaded its contents yet, start loading the contents and
        return None.
        """
        if not node.hasContents():
            return 0
        if isinstance(node, browsermodel.CriterionNode) and not node.hasLoaded():
            node.loadContents()
            return None
        height = 0
        for child in node.getContents():
            if depth == 1:
                height += self.view.itemDelegate().sizeHint(None, self.view.model().getIndex(child)).height()
            else:
                if node.hasContents() and not isinstance(node, browsermodel.HiddenValuesNode):
                    newHeight = self._getHeightOfDepth(child, depth-1, maxHeight-height)
                    if newHeight is None:
                        return None # A node is not loaded yet
                    else: height += newHeight
            if height > maxHeight:
                break
        return height
            
    def expandToDepth(self, depth, parent=None):
        """Expand all nodes up to *depth*. The root node is on depth 0, so *depth* should be at least 1.
        If *parent* is given, it is considered as root node, and only the tree below *parent* is affected.
        """
        if parent is None:
            parent = self.view.model().getRoot()
        for node in parent.contents:
            if node.hasContents() and not isinstance(node, browsermodel.HiddenValuesNode):
                self.view.expand(self.view.model().getIndex(node))
                if depth > 1:
                    self.expandToDepth(depth-1, parent=node)
