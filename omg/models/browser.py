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

from omg import config, models, search, database as db, tags, logging, utils
import omg
from omg.models import rootedtreemodel, mimedata

logger = logging.getLogger("omg.gui.browser")

searchEngine = None
smallResult = None

def initSearchEngine():
    global searchEngine, smallResult
    if searchEngine is None:
        searchEngine = search.SearchEngine()
        smallResult = searchEngine.createResultTable("browser_small")

class BrowserModel(rootedtreemodel.RootedTreeModel):
    showHiddenValues = False
    _ignoreSearchFinished = False
    time = None
    
    def __init__(self,table,layers,browser):
        """Initialize this model. It will contain only elements from <table>, group them according to <layers> and will use <smallResult> as temporary search table (BrowserModels perform internal searches when CriterionNodes are expanded for the first time."""
        rootedtreemodel.RootedTreeModel.__init__(self,RootNode(self))
        self.table = table
        self.browser = browser
        self.layers = layers
        self.time = []
        
        if searchEngine is None:
            initSearchEngine()
        
        searchEngine.searchFinished.connect(self._handleSearchFinished)
        searchEngine.searchStopped.connect(self._handleSearchStopped)
        
        self._startLoading(self.root)
        #distributor.indicesChanged.connect(self._handleIndicesChanged)
    
    def reset(self):
        """Reset the model."""
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
        return self.showHiddenValues
    
    def setShowHiddenValues(self,showHiddenValues):
        if showHiddenValues != showHiddenValues:
            self.showHiddenValues = showHiddenValues
            self.reset()
        
    def _startLoading(self,node):
        """Load the contents of <node>, which must be either root or a CriterionNode (The contents of Elements are loaded via Element.loadContents)."""
        assert node == self.root or isinstance(node,CriterionNode)
        
        if node == self.root:
            # No need to search...load directly
            if len(self.layers) > 0:
                self._loadTagLayer(node,self.table)
            else: self._loadContainerLayer(node,self.table)
        else:
            # Collect the criteria in this node and its parents and put the search results into smallResult
            searchEngine.search(self.table,smallResult,node._collectCriteria(),owner=node,parent=self.browser,data=self,lockTable=True)
    
    def _handleSearchStopped(self,stopRequest):
        if stopRequest.owner is self.browser:
            self._ignoreSearchFinished = False
            
    def _handleSearchFinished(self,searchRequest):
        if not self._ignoreSearchFinished and searchRequest.data is self and searchRequest.owner is not None:
            # Determine whether to load a tag-layer or the container-layer at the bottom of the tree.
            node = searchRequest.owner
            if node.layerIndex+1 < len(self.layers):
                self._loadTagLayer(node,smallResult)
            else: self._loadContainerLayer(node,smallResult)
            searchEngine.releaseTable(smallResult)
    
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
                    if aNode.value == value:
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
        
        if node.hasContents():
            self.beginRemoveRows(self.getIndex(node),0,node.getContentsCount()-1)
            node.setContents([])
            self.endRemoveRows()
        
        if len(valueNodes) > 0:
            self.beginInsertRows(self.getIndex(node),0,len(valueNodes)-1)
            node.setContents(valueNodes)
            self.endInsertRows()
            
        # Tag-layers containing only one CriterionNode are not helpful, so if this happens load the contents
        # of the only CriterionNode and put them into node, removing the original CriterionNode.
#        if len(valueNodes) == 1:
#            self._startLoading(valueNodes[0])
#            for n in valueNodes[0].contents:
#                n.parent = node
#            node.contents = valueNodes[0].contents

    def _loadContainerLayer(self,node,table):
        """Load the contents of <node> into a container-layer, using elements from <table>. Note that this
        creates all children of <node> not only the next level of the tree-structure as _loadTagLayer does."""
        result = db.query("SELECT id,file FROM {0} WHERE toplevel = 1".format(table))
        if node.hasContents():
            self.beginRemoveRows(self.getIndex(node),0,node.getContentsCount()-1)
            node.setContents([])
            self.endRemoveRows()
        
        self.beginInsertRows(self.getIndex(node),0,len(result)-1)
        node.setContents([(models.File if file else models.Container).fromId(id) for id,file in result])
        for element in node.contents:
            element.parent = node
            if element.isContainer():
                # For performance reasons data of contents are not loaded until the delegate wants it.
                element.loadContents(recursive=True,loadData=False)
        
        # Finally sort the contents
        sortTag = node.getSortTag()
        reverse = sortTag.type == tags.TYPE_DATE
        p = utils.PointAtInfinity(not reverse)
        node.contents.sort(
            key = lambda el: el.tags[sortTag][0] if sortTag in el.tags else p,
            reverse = reverse
        )
        self.endInsertRows()



class HiddenValuesNode(models.Node):
    def __init__(self,parent,valueNodes):
        self.parent = parent
        self.setContents(valueNodes)
        
    def __str__(self):
        return "<HiddenValues>"
        
    def toolTipText(self):
        return None


