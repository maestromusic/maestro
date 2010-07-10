#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from omg import models, search, database
from omg.models import rootedtreemodel

# Temporary tables used for search results (have to appear before the imports as they will be imported in some imports)
TT_BIG_RESULT = 'tmp_browser_bigres'
TT_SMALL_RESULT = 'tmp_browser_smallres'

class BrowserModel(rootedtreemodel.RootedTreeModel):
    def __init__(self,table,layers):
        rootedtreemodel.RootedTreeModel.__init__(self,RootNode(self))
        self.table = table
        self.layers = layers
        search.createResultTempTable(TT_BIG_RESULT,True)
        search.createResultTempTable(TT_SMALL_RESULT,True)
        self._loadLayer(self.root)
            
    def setLayer(self,layers):
        self.layers = layers
        self.reset()
    
    def getLayers(self):
        return self.layers
    
    def setTable(self,table):
        self.table = table
        self.reset()
        
    def getTable(self):
        return self.table
        
    def reset(self):
        self._loadLayer(self.root)
        rootedtreemodel.RootedTreeModel.reset(self)
            
    def getNextTagSet(self,node):
        level = node.getLevel()
        if level < len(self.layers):
            # No need to add/substract 1: list starts at 0, level (without root node) at 1 and we want the next level.
            return self.layers[level]
        else: return None # Next layer is a container layer
        
    def _loadLayer(self,node):
        assert node == self.root or isinstance(node,CriterionNode)
        
        if node == self.root:
            table = self.table
        else:
            search.stdSearch(node._collectCriteria(),TT_SMALL_RESULT,self.table)
            table = TT_SMALL_RESULT
        
        if self.getNextTagSet(node) is not None:
            self._loadTagLayer(node,table)
            #TODO: Add code to load automatically
            #~ if (recursive or 
                #~ db.query("SELECT COUNT(*) FROM {0}".format(TT_SMALL_RESULT)).getSingle()
                     #~ < self._getNextLayer().DIRECT_LOAD_LIMIT):
                #~ for element in self.elements:
                    #~ element.update(recursive)
        else: self._loadContainerLayer(node,table)


    def _loadTagLayer(self,node,table):
        valueNodes = []
        values = []
        for tag in self.getNextTagSet(node):
            # Get all values and corresponding ids of the given tag appearing in at least one toplevel result.
            result = database.get().query("""
                SELECT DISTINCT tag_{0}.id,tag_{0}.value
                FROM {1} JOIN tags ON {1}.id = tags.container_id AND tags.tag_id = {2}
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
                FROM {0} LEFT JOIN tags ON {0}.id = tags.container_id AND tags.tag_id IN ({1})
                WHERE tags.value_id IS NULL
                LIMIT 1
                """.format(table,",".join(str(tag.id) for tag in self.getNextTagSet(node))))
        if result.size():
            valueNodes.append(VariousNode(node,self,self.getNextTagSet(node)))
            
        node.contents = valueNodes
    
    def _loadContainerLayer(self,node,table):
        result = database.get().query("SELECT id FROM {0} WHERE toplevel = 1".format(table)).getSingleColumn()
        node.contents = [models.Element(id) for id in result]
        for element in node.contents:
            element.parent = node
            element.loadContents(True,table)
            element.loadTags(True)

class CriterionNode(models.Node):
    
    def __init__(self,parent,model,criterion):
        self.parent = parent
        self.model = model
        self.criterion = criterion
        self.contents = None
    
    def _collectCriteria(self,type=None):
        result = [self.getCriterion()]
        parent = self.getParent()
        while parent is not None:
            if type is None or isinstance(parent,type):
                try:
                    if parent.getCriterion() is not None:
                        result.append(parent.getCriterion())
                # Current parent node seems to have no getCriterion-method...so just skip it
                except AttributeError: pass
            parent = parent.getParent()
        return result
    
    def getCriterion(self):
        return self.criterion
    
    def hasChildren(self):
        return True
        
    def getChildrenCount(self):
        if self.contents is None:
            self.model._loadLayer(self)
        return len(self.contents)
        
    def getChildren(self):
        if self.contents is None:
            self.model._loadLayer(self)
        return self.contents
    
    def getModel(self):
        return self.model


class ValueNode(CriterionNode):
    def __init__(self,parent,model,value,valueIds):
        CriterionNode.__init__(self,parent,model,None)
        self.value = value
        self.valueIds = valueIds
    
    def __str__(self):
        return "<ValueNode '{0}'>".format(self.value)
    
    def getCriterion(self):
        return search.criteria.TagIdCriterion(self.valueIds)


class VariousNode(CriterionNode):
    def __init__(self,parent,model,tagSet):
        CriterionNode.__init__(self,parent,model,search.criteria.MissingTagCriterion(tagSet))
        
    def __str__(self):
        return "<VariousNode>"


class RootNode(models.Node):
    """Rootnode of the Browser-TreeModel."""
    def __init__(self,model):
        self.contents = []
        self.model = model
    
    def getParent(self):
        return None