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

from .. import application, config, database as db, utils
from ..core import tags, flags, levels
from ..core.elements import Element, Container
from ..search import searchbox, criteria as criteriaModule
from . import mainwindow, treeview, browserdialog, delegates
from .delegates import browser as browserdelegate
from ..models import browser as browsermodel
from . import treeactions


translate = QtCore.QCoreApplication.translate


class BrowserDock(QtGui.QDockWidget):
    """DockWidget containing the Browser."""
    def __init__(self,parent=None,state=None,location=None):
        QtGui.QDockWidget.__init__(self,parent)
        self.setWindowTitle(self.tr("Browser"))
        browser = Browser(self,state)
        self.setWidget(browser)
        
    def saveState(self):
        return self.widget().saveState()
            

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
    """Browser to search the music collection. The browser contains a searchbox, a button to open the
    configuration-dialog and one or more views. Depending on whether search value is entered and/or a
    criterionFilter is set or not, the browser displays results from its bigResult-table or 'elements'
    (the table currently used is stored in self.table). Each view has a list of tag-sets ('layers') and will
    group the contents of self.table according to the layers: For each tag-set the view will contain a level
    of ValueNodes ('taglayer') that contain only elements with this value. After these taglayers the browser
    displays the contents in the usual tree structure ('container layer'). Currently only tags of type
    varchar may be used in the taglayers.
    
    ValueNodes will load their contents only when they are requested for the first time and to do so they
    will need to search from self.table to the smallResult-table used by all browsermodels together.
    
    More features:
    
        - Hidden values: Values from values_varchar with the hidden flag are stuffed into HiddenValueNodes
          (unless the showHiddenValues option is set to True).
        - Elements that don't have a value in any of the tags used in a taglayer are stuffed into a
          VariousNode (if a container has no artist-tag the reason is most likely that its children have
          different artists).
    
    Some of the more fancy features that only affect how nodes are displayed, include

         - RestoreExpandedOptimizer: When the browser reloads its contents after a ChangeEvent it will try
           to restore previously expanded nodes.
         - ExpandVisible: As long as the next level of (still unexpanded and not visible) nodes fits into the
           view, they are loaded automatically. If the whole next level fits into the view, it is expanded.
         - DirectLoad Shortcut: If a layer of ValueNodes happens to have only one value, this value is
           directly expanded without doing a new search (would give the same search results anyway)'
         - Merge ValueNodes Optimization: After AutoExpand (we need the contents to be loaded at least to the
           first layer of Elements) check whether there are ValueNodes containing the same elements and merge
           them.  
 
    \ """
    views = None # List of BrowserTreeViews
    table = db.prefix + "elements" # The MySQL-table whose contents are currently displayed

    # Whether or not hidden values should be displayed.
    showHiddenValues = False
    
    # The option dialog if it is open, and the index of the tab that was active when the dialog was closed.
    _dialog = None
    _lastDialogTabIndex = 0
    
    # The current search request
    searchRequest = None
    
    # Called when the selection changes in any of the views
    selectionChanged = QtCore.pyqtSignal(QtGui.QItemSelectionModel,
                                         QtGui.QItemSelection, QtGui.QItemSelection)
    
    def __init__(self,parent = None,state = None):
        """Initialize a new Browser with the given parent."""
        QtGui.QWidget.__init__(self,parent)
        self.criterionFilter = []
        self.searchCriteria = []
        self.views = []
        
        if browsermodel.searchEngine is None:
            browsermodel.initSearchEngine()
            
        browsermodel.searchEngine.searchFinished.connect(self._handleSearchFinished)
        self.bigResult = browsermodel.searchEngine.createResultTable("browser_big")
        
        # Layout
        layout = QtGui.QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
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
        self.delegateProfile = browserdelegate.BrowserDelegate.profileType.default()
        self.sortTags = {}
        if state is not None and isinstance(state,dict):
            if 'instant' in state:
                self.searchBox.setInstantSearch(state['instant'])
            if 'showHiddenValues' in state:
                self.showHiddenValues = state['showHiddenValues']
            if 'views' in state:
                viewsToRestore = state['views']
            if 'flags' in state:
                flagList = [flags.get(name) for name in state['flags'] if flags.exists(name)]
                if len(flagList) > 0:
                    self.criterionFilter.append(criteriaModule.FlagsCriterion(flagList))
            if 'delegate' in state:
                self.delegateProfile = delegates.profiles.category.getFromStorage(
                                                            state.get('delegate'),
                                                            browserdelegate.BrowserDelegate.profileType)
            if 'sortTags' in state:
                for tagName,tagList in state['sortTags'].items():
                    if tags.exists(tagName):
                        tagList = [tags.get(name) for name in tagList if tags.exists(name)]
                        if len(tagList) > 0:
                            self.sortTags[tags.get(tagName)] = tagList
            elif tags.exists('artist') and tags.exists('date'):
                # Load a reasonable default
                self.sortTags = {tags.get('artist'): [tags.get('date')]}
            
        application.dispatcher.connect(self._handleDispatcher)
        levels.real.connect(self._handleLevelChange)
        
        # Convert tag names to tags, leaving the nested list structure unchanged.
        # This will in particular call self.load
        self.createViews(utils.mapRecursively(tags.get,viewsToRestore))

    def saveState(self):
        # Get the flags from self.criterionFilter
        # When a general criterionfilter is implemented we will store the filter itself as string
        # (e.g. '{flag:piano} Concert') instead of a list of flags.
        flags = []
        for criterion in self.criterionFilter:
            if isinstance(criterion,criteriaModule.FlagsCriterion):
                flags.extend(criterion.flags)
        state = {
            'instant': self.searchBox.getInstantSearch(),
            'showHiddenValues': self.showHiddenValues,
            'views': utils.mapRecursively(lambda tag: tag.name,[view.model().layers for view in self.views]),
            'flags': [flagType.name for flagType in flags],
            'sortTags': {tag.name: [t.name for t in sortTags] for tag,sortTags in self.sortTags.items()}
        }
        if self.delegateProfile is not None:
            state['delegate'] = self.delegateProfile.name
        return state
    
    def load(self,restoreExpanded=False):
        """Load contents into the browser, based on the current criterionFilter and searchCriteria. If a
        search is necessary this will only start a search and actual loading will be done in
        _handleSearchFinished. If *restoreExpanded* is True all views will store the expanded nodes and try
        to restore them again after reloading.
        """
        criteria = self.criterionFilter + self.searchCriteria
        # This will effectively stop any request from being processed
        if self.searchRequest is not None:
            self.searchRequest.stop()
            self.searchRequest = None

        if len(criteria) > 0:
            self.table = self.bigResult
            self.searchRequest = browsermodel.searchEngine.search(fromTable = db.prefix+"elements",
                                                                  resultTable = self.bigResult,
                                                                  criteria = criteria,
                                                                  data = restoreExpanded
                                                                )
            # view.resetToTable will be called when the search is finished
        else:
            self.table = db.prefix + "elements"
            self.searchRequest = None
            for view in self.views:
                view.resetToTable(self.table,restoreExpanded=restoreExpanded,
                                  expandVisible=not restoreExpanded)

    def search(self):
        """Search for the value in the search-box. If it is empty, display all values."""
        #TODO: restoreExpanded if new criteria are narrower than the old ones?
        self.searchCriteria = self.searchBox.getCriteria()
        self.load()
    
    def createViews(self,layersList):
        """Destroy all existing views and create views according to *layersList*: For each entry of
        *layersList* a BrowserTreeView using the entry as layers is created. Therefore each entry of
        *layersList* must be a list of tag-lists (confer BrowserTreeView.__init__).
        """
        for view in self.views:
            view.setParent(None)
        self.views = []
        for layers in layersList:
            newView = BrowserTreeView(self,layers,self.sortTags,self.delegateProfile)
            self.views.append(newView)
            newView.selectionModel().selectionChanged.connect(
                                    functools.partial(self.selectionChanged.emit,newView.selectionModel()))
            self.splitter.addWidget(newView)
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
    
    def setCriterionFilter(self,criteria):
        """Set the criterion filter. This is a list of criteria that will be prepended to the search criteria
        from the searchbox and thus form a permanent filter."""
        if criteria != self.criterionFilter:
            self.criterionFilter = criteria[:]
            self.load()
            
    def _handleOptionButton(self):
        """Open the option dialog."""
        if self._dialog is None:
            self._dialog = browserdialog.BrowserDialog(self)
            self._dialog.tabWidget.setCurrentIndex(self._lastDialogTabIndex)
            self._dialog.show()
    
    def _handleDialogClosed(self):
        """Close the option dialog."""
        # Note: This is called by the dialog and not by a signal
        if self._dialog is not None:
            self._lastDialogTabIndex = self._dialog.tabWidget.currentIndex()
            self._dialog = None
        
    def _handleSearchFinished(self,request):
        """React to searchFinished signals: Set the table to self.bigResult and reset the model."""
        if request is self.searchRequest:
            self.searchRequest = None
            # Whether the view should restore expanded nodes after the search is stored in request.data.
            restore = request.data
            for view in self.views:
                view.resetToTable(self.table,restoreExpanded=restore,expandVisible=not restore)
                
    def _handleDispatcher(self,event):
        """Handle a change event."""
        #TODO: Optimize some cases in which we do not have to start a new search and reload everything.
        self.load(restoreExpanded = True)
    
    def _handleLevelChange(self,event):
        self.load(restoreExpanded = True)
        pass


