#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from omg import search, models, database, tags
from . import TT_BIG_RESULT, TT_SMALL_RESULT

class Node:
    def getElementsCount(self): pass
    def getElements(self): pass
    def load(self): pass
    def getParent(self): pass
    
    def mergeElements(self):
        for i in range(0,self.getElementsCount()):
            parent = self.elements[i]
            if parent.getElementsCount() == 1:
                child = parent.elements[0]
                child.mergeWithParent()
                self.elements[i] = child


class ValueNode(Node):
    def __init__(self,value,match=None):
        self.value = value
        if not match is None:
            self.match = match
        self.elements = []
    
    def load(self):
        search.search(self.match,TT_SMALL_RESULT,TT_BIG_RESULT,addChildren=True,addParents=True)
        result = database.get().query("SELECT id FROM {0} WHERE toplevel = 1".format(TT_SMALL_RESULT)).getSingleColumn()
        self.elements = [ElementNode(id,self) for id in result]
        for element in self.elements:
            element.loadElements(TT_SMALL_RESULT)
        self.mergeElements()
        blacklist = tags.Storage({k:[self.value] for k in self.match.getTags()})
        for element in self.elements:
            element.loadTags(blacklist)
        self.improve() # TODO should be called on first expand
        
    def improve(self):
        self.elements.sort(key=ElementNode.getTitle)

    def getElementsCount(self):
        # Pretend to have at least one child so that this node will be expandable
        return len(self.elements) if self.elements else 1
        
    def getElements(self):
        if not self.elements:
            raise Exception("Elements should have been loaded.")
        return self.elements
        
    def __str__(self):
        return "<ValueNode '{0}'>".format(self.value)

    def getParent(self):
        return None

class ElementNode(models.Container,Node):
    def __init__(self,id,parent):
        models.Container.__init__(self,id)
        self.elements = []
        self.containers = []
        self.parent = parent
        
    def loadElements(self,table):
        self.updateElements(table)
        for element in self.elements:
            element.loadElements(table)
        self.mergeElements()
        
    def loadTags(self,blacklist):
        self.updateTags()
        self.tags.removeTags(blacklist)
        newBlacklist = blacklist.copy()
        newBlacklist.merge(self.tags)
        # If nodes are merged then the (former) child will load the tag of the parent and vice versa so check of tags are already loaded to prevent infinite recursion.
        for element in self.elements:
            if element.tags is None:
                element.loadTags(newBlacklist)
        for element in self.containers:
            if element.tags is None:
                element.loadTags(blacklist)
    
    def mergeWithParent(self):
        parent = self.parent
        self.parent = parent.getParent()
        if isinstance(parent,ValueNode):
            for tag in parent.match.getTags():
                self.tags.addUnique(tag,parent.value)
        else: # isinstance(node,ElementNode):
            self.containers.insert(0,parent)
            
    def getParent(self):
        return self.parent
        
    def __str__(self):
        return '<ElementNode "{0}">'.format(self.getTitle())
        
    def _createChild(self,id):
        return ElementNode(id,self)