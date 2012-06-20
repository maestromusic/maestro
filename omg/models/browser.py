# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

import itertools

from PyQt4 import QtCore
from PyQt4.QtCore import Qt

from . import rootedtreemodel, mimedata
from .. import config, search, database as db, logging, utils
from ..core import tags, levels
from ..core.elements import Element
from ..core.nodes import Node, RootNode, Wrapper
from ..gui import selection

logger = logging.getLogger(__name__)

searchEngine = None # The search engine used by all browsers

# This result table is used when a CriterionNode is expanded. It is common to all browsers, in contrast to
# the bigResult-table of a browser in which it will store the results of user searches.
smallResult = None


def initSearchEngine():
    """Initialize the single search engine used by all browsers. This is called automatically, when the first
    browser is created."""
    global searchEngine, smallResult
    if searchEngine is None:
        searchEngine = search.SearchEngine()
        smallResult = searchEngine.createResultTable("browser_small")


class BrowserModel(rootedtreemodel.RootedTreeModel):
    """ItemModel for the BrowserTreeViews (a browser may have several views and hence several models). The
    model will group its contents according to the parameter *layers*.
    """
    showHiddenValues = False

    _searchRequests = None
    
    nodeLoaded = QtCore.pyqtSignal(Node)
    
    def __init__(self,layers,sortTags):
        super().__init__(BrowserRootNode(self))
        self.table = None
        self.level = levels.real
        self.layers = layers
        self.sortTags = sortTags
        self._searchRequests = []
        
        if searchEngine is None:
            initSearchEngine()
        
        searchEngine.searchFinished.connect(self._handleSearchFinished)
    
    def reset(self,table=None):
        """Reset the model reloading all data from self.table. If *table* is given, first set self.table to
        *table*."""
        for request in self._searchRequests:
            request.stop()
        self._searchRequests = [] # Avoid handling requests whose finished-signal is already in the queue.
        
        if table is not None:
            self.table = table
        if self.table is not None:
            self._startLoading(self.root)
            rootedtreemodel.RootedTreeModel.reset(self)
    
    def getShowHiddenValues(self):
        """Return whether the browser-view with this model should display ValueNodes where the hidden-flag in
        values_varchar is set."""
        return self.showHiddenValues
    
    def setShowHiddenValues(self,showHiddenValues):
        """Show or hide ValueNodes where the hidden-flag in values_varchar is set."""
        if showHiddenValues != self.showHiddenValues:
            self.showHiddenValues = showHiddenValues
            self.reset()
            
    def flags(self,index):
        defaultFlags = rootedtreemodel.RootedTreeModel.flags(self,index)
        if index.isValid():
            return defaultFlags | Qt.ItemIsDragEnabled
        else: return defaultFlags
    
    def mimeTypes(self):
        return [config.options.gui.mime]
        
    def mimeData(self,indexes):
        return BrowserMimeData.fromIndexes(self,indexes)

    def _startLoading(self,node,wait=False):
        """Start loading the contents of *node*, which must be either root or a CriterionNode (The contents of
        containers are loaded via Container.loadContents). If *node* is a CriterionNode, start a search for
        the contents. The actual loading will be done in the searchFinished event. Only the rootnode is
        loaded directly. If *wait* is True this method will wait until the node is loaded. 
        """
        assert node == self.root or isinstance(node,CriterionNode)
        
        if node == self.root:
            # No need to search...load directly
            if len(self.layers) > 0:
                self._loadTagLayer(node,self.table)
            else: self._loadContainerLayer(node,self.table)
        else:
            method = searchEngine.search if not wait else searchEngine.searchAndWait
            # Collect the criteria in this node and its parents and put the search results into smallResult
            searchRequest = method(self.table,smallResult,node._collectCriteria(),data=node,lockTable=True)
            self._searchRequests.append(searchRequest)
            if wait:
                # Search is finished.
                self._handleSearchFinished(searchRequest)
            # else: Wait for searchFinished...somewhat paradoxical :-)
            
    def _handleSearchFinished(self,searchRequest):
        """Handle the searchFinished-event for *searchRequest*: Load the contents of the node
        ''searchRequest.data'' and emit a nodeLoaded signal.
        """
        if searchRequest in self._searchRequests:
            # Determine whether to load a tag-layer or the container-layer at the bottom of the tree.
            node = searchRequest.data
            if node.layerIndex+1 < len(self.layers):
                self._loadTagLayer(node,smallResult)
            else: self._loadContainerLayer(node,smallResult)
            searchRequest.releaseTable()
            self._searchRequests.remove(searchRequest)
            self.nodeLoaded.emit(node)
            return
    
    def _loadTagLayer(self,node,table):
        """Load the contents of *node* into a tag-layer, using elements from *table*."""
        tagSet = self.layers[node.layerIndex+1]
        if any(tag.type != tags.TYPE_VARCHAR for tag in tagSet):
            logger.warning("Only tags of type varchar are permitted in the browser's layers.")
            tagSet = {tag for tag in tagSet if tag.type == tags.TYPE_VARCHAR}
        
        # Get all values and corresponding ids of the given tag appearing in at least one toplevel result.
        result = db.query("""
            SELECT DISTINCT t.tag_id,v.id,v.value,v.hide,v.sort_value
            FROM {1} AS res JOIN {0}tags AS t ON res.id = t.element_id
                     JOIN {0}values_varchar AS v ON t.tag_id = v.tag_id AND t.value_id = v.id
            WHERE res.toplevel = 1 AND t.tag_id IN ({2})
            ORDER BY COALESCE(v.sort_value,v.value)
        """.format(db.prefix,table,",".join(str(tag.id) for tag in tagSet)))
    
        valueNodes = []
        hiddenNodes = []
        values = set()
    
        for row in result:
            tagId,valueId,value,hide,sortValue = row
            if db.isNull(sortValue):
                sortValue = None
                
            if self.showHiddenValues or not hide:
                theList = valueNodes
            else: theList = hiddenNodes
            
            if value not in values:
                theList.append(ValueNode(node,self,value,{tagId:valueId},sortValue))
                values.add(value)
            else:
                # If there is already a value node with this value,
                # add tagId -> valueId to that node
                for aNode in theList:
                    if value in aNode.values:
                        aNode.valueIds[tagId] = valueId
                        break
    
        # Check whether a VariousNode is necessary
        result = db.query("""
            SELECT t.value_id
            FROM {1} AS res LEFT JOIN {0}tags AS t
                                ON res.id = t.element_id AND t.tag_id IN ({2})
            WHERE t.value_id IS NULL
            LIMIT 1
            """.format(db.prefix,table,",".join(str(tag.id) for tag in tagSet)))

        if len(result) > 0:
            valueNodes.append(VariousNode(node,self,tagSet))
            
        if len(hiddenNodes) > 0:
            valueNodes.append(HiddenValuesNode(node,hiddenNodes))
        
        if node.contents is not None: # Confer the corresponding comment in _loadContainerLayer
            self.beginRemoveRows(self.getIndex(node),0,len(node.contents)-1)
            node.setContents([])
            self.endRemoveRows()
            if len(valueNodes) > 0:
                self.beginInsertRows(self.getIndex(node),0,len(valueNodes)-1)
                node.setContents(valueNodes)
                self.endInsertRows()
        elif len(valueNodes) > 0:
            node.setContents(valueNodes)
    
        # Directload shortcut
        # Tag-layers containing only one CriterionNode are not helpful, so if this happens load the contents
        # of the only CriterionNode. There is no need to search because it would give the same results.
        if len(valueNodes) == 1:
            if node.layerIndex+2 < len(self.layers):
                self._loadTagLayer(valueNodes[0],table)
            else: self._loadContainerLayer(valueNodes[0],table)

    def _loadContainerLayer(self,node,table):
        """Load the contents of *node* into a container-layer, using toplevel elements from *table*. Note that
        this creates all children of *node* and not only the next level of the tree-structure as _loadTagLayer
        does. For performance reasons this method does not load the data (''Element.fromId(loadData=False)'').
        """
        ids = list(db.query("SELECT id FROM {0} WHERE toplevel = 1".format(table)).getSingleColumn())
        childIds = ids
        while len(childIds) > 0:
            childIds = list(itertools.chain.from_iterable(element.contents.ids
                                for element in levels.real.getFromIds(childIds) if element.isContainer()))       
        if node.contents is not None:
            # Only use beginRemoveRows and friends if there are already contents. If we are going to add the
            # first contents to node (this happens thanks to the directload shortcut), we must not call
            # those methods as Qt will then try to access the contents...resulting in _startLoading.
            contentsNone = True
            self.beginRemoveRows(self.getIndex(node),0,len(node.contents)-1)
            node.setContents([])
            self.endRemoveRows()
        else: contentsNone = False
        
        if contentsNone:
            self.beginInsertRows(self.getIndex(node),0,len(ids)-1)
        node.setContents([Wrapper(levels.real.get(id)) for id in ids])
        for child in node.getContents():
            child.loadContents(recursive=True)
        
        # Finally sort the contents
        sortTags = [tags.TITLE] # by default sort for titles
        if isinstance(node,ValueNode):
            # In the rare case that the ValueNode's value belongs to two tags (i.e. artist and composer)
            # with different sortTags, we simply choose the first
            tagToDetermineSortTags = tags.get(list(node.valueIds.keys())[0])
            if tagToDetermineSortTags in self.sortTags:
                sortTags = self.sortTags[tagToDetermineSortTags]
            
        for sortTag in reversed(sortTags):
            reverse = sortTag.type == tags.TYPE_DATE
            p = utils.PointAtInfinity(not reverse)
            node.contents.sort(
                # TODO: respect sortvalues for e.g. composers
                key = lambda wr: wr.element.tags[sortTag][0] if sortTag in wr.element.tags else p,
                reverse = reverse
            )
                
        if contentsNone:
            self.endInsertRows()

    def applyEvent(self, ids, contents):
        """Apply an event to all elements."""
        for node in self.getAllNodes():
            if isinstance(node, Wrapper) and node.element.id in ids:
                index = self.getIndex(node)
                self.dataChanged.emit(index,index)