class BrowserTreeView(treeview.TreeView):
    """TreeView for the Browser. A browser may contain more than one view each using its own model. *parent*
    must be the browser-widget of this view. The *layers*-parameter determines how elements are grouped in
    this browser: It must be a list of tag-lists. For each entry in *layers* a tag-layer using the entry's
    tags is created. A BrowserTreeView initialized with
        [[tags.get('genre')],[tags.get('artist'),tags.get('composer')]]
    will group result first into different genres and then into different artist/composer-values, before
    finally displaying the elements itself."""
    
    # List of optimizers which will improve the display after reloading.
    _optimizers = None
    
    actionConfig = treeview.TreeActionConfiguration()
    sect = translate("BrowserTreeView", "browser")
    actionConfig.addActionDefinition(((sect, 'value'),), treeactions.TagValueAction)
    sect = translate("BrowserTreeView", "elements")
    actionConfig.addActionDefinition(((sect, 'editTags'),), treeactions.EditTagsAction, recursive=False)
    actionConfig.addActionDefinition(((sect, 'editTagsR'),), treeactions.EditTagsAction, recursive=True)
    actionConfig.addActionDefinition(((sect, 'remove'),), treeactions.RemoveFromParentAction)
    actionConfig.addActionDefinition(((sect, 'rename'),), treeactions.RenameAction)
    actionConfig.addActionDefinition(((sect, 'delete'),), treeactions.DeleteAction,
                                     text=translate("BrowserTreeView", "delete from OMG"))
    actionConfig.addActionDefinition(((sect, 'merge'),), treeactions.MergeAction)
    actionConfig.addActionDefinition(((sect, 'major?'),), treeactions.ToggleMajorAction)
    actionConfig.addActionDefinition(((sect, 'position+'),), treeactions.ChangePositionAction, mode="+1")
    actionConfig.addActionDefinition(((sect, 'position-'),), treeactions.ChangePositionAction, mode="-1") 
    
    def __init__(self,parent,layers,sortTags,delegateProfile):
        super().__init__(levels.real,parent)
        self.setModel(browsermodel.BrowserModel(layers,sortTags))
        self.setRootIsDecorated(self.model().hasContents())
        self.model().hasContentsChanged.connect(self.setRootIsDecorated)
        self.header().sectionResized.connect(self.model().layoutChanged)
        self.setItemDelegate(browserdelegate.BrowserDelegate(self,delegateProfile))
        self._optimizers = []
        #self.doubleClicked.connect(self._handleDoubleClicked)
    
    def resetToTable(self,table,restoreExpanded,expandVisible):
        """Reset the view and its model so that it displays elements from *table*. If *restoreExpanded* is
        True, try to restore expanded nodes after reloading. If *expandVisible* is True, automatically 
        expand as much layers as are possible without vertical scrollbar.
        """
        if len(self._optimizers) > 0:
            # Disconnect or otherwise the next optimizer will be started via the finished signal.
            self._optimizers[-1].finished.disconnect(self._handleOptimizerFinished)
            self._optimizers[-1].stop()
        self._optimizers = []
        
        # The order of the optimizers is very important!
        if restoreExpanded:
            self._optimizers.append(RestoreExpandedOptimizer(self))
        if expandVisible:
            self._optimizers.append(ExpandVisibleOptimizer(self))
        self._optimizers.append(ExpandSingleOptimizer(self))
        #self._optimizers.append(MergeValueNodesOptimizer(self))
        
        self.model().reset(table)
        
        if len(self._optimizers) > 0:
            for optimizer in self._optimizers:
                optimizer.finished.connect(self._handleOptimizerFinished)
            self._optimizers[0].start()
        
    def _handleOptimizerFinished(self):
        """Handle the finished-signal from the current optimizer."""
        if len(self._optimizers) == 0:
            # This happens when resetToTable is called and the optimizers are cleared
            # before the already emitted signal is processed.
            return
        optimizer = self._optimizers.pop(0)
        optimizer.finished.disconnect(self._handleOptimizerFinished)
        if len(self._optimizers) > 0:
            self._optimizers[0].start()
    
    def mouseDoubleClickEvent(self, event):
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
        model.insert(model.root, len(model.root.contents), wrappers)
        if event.modifiers() & Qt.ControlModifier:
            model.backend.play()
            model.stack.endMacro()
        
       
