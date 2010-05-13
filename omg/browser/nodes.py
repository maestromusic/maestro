#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtCore
from omg import search, database, tags, models
from . import TT_BIG_RESULT, TT_SMALL_RESULT, layers
from PyQt4.QtCore import SIGNAL

db = database.get()

class Node:
    index = None
    
    # Methods for ForestModel
    def hasChildren(self): pass
    def getElementsCount(self): pass
    def getElements(self): pass

    def getParent(self):
        return self.parent
    
    def getIndex(self):
        model = self.getModel()
        if self.getParent() is None:
            containingList = model.getRoots()
            return model.index(containingList.index(self),0,QtCore.QModelIndex())
        else:
            containingList = self.getParent().getElements()
            return model.index(containingList.index(self),0,self.getParent().getIndex())

    def getTitle(self):
        """Return a title of this element which is created from the title-tags. If this element does not contain a title-tag some dummy-title is returned."""
        if tags.TITLE in self.tags:
            return " - ".join(self.tags[tags.TITLE])
        else: return '<Kein Titel>'


class CriterionNode(Node):
    def __init__(self,parent,layer,criterion):
        self.parent = parent
        self.layer = layer
        self.criterion = criterion
        self.elements = None
    
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
        
    def getElementsCount(self):
        if self.elements is None:
            self.update()
        return len(self.elements)
        
    def getElements(self):
        if self.elements is None:
            self.update()
        return self.elements
    
    def getModel(self):
        return self.parent.getModel()
    
    def retrieveElementList(self):
        if self.elements is None:
            self.update(True)
        result = []
        for element in self.elements:
            result.extend(element.retrieveElementList())
        return result

    def _getTable(self):
        return self.parent._getTable()
        
    def _getNextLayer(self):
        return self.layer.nextLayer
        
    def update(self,recursive=False):
        search.stdSearch(self._collectCriteria(),TT_SMALL_RESULT,self._getTable())
        model = self.getModel()
        if isinstance(self._getNextLayer(),layers.TagLayer):
            self._loadTagLayer(TT_SMALL_RESULT)
            if (recursive or 
                db.query("SELECT COUNT(*) FROM {0}".format(TT_SMALL_RESULT)).getSingle()
                     < self._getNextLayer().DIRECT_LOAD_LIMIT):
                for element in self.elements:
                    element.update(recursive)
        else: self._loadContainerLayer(TT_SMALL_RESULT)
        
    
    def _loadTagLayer(self,fromTable):
        valueNodes = []
        values = []
        for tag in self._getNextLayer().tagSet:
            # Get all values and corresponding ids of the given tag appearing in at least one toplevel result.
            result = database.get().query("""
                SELECT DISTINCT tag_{0}.id,tag_{0}.value
                FROM {1} JOIN tags ON {1}.id = tags.container_id AND tags.tag_id = {2}
                         JOIN tag_{0} ON tags.value_id = tag_{0}.id
                WHERE {1}.toplevel = 1
                """.format(tag.name,fromTable,tag.id))
            for row in result:
                try:
                    # If there is already a value node with value row[1], add this tag to that node
                    valueNodes[values.index(row[1])].valueIds[tag] = row[0]
                except ValueError: # there is no value node of this value...so add one
                    valueNodes.append(ValueNode(self,self._getNextLayer(),row[1],{tag:row[0]}))
                    values.append(row[1])
        valueNodes.sort(key=lambda node: str.lower(node.value))
        self.elements = valueNodes
            
        # Check whether a VariousNode is necessary
        result = db.query("""
                SELECT {0}.id
                FROM {0} LEFT JOIN tags ON {0}.id = tags.container_id AND tags.tag_id IN ({1})
                WHERE tags.value_id IS NULL
                LIMIT 1
                """.format(fromTable,",".join(str(tag.id) for tag in self._getNextLayer().tagSet)))
        if result.size():
            valueNodes.append(VariousNode(self,self._getNextLayer()))


    def _loadContainerLayer(self,fromTable):
        result = database.get().query("SELECT id FROM {0} WHERE toplevel = 1".format(fromTable)).getSingleColumn()
        self.elements = [ElementNode(id,self) for id in result]
        for element in self.elements:
            element.loadElements(fromTable)
        blacklist = tags.Storage()
        for criterion in self._collectCriteria(search.criteria.TagIdCriterion):
            for tag,value in criterion.valueIds.items():
                blacklist[tag].append(value)
        for element in self.elements:
            element.loadTags(blacklist)