class CriterionNode(Node):
    """CriterionNode is the base class for nodes used to group elements according to a criterion (confer 
    search.criteria) in a BrowserModel. The level below this node will contain all elements of this level
    that match the criterion."""
    def __init__(self,parent,model):
        """Initialize this CriterionNode with the parent-node <parent> and the given model and criterion."""
        self.parent = parent
        self.model = model
        self.layerIndex = parent.layerIndex + 1
        self.contents = None
    
    def _collectCriteria(self):
        """Return a list containing the criteria of this node and of all of its parent nodes (as long as they
        are of type CriterionNode)."""
        result = [self.getCriterion()]
        parent = self.parent
        while parent is not None:
            if isinstance(parent,CriterionNode): # Skip HiddenValuesNodes
                result.append(parent.getCriterion())
            parent = parent.parent
        return result
    
    def getCriterion(self):
        """Return the criterion of this node."""
        assert False # implemented in subclasses

    def hasContents(self):
        # Always return True. The contents of a CriterionNode are loaded when getContents or getContentsCount
        # is called for the first time. Prior to that call hasContents=True will tell the view that the node
        # is expandable and make the view draw a plus-sign in front of the node.
        return True
        
    def getContentsCount(self,recursive=False):
        if self.contents is None:
            self.loadContents()
        return super().getContentsCount(recursive)
        
    def getContents(self):
        if self.contents is None:
            self.loadContents()
        return self.contents
    
    def getAllNodes(self):
        if self.contents is None:
            return
        else: 
            for node in super().getAllNodes():
                yield node
            
    def hasLoaded(self):
        """Return whether this CriterionNode did already load its contents."""
        return self.contents is not None and (len(self.contents) != 1 
                                               or not isinstance(self.contents[0],LoadingNode))
                                               
    def loadContents(self,wait=False):
        """If they are not loaded yet, start to load the contents of this node. The actual loading is done
        by the model when it reacts to the searchFinished event. If *wait* is True, the contents are loaded
        directly, i.e. the method waits for the search to finish.
        """
        if self.contents is None:
            if not wait:
                self.contents = [LoadingNode(self)]
                self.model._startLoading(self)
                # The contents will be added in BrowserModel.searchFinished
            else:
                self.model._startLoading(self,wait=True) # block until the contents are loaded


