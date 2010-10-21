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

from omg import config, models, search, database, tags
import omg
from omg.models import rootedtreemodel, mimedata

class BrowserModel(rootedtreemodel.RootedTreeModel):
    """Model for a BrowserTreeView."""
    def __init__(self,table,layers,smallResult):
        """Initialize this model. It will contain only elements from <table>, group them according to <layers> and will use <smallResult> as temporary search table (BrowserModels perform internal searches when CriterionNodes are expanded for the first time."""
        rootedtreemodel.RootedTreeModel.__init__(self,RootNode(self))
        self.table = table
        self.layers = layers
        self.smallResult = smallResult
        self._loadLayer(self.root)
    
    def setLayer(self,layers):
        """Set the layers of the model and reset."""
        self.layers = layers
        self.reset()
    
    def getLayers(self):
        """Return the layers of this model."""
        return self.layers
    
    def setTable(self,table):
        """Set the table of this model. The model will only contain elements from <table>."""
        self.table = table
        self.reset()
        
    def getTable(self):
        """Return the table in which this model's contents are contained."""
        return self.table
        
    def reset(self):
        """Reset the model."""
        self._loadLayer(self.root)
        rootedtreemodel.RootedTreeModel.reset(self)
    
    def flags(self,index):
        defaultFlags = rootedtreemodel.RootedTreeModel.flags(self,index)
        if index.isValid():
            return defaultFlags | Qt.ItemIsDragEnabled
        else: return defaultFlags
    
    def mimeTypes(self):
        return [config.get("gui","mime")]
    
    def mimeData(self,indexes):
        return mimedata.createFromIndexes(self,indexes)
        
    def _loadLayer(self,node):
        """Load the contents of <node>, which must be either root or a CriterionNode (The contents of Elements are loaded via Element.loadContents)."""
        assert node == self.root or isinstance(node,CriterionNode)
        
        if node == self.root:
            table = self.table
        else:
            # Collect the criteria in this node and its parents and put the search results into smallResult
            search.stdSearch(node._collectCriteria(),self.smallResult,self.table)
            table = self.smallResult
        
        # Determine whether to load a tag-layer or the container-layer at the bottom of the tree.
        if node.layerIndex+1 < len(self.layers):
            self._loadTagLayer(node,table)
            #TODO: Add code to load automatically
            #~ if (recursive or 
                #~ db.query("SELECT COUNT(*) FROM {0}".format(SMALL_RESULT)).getSingle()
                     #~ < self._getNextLayer().DIRECT_LOAD_LIMIT):
                #~ for element in self.elements:
                    #~ element.update(recursive)
        else: self._loadContainerLayer(node,table)


    def _loadTagLayer(self,node,table):
        """Load the contents of <node> into a tag-layer, using elements from <table>."""
        tagSet = self.layers[node.layerIndex+1]
        valueNodes = []
        values = []
        for tag in tagSet:
            # Get all values and corresponding ids of the given tag appearing in at least one toplevel result.
            result = database.get().query("""
                SELECT DISTINCT tag_{0}.id,tag_{0}.value
                FROM {1} JOIN tags ON {1}.id = tags.element_id AND tags.tag_id = {2}
                         JOIN tag_{0} ON tags.value_id = tag_{0}.id
                WHERE {1}.toplevel = 1
                """.format(tag.name,table,tag.id))
            for row in result:
                try:
                    # If there is already a value node with value row[1], add this tag to that node
                    valueNodes[values.index(row[1])].valueIds[tag] = row[0]
                except ValueError: # there is no value node of this value...so add one
                    valueNodes.append(ValueNode(node,self,row[1],{tag:row[0]}))
                    values.append(row[1])
                    
        valueNodes.sort(key=lambda node: str.lower(node.value))
            
        # Check whether a VariousNode is necessary
        result = database.get().query("""
                SELECT {0}.id
                FROM {0} LEFT JOIN tags ON {0}.id = tags.element_id AND tags.tag_id IN ({1})
                WHERE tags.value_id IS NULL
                LIMIT 1
                """.format(table,",".join(str(tag.id) for tag in tagSet)))
        if result.size():
            valueNodes.append(VariousNode(node,self,tagSet))
            
        node.contents = valueNodes
        
        # Tag-layers containing only one CriterionNode are not helpful, so if this happens load the contents of the only CriterionNode and put them into node, removing the onlay CriterionNode.
        if len(valueNodes) == 1:
            self._loadLayer(valueNodes[0])
            for n in valueNodes[0].contents:
                n.parent = node
            node.contents = valueNodes[0].contents
    
    def _loadContainerLayer(self,node,table):
        """Load the contents of <node> into a container-layer, using elements from <table>. Note that this creates all children of <node> not only the next level of the tree-structure as _loadTagLayer does."""
        result = database.get().query("SELECT id,file FROM {0} WHERE toplevel = 1".format(table))
        node.contents = [models.createElement(id,file=file) for id,file in result]
        for element in node.contents:
            element.parent = node
            if element.isContainer():
                element.loadContents(True,table)
            element.loadTags(True)
        node.contents.sort(key = lambda elem: elem.tags[tags.DATE][0] if tags.DATE in elem.tags else omg.FlexiDate(900))


