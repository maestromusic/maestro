#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from omg import tags, database

def getTagValue(tag,valueId):
    """Retrieve the value of the indexed tag <tag> with the given <valueId> from the corresponding tag-table."""
    tableName = "tag_"+tag.name
    value = database.get().query("SELECT value FROM "+tableName+" WHERE id = ?",valueId).getSingle()
    if tag.type == 'date':
        value = database.get().getDate(value)
    return value


class Element:
    """Base class for files and containers. This class stores an id of a row in the containers-table and can fetch the corresponding tags from the database.
    
    Public attributes:
    tags: Dictionary mapping tags to lists (!) of values. The methods of this class guarantee that the dictionary contains no empty lists and you should keep this invariant then modifying tags directly. If tags is None, methods like getTag will automatically call updateTags to fetch values from the database.
    """
    
    def __init__(self,id,tags=None):
        """Initialize a new element with the given id and optionally define its tags."""
        self.id = id
        self.tags = tags
        
    def getTag(self,tag):
        """Get a list of all tag-values of the given tag stored in this element. If """
        if self.tags is None:
            self.updateTags(False)
        if tag in self.tags:
            return self.tags[tag]
        else: return None
        
    def getTags(self):
        """Return self.tag if not None, otherwise update indexed tags from the database and return them."""
        if self.tags is None:
            self.updateTags(False)
        return self.tags
    
    def updateTags(self,otherTags=False):
        """Delete the tags stored in this element and fetch the tags from the database. If otherTags is false (which is the default), only indexed tags are fetched."""
        self.tags = {}
        result = database.get().query("SELECT tag_id,value_id FROM tags WHERE container_id = ?",self.id)
        for row in result:
            tag = tags.get(row[0])
            if tag not in self.tags:
                self.tags[tag] = []
            self.tags[tag].append(getTagValue(tag,row[1]))

        if otherTags:
            result = database.get().query("SELECT tagname,value FROM othertags WHERE container_id = ?",self.id)
            for row in result:
                tag = tags.OtherTag(row[0])
                if tag not in self.tags:
                    tagsToReturn[tag] = []
                self.tags[tag].append(row[1])

    def getTitle(self):
        """Return a title of this element which is created from the title-tags. If this element does not contain a title-tag some dummy-title is returned."""
        if self.getTag(tags.TITLE) is None:
            return '<Kein Titel>'
        else: return " - ".join(self.getTag(tags.TITLE))


class Container(Element):
    """Subclass of element which may contain child elements (which should also be of type Container). This class contains methods to fetch those child elements from the database.
    
    public attributes:
    tags: confer Element
    elements: list of child elements. If elements is None, methods like getElements will call updateElements to fetch them from the database.
    """
    
    def __init__(self,id,tags=None,elements=None):
        """Initialize a new container with an id and optionally with tags and elements."""
        Element.__init__(self,id,tags)
        self.elements = elements
        
    def getElements(self):
        """Return the list of child elements of this element. If elements is None updateElements is called first."""
        if self.elements is None:
            self.updateElements()
        return self.elements
        
    def updateElements(self,table="containers",recursive=False):
        """Delete the stored element list and fetch the child elements from the database. You may use the <table>-parameter to restrict the elements to a specific table: The table with name <table> must contain a column 'id' and this method will only fetch elements which appear in that column. If <recursive> is true updateElements will be called recursively for all child elements."""
        self.elements = []
        result = database.get().query("""
                SELECT {0}.id
                FROM contents JOIN {0} ON contents.container_id = {1} AND contents.element_id = {0}.id
                ORDER BY contents.position
                """.format(table,self.id))
        for id in result.getSingleColumn():
            self.elements.append(self._createChild(id))
        if recursive:
            for element in self.elements:
                element.updateElements(table,True) # This assumes that all elements are of type Container
                
    def getElementsCount(self):
        """Return the number of child elements. If elements is None updateElements will be called first."""
        if self.elements is None:
            self.updateElements()
        return len(self.elements)
    
    def updateTags(self,otherTags=False,recursive=False):
        """Delete the tags stored in this element and fetch the tags from the database. If otherTags is false (which is the default), only indexed tags are fetched. If recursive is true, updateTags will be called recursively for all child elements."""
        Element.updateTags(self,otherTags)
        if recursive:
            for element in self.elements:
                element.updateTags(otherTags,True) # This assumes that all elements are of type Container
        
    def __str__(self):
        return "<Container {0}>".format(self.id)
        
    def isFile(self):
        """Return true if and only if this container is a file."""
        if self.elements is None:
            self.updateElements()
        return len(self.elements) == 0
        
    def _createChild(self,id):
        """Create a child element with the given id. This method is used by subclasses to ensure that child elements have a specific type."""
        return Container(id)