class ValueNode(CriterionNode):
    """A ValueNode groups elements which have the same tag-value in one or more tags. Not that only the value
    must coincide, the tags need not be the same, but they must be in a given list. This enables BrowserViews
    display e.g. all artists and all composers in one tag-layer.
    """
    def __init__(self,parent,model,value,valueIds,sortValue):
        """Initialize this ValueNode with the parent-node *parent* and the given model. *valueIds* is a dict
        mapping tag-ids to value-ids of the tag. This node will contain elements having at least one of the
        value-ids in the corresponding tag. *value* is the value of the value-ids (which should be the same
        for all tags) and will be displayed on the node.
        """
        CriterionNode.__init__(self,parent,model)
        self.valueIds = valueIds
        self.values = [value]
        self.sortValues = [sortValue if sortValue is not None else value]
    
    def getCriterion(self):
        return search.criteria.TagIdCriterion(self.valueIds)

    def addValues(self,other):
        """Add the values (and sortValues) of *other* to this node. This won't affect the contents of this
        node, so be sure to call this node only when it makes sense.
        """
        self.values.extend(other.values)
        self.values.sort()
        self.sortValues.extend(other.sortValues)
        self.sortValues.sort()
        qtIndex = self.model.getIndex(self)
        self.model.dataChanged.emit(qtIndex,qtIndex)
        
    def __str__(self):
        return "<ValueNode {} ({})>".format(self.values, ", ".join(map(str,self.valueIds)))
    
    def toolTipText(self):
        if config.options.misc.show_ids: # Display the value-ids
            lines = ["[{}]".format(", ".join("{}->{}".format(tags.get(tagId).name,valueId)
                                    for tagId,valueId in self.valueIds.items()))]
            lines.extend(self.values)
        else: lines = self.values
        return '\n'.join(lines)

    def getKey(self):
        return (ValueNode,self.values[0])