class CriterionNode(models.Node):
    """CriterionNode is the base class for nodes used to group elements according to a criterion (confer search.criteria) in a BrowserModel."""
    def __init__(self,parent,model,criterion):
        """Initialize this CriterionNode with the parent-node <parent> and the given model and criterion."""
        self.parent = parent
        self.model = model
        self.criterion = criterion
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
        return self.criterion
    
    def hasChildren(self):
        # Always return True. The contents of a CriterionNode are loaded when getChildren or getChildrenCount is called for the first time. Prior to this call hasChildren=True will tell the view that the node is expandable and make the view draw a plus-sign in front of the node.
        return True
        
    def getChildrenCount(self):
        if self.contents is None:
            self.model._loadLayer(self)
        return len(self.contents)
        
    def getChildren(self):
        if self.contents is None:
            self.model._loadLayer(self)
        return self.contents

    def getElements(self):
        """Return all elements (container and files) contained in this CriterionNode."""
        if self.contents is None:
            self.model._loadLayer(self)
        # Add either the node or invoke getElements recursively
        return itertools.chain(*[[node] if isinstance(node,models.Element)
                                 else node.getElements() for node in self.contents])


class ValueNode(CriterionNode):
    """A ValueNode groups elements which have the same tag-value in one or more tags. Not that only the value must coincide, the tags need not be the same, but they must be in a given list. This enables BrowserViews display e.g. all artists and all composers in one tag-layer."""
    def __init__(self,parent,model,value,valueIds):
        """Initialize this ValueNode with the parent-node <parent> and the given model. <valueIds> is a dict mapping tags to value-ids of the tag. This node will contain elements having at least one of the value-ids in the corresponding tag. <value> is the value of the value-ids (which should be the same for all tags) and will be displayed on the node."""
        CriterionNode.__init__(self,parent,model,None)
        self.value = value
        self.valueIds = valueIds
    
    def __str__(self):
        return "<ValueNode '{0}' ({1})>".format(self.value, ", ".join(map(str,self.valueIds)))
    
    def getCriterion(self):
        return search.criteria.TagIdCriterion(self.valueIds)


class VariousNode(CriterionNode):
    """A VariousNode groups elements in a tag-layer which have no tag in any of the tags in the tag-layer's tagset."""
    def __init__(self,parent,model,tagSet):
        """Initialize this VariousNode with the parent-node <parent>, the given model and the tag-layer's tagset <tagSet>."""
        CriterionNode.__init__(self,parent,model,search.criteria.MissingTagCriterion(tagSet))
        
    def __str__(self):
        return "<VariousNode>"


class RootNode(models.RootNode):
    """Rootnode of the Browser-TreeModel."""
    def __init__(self,model):
        """Initialize this Rootnode with the given model."""
        models.RootNode.__init__(self)
        self.model = model
        self.layerIndex = -1