class Optimizer(QtCore.QObject):
    """Optimizers improve the display of a BrowserTreeView after its nodes have been loaded. They are 
    created before the model is reset and thus may store information as currently expanded nodes. After
    the nodes have been loaded, ''start'' is called."""
    finished = QtCore.pyqtSignal()
    
    def __init__(self,view):
        super().__init__(view)
        self.view = view

    def start(self):
        pass
    
    def stop(self):
        pass
 
 
class ExpandSingleOptimizer(Optimizer):
    """Optimizer which expands single nodes and stops when a level contains more than one node. Note that
    this is not necessarily done by the ExpandVisibleOptimizer because it might make a vertical scrollbar
    necessary. Thanks to the DirectLoad-shortcut of BrowserModel, this optimizer does not have to load
    nodes and can thus finish immediately."""
    def start(self):
        node = self.view.model().getRoot()
        while (not isinstance(node,browsermodel.CriterionNode) or node.hasLoaded()) \
                and node.getContentsCount() == 1:
            node = node.getContents()[0]
            self.view.expand(self.view.model().getIndex(node))

        self.finished.emit()


class RestoreExpandedOptimizer(Optimizer):
    def __init__(self,view):
        super().__init__(view)
        self._expanded = self._getExpandedNodes(QtCore.QModelIndex())
        self._stopped = True
    
    def start(self):
        self.view.model().nodeLoaded.connect(self._handleNodeLoaded)
        self._generator = self._expandedNodesGenerator()
        self._stopped = False
        self._handleNodeLoaded(None)
        
    def stop(self):
        self._stopped = True            
        self.view.model().nodeLoaded.disconnect(self._handleNodeLoaded)
        self.finished.emit()
                
    def _getExpandedNodes(self,index):
        model = self.view.model()
        result = {}
        for i in range(model.rowCount(index)):
            childIndex = model.index(i,0,index)
            if self.view.isExpanded(childIndex):
                child = model.data(childIndex,Qt.EditRole)
                # Get an identifier for this node, which is unique among all siblings and will be the same
                # for an equivalent node after reloading the model.
                if isinstance(child,browsermodel.ValueNode):
                    key = child.getKey()
                elif isinstance(child, Element):
                    key = child.id    
                else: 
                    # This works for nodeclasses of which not more than one instance has the same parent.
                    # (e.g. HiddenValuesNode).
                    key = (child.__class__,)
                result[key] = self._getExpandedNodes(childIndex)
        return result
    
    def _handleNodeLoaded(self,node=None):
        if self._stopped:
            return
        try:
            next(self._generator)
            # Reaching this point means a node was expanded, that had not already loaded its contents.
            # Thus we have to wait until the search finishes and the signal is emitted again.
            return
        except StopIteration:
            self.stop()
    
    def _expandedNodesGenerator(self):
        model = self.view.model()
        listOfDicts = [self._expanded] # No need to copy although this will be modified below.
        listOfNodes = [model.getRoot()]
        while len(listOfDicts):
            currentDict = listOfDicts[-1]
            currentNode = listOfNodes[-1]
            if len(currentDict) == 0:
                listOfDicts.pop()
                listOfNodes.pop()
                continue
            key,expanded = currentDict.popitem()
            for child in currentNode.getContents():
                if (isinstance(child,browsermodel.ValueNode) and child.getKey() == key) \
                            or (isinstance(child,Container) and child.id == key) \
                            or (key == (child.__class__,)):
                    if len(expanded) > 0:
                        # After expanding this node, process expanded nodes below this one
                        listOfDicts.append(expanded)
                        listOfNodes.append(child)
                    # If this is a CriterionNode expanding the node will start a search and we have to wait.
                    mustSearch = isinstance(child,browsermodel.CriterionNode) and not child.hasLoaded()
                    self.view.expand(model.getIndex(child))
                    if mustSearch:
                        yield child
                    break
            
    