class VariousNode(CriterionNode):
    """A VariousNode groups elements in a tag-layer which have no tag in any of the tags in the tag-layer's
    tagset."""
    def __init__(self,parent,model,tagSet):
        """Initialize this VariousNode with the parent-node <parent>, the given model and the tag-layer's
        tagset *tagSet*."""
        CriterionNode.__init__(self,parent,model)
        self.tagSet = tagSet

    def getCriterion(self):
        return search.criteria.MissingTagCriterion(self.tagSet)
    
    def __str__(self):
        return "<VariousNode>"
        
    def toolTipText(self):
        return None


class HiddenValuesNode(Node):
    """A node that contains hidden value nodes."""
    def __init__(self,parent,valueNodes):
        self.parent = parent
        self.setContents(valueNodes)
        
    def __str__(self):
        return "<HiddenValues>"
        
    def toolTipText(self):
        return None
        
        
class BrowserRootNode(RootNode):
    """Rootnode of the Browser-TreeModel."""
    def __init__(self,model):
        super().__init__(model)
        self.layerIndex = -1
        

class LoadingNode(Node):
    """This is a placeholder for those moments when we must wait for a search to terminate before we can
    display the real contents. The delegate will draw the string "Loading...".
    """
    def __init__(self,parent):
        self.parent = parent
    
    def hasContents(self):
        return False
    
    @property
    def contents(self):
        return list()
    
    def __str__(self):
        return "<LoadingNode>"
        
    def toolTipText(self):
        None
    

class BrowserMimeData(mimedata.MimeData):
    """This is the subclass of mimedata.MimeData that is used by the browser. The main differences are that
    the browser contains nodes that are no elements and that they may not have loaded their contents yet.   
    """  
    def __init__(self, nodeSelection):
        super().__init__(nodeSelection)
        self._wrappersLoaded = False

    def wrappers(self):
        if not self._wrappersLoaded:
            # self.nodes() may contain CriterionNodes or (unlikely) LoadingNodes.
            self._wrappers = list(itertools.chain.from_iterable(self._getElementsInstantly(node)
                                                                   for node in self.nodes()))
            self._wrappersLoaded = True
        return self._wrappers
                                          
    def _getElementsInstantly(self,node):
        """If *node* is a CriterionNode return all (toplevel) elements contained in it. If contents have to
        be loaded, wait for the search to finish. If *node* is an element return ''[node]''.
        """
        if isinstance(node, Wrapper):
            return [node]
        if isinstance(node,CriterionNode):
            node.loadContents(wait=True) # This does not load element data
            return itertools.chain.from_iterable(self._getElementsInstantly(child)
                                                    for child in node.getContents())
        else: return [] # Should be a LoadingNode

    @staticmethod
    def fromIndexes(model,indexList):
        """Generate a MimeData instance from the indexes in *indexList*. *model* must be the model containing
        these indexes.
        """
        nodes = [model.data(index,role=Qt.EditRole) for index in indexList]
        return BrowserMimeData(selection.NodeSelection(model.level,nodes))
