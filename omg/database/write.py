#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation

import itertools
from omg import database as db

def setContents(data):
    """Set contents of one or more elements. *data* is a dict mapping ids to lists of contents. The lists
    of contents must contain elements with an id. This method is not recursive."""
    # TODO: Handle positions 
    db.multiQuery(
        "DELETE FROM {}contents WHERE container_id = ? AND position > ?".format(db.prefix),
        ((id,len(contents)) for id,contents in data.items()))
    db.multiQuery(
        "REPLACE INTO {}contents (container_id,position,element_id) VALUES (?,?,?)".format(db.prefix),
        ((id,pos,element.id) for pos,element in contents for id,contents in data.items()))


def addTagValuesById(elids,tag,valueIds):
    """Add tag values given by their id to some elements. *elids* is either a single id or a list of ids,
    *tag* is the affected tag and *valueIds* is a list of values-ids for *tag*.
    
    This method does not check for duplicates!
    """
    if not hasattr(elids,'__iter__'):
        elids = [elids]
    db.multiQuery("INSERT INTO {}tags (element_id,tag_id,value_id) VALUES (?,{},?)"
                   .format(db.prefix,tag.id),
                   itertools.product(elids,valueIds))
    
def addTagValues(elids,tag,values):
    """Add tag values to some elements. *elids* is either a single id or a list of ids, *tag* is the
    affected tag and *values* is a list of values. If a value does not already exist in the database, it
    will be inserted.
    
    This method does not check for duplicates!
    """
    addTagValuesById(elids,tag,[db.idFromValue(tag,value,insert=True) for value in values])
    
    
def removeAllTagValues(elids,tag):
    """Remove all values of the given tag from some elements. *elids* is either a single id or a list of ids.
    """
    db.query("DELETE FROM {}tags WHERE element_id IN ({}) AND tag_id = {}"
               .format(db.prefix,db.csList(elids),tag.id))

def removeTagValuesById(elids,tag,valueIds):
    """Remove some values of one tag from some elements. *elids* is either a single id or a list of ids,
    *tag* is the affected tag, *valueIds* is a list of value-ids of *tag*."""
    db.query("DELETE FROM {}tags WHERE element_id IN ({}) AND tag_id = {} AND value_id IN ({})"
                .format(db.prefix,db.csList(elids),tag.id,db.csList(valueIds)))
    
def removeTagValues(elids,tag,values):
    """Remove some values of one tag from some elements. *elids* is either a single id or a list of ids,
    *tag* is the affected tag, *valueIds* is a list of values of *tag*."""
    removeTagValuesById(elids,tag,(db.idFromValue(tag,value) for value in values))
    
def changeTagValueById(elids,tag,oldId,newId):
    """Change a tag value in some elements. *elids* is either a single id or a list of ids, *tag* is the
    affected tag, *oldId* and *newId* are the ids of the old and new value, respectively."""
    db.query("UPDATE {}tags SET value_id = ? WHERE element_id IN ({}) AND tag_id = ? AND value_id = ?"
               .format(db.prefix,db.csList(elids)),newId,tag.id,oldId)

def changeTagValue(elids,tag,oldValue,newValue):
    """Change a tag value in some elements. *elids* is either a single id or a list of ids, *tag* is the
    affected tag, *oldValue* and *newValue* are the old and new value, respectively. If the new value does
    not already exist in the database, it will be created.
    """
    oldId = db.idFromValue(tag,oldValue)
    newId = db.idFromValue(tag,newValue,insert=True)
    changeTagValueById(elids,tag,oldId,newId)
    