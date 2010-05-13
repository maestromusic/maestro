#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from omg import tags, database
db = database.get()

class Element:
    tags = None
    contents = None
    
    def __init__(self,id):
        assert isinstance(id,int)
        self.id = id

    def isFile(self):
        if self.contents is None:
            return None
        else: return len(self.contents) == 0
        
    def getPath(self):
        return db.query("SELECT path FROM files WHERE container_id = {0}".format(self.id)).getSingle()
    
    def getTitle(self):
        """Return a title of this element which is created from the title-tags. If this element does not contain a title-tag some dummy-title is returned."""
        if self.tags is None:
            self.loadTags()
        if tags.TITLE in self.tags:
            return " - ".join(self.tags[tags.TITLE])
        else: return '<Kein Titel>'
        
    def loadContents(self,recursive=False,table="containers"):
        """Delete the stored contents-list and fetch the contents from the database. You may use the <table>-parameter to restrict the child elements to a specific table: The table with name <table> must contain a column 'id' and this method will only fetch elements which appear in that column. If <recursive> is true loadContents will be called recursively for all child elements."""
        self.contents = []
        result = db.query("""
                SELECT contents.element_id
                FROM contents JOIN {0} ON contents.container_id = {1} AND contents.element_id = {0}.id
                ORDER BY contents.position
                """.format(table,self.id)).getSingleColumn()
        for id in result:
            self.contents.append(Element(id))
        if recursive:
            for element in self.contents:
                element.loadContents(recursive,table)


    def loadTags(self,recursive=False,tagList=None):
        self.tags = tags.Storage()
        
        if tagList is not None:
            additionalWhereClause = " AND tag_id IN ({0})".format(",".join(str(tag.id) for tag in tagList))
        else: additionalWhereClause = ''
        
        result = db.query("""
            SELECT tag_id,value_id 
            FROM tags
            WHERE container_id = {0} {1}
            """.format(self.id,additionalWhereClause))
        for row in result:
            tag = tags.get(row[0])
            self.tags[tag].append(tag.getValue(row[1]))
        if recursive:
            for element in self.contents:
                element.loadTags(recursive,tagList)
    
    def ensureTagsAreLoaded(self):
        if self.tags is None:
            self.loadTags()
        
    def ensureContentsAreLoaded(self):
        if self.contents is None:
            self.loadContents()
            
    def index(self,element):
        for i in range(0,len(self.contents)):
            if self.contents[i].id == element.id:
                return i
        raise ValueError("Element.index: Element {0} is not contained in element {1}.".format(element.id,self.id))
        
    def find(self,element):
        for i in range(0,len(self.contents)):
            if self.contents[i].id == elements.id:
                return i
        return -1
    
    def getLength(self):
        if self.contents is None:
            return None
        if len(self.contents) == 0:
            return db.query("SELECT length FROM files WHERE container_id = {0}".format(self.id)).getSingle()
        else:
            try:
                return sum(element.getLength() for element in self.contents)
            except TypeError: # At least one element does not know its length
                return None

    def __str__(self):
        if self.tags is not None:
            return "<Element {0}".format(self.getTitle())
        else: return "<Element {0}>".format(self.id)