class CriterionNode(models.Node):
    """CriterionNode is the base class for nodes used to group elements according to a criterion (confer search.criteria) in a BrowserModel."""
    def __init__(self,parent,model):
        """Initialize this CriterionNode with the parent-node <parent> and the given model and criterion."""
        self.parent = parent
        self.model = model
        self.layerIndex = parent.layerIndex + 1
        self.contents = None
    
    def _collectCriteria(self):
        """Return a list containing the criteria of this node and of all of its parent nodes (as long as they are of type CriterionNode)."""
        result = [self.getCriterion()]
        parent = self.getParent()
        while parent is not None:
            if isinstance(parent,CriterionNode):
                result.append(parent.getCriterion())
            parent = parent.getParent()
        return result
    
    def getCriterion(self):
        """Return the criterion of this node."""
        assert False # implemented in subclasses
    
    def hasContents(self):
        # Always return True. The contents of a CriterionNode are loaded when getChildren or getChildrenCount is called for the first time. Prior to this call hasChildren=True will tell the view that the node is expandable and make the view draw a plus-sign in front of the node.
        return True
        
    def getContentsCount(self,recursive=False):
        if self.contents is None:
            self.model._startLoading(self)
            self.contents = [LoadingNode(self)]
            return 1 # "Loading..."
        return super().getContentsCount(recursive)
        
    def getContents(self):
        if self.contents is None:
            self.contents = [LoadingNode(self)]
            self.model._startLoading(self)
        return self.contents


class ValueNode(CriterionNode):
    """A ValueNode groups elements which have the same tag-value in one or more tags. Not that only the value must coincide, the tags need not be the same, but they must be in a given list. This enables BrowserViews display e.g. all artists and all composers in one tag-layer."""
    def __init__(self,parent,model,value,valueIds,sortValue):
        """Initialize this ValueNode with the parent-node <parent> and the given model. <valueIds> is a dict mapping tags to value-ids of the tag. This node will contain elements having at least one of the value-ids in the corresponding tag. <value> is the value of the value-ids (which should be the same for all tags) and will be displayed on the node."""
        CriterionNode.__init__(self,parent,model)
        self.value = value
        self.valueIds = valueIds
        self.sortValue = sortValue
    
    def getDisplayValue(self):
        if config.options.gui.browser_show_sort_values:
            return self.sortValue if self.sortValue is not None else self.value
        else: return self.value

    def getCriterion(self):
        return search.criteria.TagIdCriterion(self.valueIds)
    
    def getSortTag(self):
        sortTags = [tags.get(tagId) for tagId in db.query("SELECT sortKey FROM {}tagids WHERE id IN ({})"
                               .format(db.prefix,",".join(str(key) for key in self.valueIds))).getSingleColumn()]
        # If sortTags contains more than one tag, prefer title
        if tags.TITLE in sortTags:
            return tags.TITLE
        else: return sortTags[0]

    def __str__(self):
        return "<ValueNode '{0}' ({1})>".format(self.value, ", ".join(map(str,self.valueIds)))
    
    def toolTipText(self):
        if config.options.misc.show_ids: # Display the value-ids
            idString = ", ".join("{} {}".format(tags.get(tagId).name,valueId) for tagId,valueId in self.valueIds.items())
            return "{} [{}]".format(self.value,idString)
        else: return self.value


class VariousNode(CriterionNode):
    """A VariousNode groups elements in a tag-layer which have no tag in any of the tags in the tag-layer's tagset."""
    def __init__(self,parent,model,tagSet):
        """Initialize this VariousNode with the parent-node <parent>, the given model and the tag-layer's tagset <tagSet>."""
        CriterionNode.__init__(self,parent,model)
        self.tagSet = tagSet

    def getCriterion(self):
        return search.criteria.MissingTagCriterion(self.tagSet)
    
    def getSortTag(self):
        sortTags = [tags.get(tagId) for tagId in db.query("SELECT sortKey FROM {}tagids WHERE id IN ({})"
                          .format(db.prefix,",".join(str(tag.id) for tag in self.tagSet))).getSingleColumn()]
        # If sortTags contains more than one tag, prefer title
        if tags.TITLE in sortTags:
            return tags.TITLE
        else: return sortTags[0]
        
    def __str__(self):
        return "<VariousNode>"
        
    def toolTipText(self):
        return None


class RootNode(models.RootNode):
    """Rootnode of the Browser-TreeModel."""
    def __init__(self,model):
        """Initialize this Rootnode with the given model."""
        models.RootNode.__init__(self)
        self.model = model
        self.layerIndex = -1
        

class LoadingNode(models.Node):
    def __init__(self,parent):
        self.parent = parent
    
    def hasContents(self):
        return False
        
    def __str__(self):
        return "<LoadingNode>"
        
    def toolTipText(self):
        None
