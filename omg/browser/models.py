#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from omg import search, models, database
from . import TT_BIG_RESULT, TT_SMALL_RESULT

class Blacklist:
    def __init__(self,tags=None):
        self.tags = tags
            
    def copy(self):
        return Blacklist(self.tags.copy())

    def merge(self,tags):
        for tag,valueList in tags.items():
            if not tag in self.tags:
                self.tags[tag] = valueList[:] # Copy the list
            else: list(set(self.tags[tag]).union(set(valueList)))

class ValueNode:
    def __init__(self,value,query=None):
        self.value = value
        if not query is None:
            self.query = query
        self.elements = []
    
    def load(self,query=None):
        if query is None:
            if hasattr(self,'query'):
                query = self.query
            else: raise Exception("ValueNode needs a query to load data.")
        search.search(query,TT_SMALL_RESULT,TT_BIG_RESULT,addChildren=True,addParents=True)
        
        result = database.get().query("SELECT id FROM {0} WHERE toplevel = 1".format(TT_SMALL_RESULT)).getSingleColumn()
        self.elements = [ElementNode(id,self) for id in result]
        blacklist = Blacklist({k:[self.value] for k in self.query.getTags()})
        for element in self.elements:
            element.load(TT_SMALL_RESULT,blacklist)
        self.elements.sort(key=ElementNode.getTitle)

    def getElementsCount(self):
        # Pretend to have at least one child so that this node will be expandable
        return len(self.elements) if self.elements else 1
        
    def getElements(self):
        if not self.elements:
            raise Exception("Elements should have been loaded.")
        return self.elements
        
    def __str__(self):
        return "<ValueNode '{0}'>".format(self.value)#.format(self.value,"\n".join([str(e) for e in self.elements]))

    def getParent(self):
        return None

class ElementNode(models.Container):
    def __init__(self,id,parent):
        models.Container.__init__(self,id)
        self.elements = []
        self.parent = parent
        
    def load(self,table,blacklist):
        self.updateElements(table)
        self.updateTags()
        
        
        for tag,taglist in self.tags.items():
            if not taglist:
                print("Problem in id {0} and tag {1}".format(self.id,tag))
                
        for tag in self.tags.keys():
            if tag in blacklist.tags:
                for removeTag in blacklist.tags[tag]:
                    self.tags[tag] = list(set(self.tags[tag]) - set(blacklist.tags[tag]))
        for tag in [k for k,l in self.tags.items() if not l]:
            del self.tags[tag]
                
        newBlacklist = blacklist.copy()
        newBlacklist.merge(self.tags)
        
        for element in self.elements:
            element.load(table,newBlacklist)
    
    def getParent(self):
        return self.parent
        
    def __str__(self):
        return '<ElementNode "{0}">'.format(self.getTitle())#{1}'.format(self.getTitle(),"\n".join([str(e) for e in self.elements]))
        
    def _createChild(self,id):
        return ElementNode(id,self)