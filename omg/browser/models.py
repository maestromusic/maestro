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

class ValueNode:
    def __init__(self,value,match=None):
        self.value = value
        if not match is None:
            self.match = match
        self.elements = []
    
    def load(self,match=None):
        if match is None:
            if hasattr(self,'match'):
                match = self.match
            else: raise Exception("ValueNode needs a match to load data.")
        search.search(match,TT_SMALL_RESULT,TT_BIG_RESULT,addChildren=True,addParents=True)
        
        result = database.get().query("SELECT id FROM {0} WHERE toplevel = 1".format(TT_SMALL_RESULT)).getSingleColumn()
        self.elements = [ElementNode(id,self) for id in result]
        blacklist = tags.Storage({k:[self.value] for k in self.match.getTags()})
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
        return "<ValueNode '{0}'>".format(self.value)

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
        self.tags.removeTags(blacklist)
        newBlacklist = blacklist.copy()
        newBlacklist.merge(self.tags)
        for element in self.elements:
            element.load(table,newBlacklist)
    
    def getParent(self):
        return self.parent
        
    def __str__(self):
        return '<ElementNode "{0}">'.format(self.getTitle())
        
    def _createChild(self,id):
        return ElementNode(id,self)