class ValueNode(CriterionNode):
    def __init__(self,parent,layer,value,valueIds):
        CriterionNode.__init__(self,parent,layer,None)
        self.value = value
        self.valueIds = valueIds
    
    def __str__(self):
        return "<ValueNode '{0}'>".format(self.value)
    
    def getCriterion(self):
        return search.criteria.TagIdCriterion(self.valueIds)

                
class RootNode(CriterionNode):
    def __init__(self,table,model):
        self.table = table
        self.elements = None
        self.nextLayer = None # Set by the browser when the layers are created
        self.model = model
        
    def getParent(self):
        return None
    
    def getCriterion(self):
        return None

    def getModel(self):
        return self.model
        
    def update(self,recursive=False):
        if isinstance(self._getNextLayer(),layers.TagLayer):
            self._loadTagLayer(self.table)
            if (recursive or 
                db.query("SELECT COUNT(*) FROM {0}".format(self.table)).getSingle()
                     < self._getNextLayer().DIRECT_LOAD_LIMIT):
                for element in self.elements:
                    element.update(recursive)
        else: self._loadContainerLayer(TT_SMALL_RESULT)
        
    def _getNextLayer(self):
        return self.nextLayer
        
    def _getTable(self):
        return self.table
        
    def __str__(self):
        return "<RootNode>"


class VariousNode(CriterionNode):
    def __init__(self,parent,layer):
        CriterionNode.__init__(self,parent,layer,search.criteria.MissingTagCriterion(layer.tagSet))
        
    def __str__(self):
        return "<VariousNode>"
        
        
class ElementNode(Node):
    def __init__(self,id,parent,position = None):
        self.id = id
        self.elements = []
        self.parent = parent
        self.position = position
    
    def getModel(self):
        return self.parent.getModel()
    
    def hasChildren(self):
        return len(self.elements) > 0
        
    def getElements(self):
        return self.elements
    
    def getElementsCount(self):
        return len(self.elements)
    
    def retrieveElementList(self):
        if not self.elements:
            return [models.Element(self.id)]
        else:
            result = []
            for element in self.elements:
                result.extend(element.retrieveElementList())
            return result
            
    def __str__(self):
        if self.position is not None:
            return '<ElementNode "{0}">'.format(self.getTitle())
        else: return '<ElementNode {0} "{1}">'.format(self.position,self.getTitle())
    
    def isFile(self):
        return len(self.elements) == 0
        
    def loadElements(self,table):
        """Delete the stored element list and fetch the child elements from the database. You may use the <table>-parameter to restrict the elements to a specific table: The table with name <table> must contain a column 'id' and this method will only fetch elements which appear in that column."""
        self.elements = []
        result = db.query("""
                SELECT contents.element_id,contents.position
                FROM contents JOIN {0} ON contents.container_id = {1} AND contents.element_id = {0}.id
                ORDER BY contents.position
                """.format(table,self.id))
        for row in result:
            self.elements.append(ElementNode(row[0],self,row[1]))
        for element in self.elements:
            element.loadElements(table)
        
    def loadTags(self,blacklist):
        self.tags = tags.Storage()
        if self.elements:
            newBlacklist = blacklist.copy()
        tagIdList = ",".join(str(tag.id) for tag in (tags.TITLE,tags.ALBUM) + tags.artistTags)
        result = db.query("""
            SELECT tag_id,value_id 
            FROM tags
            WHERE container_id = {0} AND tag_id IN ({1})
            """.format(self.id,tagIdList))
        for row in result:
            tag = tags.get(row[0])
            if row[1] not in blacklist[tag]:
                self.tags[tag].append(tag.getValue(row[1]))
                # Do not write title tags on the blacklist as it is quite common for albums to contain a piece of the same title.
                if not self.isFile() and tag != tags.TITLE:
                    newBlacklist[tag].append(row[1])
        for element in self.elements:
            element.loadTags(newBlacklist)