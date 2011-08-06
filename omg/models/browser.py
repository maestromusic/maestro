#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import itertools

from PyQt4 import QtCore
from PyQt4.QtCore import Qt

from .. import config, models, search, database as db, tags, logging, utils
from ..models import rootedtreemodel, mimedata, Element

logger = logging.getLogger(__name__)

searchEngine = None # The search engine used by all browsers

# This result table is used when a CriterionNode is expanded. It is common to all browsers, in contrast to the
# bigResult-table of a browser in which it will store the results of user searches.
smallResult = None


def initSearchEngine():
    """Initialize the single search engine used by all browsers."""
    global searchEngine, smallResult
    if searchEngine is None:
        searchEngine = search.SearchEngine()
        smallResult = searchEngine.createResultTable("browser_small")


class BrowserModel(rootedtreemodel.RootedTreeModel):
    """ItemModel for the BrowserTreeViews (Thus a browser may have several models)."""
    showHiddenValues = False
    
    _autoLoadEnabled = False # While enabled AutoLoading loads the contents of all nodes.
    _autoLoadGen = None # Generator that produces elements that have to be loaded.
    
    def __init__(self,table,layers,browser,view):
        """Initialize this model. It will contain only elements from *table* and group them according to
        *layers*. *browser* and *view* must be the browser and its view that uses this model.
        """
        rootedtreemodel.RootedTreeModel.__init__(self,RootNode(self))
        self.table = table
        self.browser = browser
        self.view = view
        self.layers = layers
        
        if searchEngine is None:
            initSearchEngine()
        
        searchEngine.searchFinished.connect(self._handleSearchFinished)
        #distributor.indicesChanged.connect(self._handleIndicesChanged)
        
        if self._autoLoadEnabled:
            # Start new autoLoading
            self._autoLoadGen = self.breadthFirstTraversal()
        self._startLoading(self.root)
    
    def reset(self):
        """Reset the model."""
        if self._autoLoadEnabled:
            # Start new autoLoading
            self._autoLoadGen = self.breadthFirstTraversal()
        self._startLoading(self.root)
        rootedtreemodel.RootedTreeModel.reset(self)

    def setLayer(self,layers):
        """Set the layers of the model and reset."""
        if layers != self.layers:
            self.layers = layers
            self.reset()
    
    def getLayers(self):
        """Return the layers of this model."""
        return self.layers
    
    def setTable(self,table):
        """Set the table of this model. The model will only contain elements from <table>."""
        if table != self.table:
            self.table = table
            self.reset()
        
    def getTable(self):
        """Return the table in which this model's contents are contained."""
        return self.table
    
    def getShowHiddenValues(self):
        """Return whether the browser-view with this model should display ValueNodes where the hidden-flag in
        values_varchar is set."""
        return self.showHiddenValues
    
    def setShowHiddenValues(self,showHiddenValues):
        """Show or hide ValueNodes where the hidden-flag in values_varchar is set."""
        if showHiddenValues != showHiddenValues:
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

    def isAutoLoadEnabled(self):
        """Return whether AutoLoad is enabled."""
        return self.autoLoadEnabled

    def setAutoLoad(self,autoLoad):
        """Enable or disable AutoLoad. While enabled the BrowserModel will load the contents of all nodes, one
        by one.
        """
        if autoLoad and not self._autoLoadEnabled:
            self._autoLoadEnabled = True
            self._autoLoadGen = self.breadthFirstTraversal()
            self._autoLoad()
        elif not autoLoad and self._autoLoadEnabled:
            self._autoLoadEnabled = False
            self._autoLoadGen = None

    def _autoLoad(self):
        """If AutoLoad is enabled, load the contents of the next node produced by self._autoLoadGen. To be
        precise: Only start loading them and delay the actual loading to the searchFinished-event.
        """
        if not self._autoLoadEnabled or self._autoLoadGen is None:
            # The latter means that all nodes have been loaded already.
            return
        try:
            while True:
                node = next(self._autoLoadGen)
                if isinstance(node,CriterionNode) and not node.hasLoaded():
                    #print("AutoLoading node {} {}".format(id(node),node))
                    node.loadContents()
                    # Wait for the contents to be loaded, _autoLoad will be called again in _searchFinished.
                    break 
        except StopIteration:
            self._autoLoadGen = None

    def _startLoading(self,node,wait=False):
        """Start loading the contents of *node*, which must be either root or a CriterionNode (The contents of
        containers are loaded via Container.loadContents). For CriterionNodes start a search for the contents.
        The actual loading will be done in the searchFinished event. Only the rootnode is loaded directly. If
        *wait* is True this method will wait until the node is loaded. 
        """
        assert node == self.root or isinstance(node,CriterionNode)
        
        if node == self.root:
            # No need to search...load directly
            if len(self.layers) > 0:
                self._loadTagLayer(node,self.table)
                if self._autoLoadEnabled:
                    self._autoLoad()
            else: self._loadContainerLayer(node,self.table)
        else:
            method = searchEngine.search if not wait else searchEngine.searchAndWait
            # Collect the criteria in this node and its parents and put the search results into smallResult
            searchRequest = method(self.table,smallResult,node._collectCriteria(),
                                parent=self.browser.searchRequest,
                                owner=self,
                                data=node,
                                lockTable=True)
            if wait:
                # Search is finished.
                self._handleSearchFinished(searchRequest,noAutoLoad=True)
            # else: Wait for searchFinished...somewhat paradoxical :-)
            
    def _handleSearchFinished(self,searchRequest,noAutoLoad=False):
        """Handle the searchFinished-event for *searchRequest*: Load the contents of the node
        ''searchRequest.data''. If AutoLoading is enabled, call self.view.autoExpand to check whether it 
        should be disabled. If that is not the case, call self._autoLoad to keep AutoLoad running. If the 
        parameter *noAutoLoad* is True this behaviour is deactivated. AutoLoad is not disabled, though.
        """
        if searchRequest.owner is self and not searchRequest.isStopped():
            # Determine whether to load a tag-layer or the container-layer at the bottom of the tree.
            node = searchRequest.data
            if node.layerIndex+1 < len(self.layers):
                self._loadTagLayer(node,smallResult)
            else: self._loadContainerLayer(node,smallResult)
            searchRequest.releaseTable()
            if self._autoLoadEnabled and not noAutoLoad:
                self.view.autoExpand()
                # When AutoExpand fails, the view will disable AutoLoad. 
            if self._autoLoadEnabled and not noAutoLoad:
                self._autoLoad() # Continue auto loading
    
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
        result = db.query("SELECT id,file FROM {0} WHERE toplevel = 1".format(table))
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
            self.beginInsertRows(self.getIndex(node),0,len(result)-1)
        node.setContents([(models.File if file else models.Container).fromId(id) for id,file in result])
        for element in node.contents:
            element.parent = node
            if element.isContainer():
                # For performance reasons data of contents are not loaded until the delegate wants it.
                element.loadContents(recursive=True,table=self.table,loadData=False)
        
        # Finally sort the contents
        for sortTag in reversed(node.getSortTags()):
            reverse = sortTag.type == tags.TYPE_DATE
            p = utils.PointAtInfinity(not reverse)
            node.contents.sort(
                key = lambda el: el.tags[sortTag][0] if sortTag in el.tags else p,
                reverse = reverse
            )
        if contentsNone:
            self.endInsertRows()


