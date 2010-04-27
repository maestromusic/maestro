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

class Container:
    tags = None
    elements = None
    
    def __init__(self,id):
        assert isinstance(id,int)
        self.id = id

    def getPath(self):
        return db.query("SELECT path FROM files WHERE container_id = {0}".format(self.id)).getSingle()
    
    def getTitle(self):
        """Return a title of this element which is created from the title-tags. If this element does not contain a title-tag some dummy-title is returned."""
        if self.tags is None:
            self.loadTags()
        if tags.TITLE in self.tags:
            return " - ".join(self.tags[tags.TITLE])
        else: return '<Kein Titel>'
        
    def loadElements(self,recursive=False,table="containers"):
        """Delete the stored element list and fetch the child elements from the database. You may use the <table>-parameter to restrict the elements to a specific table: The table with name <table> must contain a column 'id' and this method will only fetch elements which appear in that column. If <recursive> is true updateElements will be called recursively for all child elements."""
        self.elements = []
        result = db.query("""
                SELECT contents.element_id
                FROM contents JOIN {0} ON contents.container_id = {1} AND contents.element_id = {0}.id
                ORDER BY contents.position
                """.format(table,self.id)).getSingleColumn()
        for id in result:
            self.elements.append(Container(id))
        if recursive:
            for element in self.elements:
                element.loadElements(True,table)


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
            for element in self.elements:
                element.loadTags(newBlacklist)
    
    def __str__(self):
        if self.tags is not None:
            return "<Container {0}".format(self.getTitle())
        else: return "<Container {0}>".format(self.id)