class ExpandVisibleOptimizer(Optimizer):
    def start(self):
        """Start AutoExpand: Calculate the height of all nodes with depth 1. If they fit into the view and
        there is still place left, load the contents of those nodes (using the AutoLoad feature of
        BrowserModel) until all nodes of depth 2 are loaded or the height of the loaded nodes together with
        all nodes of depth 1 exceeds the height of the view. In the first case expand all nodes of depth 1
        and continue with the next level. In the second case it is clear that we cannot display all nodes of
        depth 2, so stop AutoExpand and AutoLoad.
        
        Because loading contents involves searches the _autoExpand-method needs to be called repeatedly after
        each search.
        """
        self._autoExpandDepth = 0
        maxHeight = self.view.maximumViewportSize().height()
        # Calculate the height of the first level
        height = self._getHeightOfDepth(self.view.model().getRoot(),1,maxHeight)
        if height is None or height < maxHeight:
            self._depthHeights = [height]
            self.view.model().nodeLoaded.connect(self._handleNodeLoaded)
            self._handleNodeLoaded()
        else:
            self.finished.emit()
            
    def stop(self):
        self.view.model().nodeLoaded.disconnect(self._handleNodeLoaded)
        self.finished.emit()
            
    def _handleNodeLoaded(self):
        """This is called at the start of AutoExpand and (by the model) whenever the contents of a node has
        been loaded. The method will calculate the height of all nodes of the visible depths and of the
        nodes whose contents are already loaded on the next level and
        
            - stop AutoExpand and AutoLoad if the next level doesn't fit into the view
            - expand to the next level if all nodes are loaded and it does fit
            - load a node if the next level may fit into the view and we need the contents to find out.
              autoExpand will be called again from BrowserModel._handleSearchFinished.
            
        \ """
        maxHeight = self.view.maximumViewportSize().height()
        while True:
            # this is at least 2, since depthHeights is initialized with the height of depth 1 in
            # startAutoExpand. 
            depth = len(self._depthHeights)+1
            height = self._getHeightOfDepth(self.view.model().getRoot(),
                                            depth,maxHeight-sum(self._depthHeights))
            if height is None:
                return # a node is not loaded yet, so wait for the next call
            if height == 0: # We have reached the last level
                self.stop()
                return
            self._depthHeights.append(height)
            if sum(self._depthHeights) <= maxHeight:
                self._autoExpandDepth = depth
                #print("Expanding to depth {}".format(depth-2))
                # If two levels fit in the view, we want to expand up to depth 1. Qt counts from 0, thus -2.
                self.view.expandToDepth(depth-2)
            else:
                self.stop()
                return
    
    def _getHeightOfDepth(self,node,depth,maxHeight):
        """Caculate the height of all nodes of depth *depth* relative to their ancestor *node*. Stop when
        *maxHeight* is exceeded. If a node has not loaded its contents yet, start loading the contents and
        return None.
        """
        if not node.hasContents():
            return 0
        if isinstance(node,browsermodel.CriterionNode) and not node.hasLoaded():
            node.loadContents()
            return None
        height = 0
        for child in node.getContents():
            if depth == 1:
                height += self.view.itemDelegate().sizeHint(None,self.view.model().getIndex(child)).height()
            else:
                if node.hasContents():
                    newHeight = self._getHeightOfDepth(child, depth-1,maxHeight-height)
                    if newHeight is None:
                        return None # A node is not loaded yet
                    else: height += newHeight
            if height > maxHeight:
                break
        return height