class CriterionNode(models.Node):
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
        parent = self.getParent()
        while parent is not None:
            if isinstance(parent,CriterionNode): # Skip HiddenValuesNodes
                result.append(parent.getCriterion())
            parent = parent.getParent()
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
        """Initialize this ValueNode with the parent-node <parent> and the given model. <valueIds> is a dict
        mapping tags to value-ids of the tag. This node will contain elements having at least one of the
        value-ids in the corresponding tag. <value> is the value of the value-ids (which should be the same
        for all tags) and will be displayed on the node.
        """
        CriterionNode.__init__(self,parent,model)
        self.valueIds = valueIds
        self.values = [value]
        if config.options.gui.browser_show_sort_values:
            self.sortValues = [sortValue if sortValue is not None else value]
    
    def getDisplayValues(self):
        """Return the values that should be displayed for this node."""
        if config.options.gui.browser_show_sort_values:
            return self.values
        else: return self.sortValues

    def getCriterion(self):
        return search.criteria.TagIdCriterion(self.valueIds)
    
    def getSortTags(self):
        """Return the tags that should be used to sort the nodes below this one."""
        # TODO: Do something if there are several tags with different sorttags
        return tags.get(list(self.valueIds.keys())[0]).sortTags

    def addValues(self,other):
        """Add the values (and sortValues) of *other* to this node. This won't affect the contents of this
        node, so be sure to call this node only when it makes sense.
        """
        self.values.extend(other.values)
        self.values.sort()
        if config.options.gui.browser_show_sort_values:
            self.sortValues.extend(other.sortValues)
            self.sortValues.sort()
        qtIndex = self.model.getIndex(self)
        self.model.dataChanged.emit(qtIndex,qtIndex)
        
    def __str__(self):
        return "<ValueNode '{0}' ({1})>".format(self.value, ", ".join(map(str,self.valueIds)))
    
    def toolTipText(self):
        if config.options.misc.show_ids: # Display the value-ids
            lines = ["[{}]".format(", ".join("{}->{}".format(tags.get(tagId).name,valueId)
                                    for tagId,valueId in self.valueIds.items()))]
            lines.extend(self.getDisplayValues())
        else: lines = self.getDisplayValues()
        return '\n'.join(lines)


