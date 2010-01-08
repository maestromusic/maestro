#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from omg import tags,lowlevel
    
class Element:
    def __init__(self,id,tags=None):
        self.id = id
        self.tags = tags
        
    def getTag(self,tag):
        if self.tags is None:
            self.updateTags(False)
        if tag in self.tags:
            return self.tags[tag]
        else: return None
        
    def getTags(self):
        if self.tags is None:
            self.updateTags(False)
        return self.tags
    
    def updateTags(self,otherTags=False):
        self.tags = lowlevel.getTagsFromDB(self.id)
        if otherTags:
            self.tags.extend(lowlevel.getOtherTagsFromDB(self.id))

    def getTitle(self):
        if self.getTag(tags.TITLE) is None:
            return '<Kein Titel>'
        else: return " - ".join(self.getTag(tags.TITLE))


class Container(Element):    
    def __init__(self,id,tags=None,elements=None):
        Element.__init__(self,id,tags)
        self.elements = elements
        
    def getElements(self):
        if self.elements is None:
            self.updateElements()
        return self.elements
        
    def updateElements(self,table="containers",recursive=False):
        self.elements = []
        for id in lowlevel.getElements(table,self.id):
            self.elements.append(self._createChild(id))

    def getElementsCount(self):
        if self.elements is None:
            self.updateElements()
        return len(self.elements)
    
    def updateTags(self,otherTags=False,recursive=False):
        Element.updateTags(self,otherTags)
        if recursive:
            for element in self.elements:
                element.updateTags(otherTags,True) # This assumes that all elements are of type Container
        
    def __str__(self):
        return "<Container {0}>".format(self.id)
        
    def isFile(self):
        if self.elements is None:
            self.updateElements()
        return len(self.elements) == 0
        
    def _createChild(self,id):
        return Container(id)