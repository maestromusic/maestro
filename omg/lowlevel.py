#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from omg import tags,database
db = database.get()

def getTagValue(tag,valueId):
    tableName = "tag_"+tag.name
    value = db.query("SELECT value FROM "+tableName+" WHERE id = ?",valueId).getSingle()
    if tag.type == 'date':
        value = db.getDate(value)
    return value

def getTagsFromDB(containerId):
    tagsToReturn = {}

    result = db.query("SELECT tag_id,value_id FROM tags WHERE container_id = ?",containerId)
    for row in result:
        tag = tags.get(row[0])
        if tag in tagsToReturn:
            tagsToReturn[tag].append(getTagValue(tag,row[1]))
        else: tagsToReturn[tag] = [getTagValue(tag,row[1])]
    return tagsToReturn

def getOtherTagsFromDB(containerId):
    tagsToReturn = {}
    result = db.query("SELECT tagname,value FROM othertags WHERE container_id = ?",containerId)
    for row in result:
        tag = tags.OtherTag(row[0])
        if not tag in tagsToReturn:
            tagsToReturn[tag] = []
        tagsToReturn[tag].append(row[1])
    return tagsToReturn
    
def getElements(table,containerId):
    result = db.query("""
            SELECT {0}.id
            FROM contents JOIN {0} ON contents.container_id = {1} AND contents.element_id = {0}.id
            ORDER BY contents.position
            """.format(table,containerId))
    return (row[0] for row in result)