class MergeValueNodesOptimizer(Optimizer):
    """After AutoExpand (we need the contents to be loaded at least to the first layer of Elements) check
    whether there are ValueNodes containing the same elements and merge them.
    
    This method optimizes the ValueNodes below *node* and returns the toplevel element contents of *node*
    as set. If any node below *node* has not loaded its contents, this method returns None.
    """
    def start(self):
        self._optimize(self.view.model().getRoot())
        self.finished.emit()
        
    def _optimize(self,node):
        model = self.view.model()
        
        # Later this set will contain the element-ids of all toplevel elements that are recursively
        # contained in this node (it will only contain elements whose direct parent is a ValueNode).
        contentIds = set()
        
        # This maps hashes of contents (ordered tuples of contentIds to be precise) to the child of *node*
        # containing those contents.
        contentDict = {}
        
        # Set to false if a child has not fully loaded its contents.
        loaded = True
        
        # Copy the list as contents may change.
        for child in node.getContents()[:]: 
            if isinstance(child,Element):
                contentIds.add(child.id)
                continue
            if not isinstance(child,browsermodel.ValueNode):
                # TODO: Handle VariousNodes, HiddenValuesNodes
                continue
            if not child.hasLoaded():
                loaded = False
                continue
            
            # First optimize the nodes below child and get the contents
            subContentIds = self._optimize(child)
            if subContentIds is None: # child has not fully loaded its contents
                loaded = False
                continue
                
            # Calculate the hash used to compare contents. It is important to sort the ids because often the
            # children are sorted differently depending on the value of node (e.g. when using a layer with
            # artist and composer tags, having sorttags date for artist and title for composer).
            contentHash = hash(tuple(sorted(subContentIds)))
            
            if contentHash not in contentDict:
                contentDict[contentHash] = child
                contentIds.update(subContentIds)
            else:
                # Yeah! We found two children with the same contents
                contentDict[contentHash].addValues(child)
                position = node.index(child)
                model.beginRemoveRows(model.getIndex(node),position,position)
                del node.contents[position]
                model.endRemoveRows()
            
        if loaded:
            return contentIds
        else: return None
          