class VariousNode(CriterionNode):
    """A VariousNode groups elements in a tag-layer which have no tag in any of the tags in the tag-layer's
    tagset."""
    def __init__(self,parent,model,tagSet):
        """Initialize this VariousNode with the parent-node <parent>, the given model and the tag-layer's
        tagset <tagSet>."""
        CriterionNode.__init__(self,parent,model)
        self.tagSet = tagSet

    def getCriterion(self):
        return search.criteria.MissingTagCriterion(self.tagSet)
    
    def getSortTags(self):
        """Return the tags that should be used to sort the nodes below this one."""
        # TODO: Do something if there are several tags with different sorttags
        return tags.get(list(self.tagSet)[0]).sortTags
        
    def __str__(self):
        return "<VariousNode>"
        
    def toolTipText(self):
        return None


class HiddenValuesNode(models.Node):
    """A node that contains hidden value nodes."""
    def __init__(self,parent,valueNodes):
        self.parent = parent
        self.setContents(valueNodes)
        
    def __str__(self):
        return "<HiddenValues>"
        
    def toolTipText(self):
        return None
        
        
class RootNode(models.RootNode):
    """Rootnode of the Browser-TreeModel."""
    def __init__(self,model):
        models.RootNode.__init__(self)
        self.model = model
        self.layerIndex = -1
        

class LoadingNode(models.Node):
    """This is a placeholder for those moments when we must wait for a search to terminate before we can
    display the real contents. The delegate will draw the string "Loading...".
    """
    def __init__(self,parent):
        self.parent = parent
    
    def hasContents(self):
        return False
        
    def __str__(self):
        return "<LoadingNode>"
        
    def toolTipText(self):
        None
    
    
class BrowserMimeData(mimedata.MimeData):
    """This is the subclass of mimedata.MimeData that is used by the browser. The main differences are that
    the browser contains nodes that are no elements and that they may not have loaded their contents yet.   
    """  
    def __init__(self,nodeList):
        mimedata.MimeData.__init__(self,None) # The element list will be computed when it is needed.
        self.nodeList = nodeList

    def getElements(self):
        if self.elementList is not None:
            return self.elementList
        # self.elementList may contain CriterionNodes or (unlikely) LoadingNodes.
        self.elementList = itertools.chain.from_iterable(self._getElementsInstantly(node)
                                                            for node in self.nodeList)
        self.nodeList = None # Save memory
        return self.elementList
                                          
    def _getElementsInstantly(self,node):
        """If *node* is a CriterionNode return all (toplevel) elements contained in it. If contents have to
        be loaded, wait for the search to finish. If *node* is an element return ''[node]''.
        """
        if isinstance(node,Element):
            return [node]
        if isinstance(node,CriterionNode):
            node.loadContents(wait=True)
            return itertools.chain.from_iterable(self._getElementsInstantly(child)
                                                    for child in node.getContents())
        else: return [] # Should be a LoadingNode
    
    def paths(self):
        """Return a list of absolute paths to all files contained in this MimeData-instance."""
        # The browser doesn't load the paths.
        return [utils.absPath(db.path(file.id)) for file in self.getFiles()]

    @staticmethod
    def fromIndexes(model,indexList):
        """Generate a MimeData instance from the indexes in *indexList*. *model* must be the model containing
        these indexes. This method will remove an index when an ancestor is contained in *indexList*, too.
        """
        nodes = [model.data(index,role=Qt.EditRole) for index in indexList]
        # Filter away nodes if a parent as also contained in the indexList. 
        nodes = [n for n in nodes if not any(parent in nodes for parent in n.getParents())]
        return BrowserMimeData(nodes)
    