#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.

import itertools
from omg import database as db

def createNewElement(file,toplevel,elementNumber,major):
    return db.query("INSERT INTO {}elements (file,toplevel,elements,major) VALUES (?,1,0,?)"
                        .format(db.prefix),int(file),int(major)).insertId()
                        
                        
def deleteElements(ids):
    db.transaction()
    parentIds = db.parents(ids)
    contentsIds = db.contents(ids)
    db.query("DELETE FROM {}elements WHERE id IN ({})".format(db.prefix,db.csList(ids)))
    updateElementsCounter(parents)
    updateToplevelFlags(contents)
    db.commit()


def setContents(data):
    """Set contents of one or more elements. *data* is a dict mapping ids to lists of contents. The lists
    of contents must contain elements with an id and a position. This method is not recursive."""
    db.transaction()
    
    # Remove old contents but remember their ids
    oldContents = db.contents(data.keys())
    db.query("DELETE FROM {}contents WHERE container_id IN ({})".format(db.prefix,db.csList(data.keys())))
    
    # Insert new contents
    params = ((cid,el.position,el.id) for el in contents for cid,contents in data.items())  
    db.multiQuery("INSERT INTO {}contents (container_id,position,element_id) VALUES(?,?,?)"
                    .format(db.prefix),params)
                    
    # Update element counter of changed containers
    db.updateElementsCounter(data.keys())

    # Set toplevel flag of all contents to 0
    contents = [element.id for element in itertools.chain.from_iterable(data.values())]
    db.query("UPDATE {}elements SET toplevel = 0 WHERE id IN ({})"
                .format(db.prefix,db.csList(contents)))
                
    # Finally update the toplevel flag of elements that got removed from the contents
    db.updateToplevelFlags((id for id in oldContents if not id in newContents))
    
    db.commit()


def updateElementsCounter(elids = None):
    if elids is not None:
        whereClause = "WHERE id IN ({})".format(db.csList(elids))
    else: whereClause = '' 
    db.query("""
        UPDATE {0}elements
        SET elements = (SELECT COUNT(*) FROM {0}contents WHERE container_id = id)
        {1}
        """.format(db.prefix,whereClause))
        
        
def updateToplevelFlags(elids = None):
    if elids is not None:
        whereClause = "WHERE id IN ({})".format(db.csList(elids))
    else: whereClause = '' 
    db.query("""
        UPDATE {0}elements
        SET toplevel = (NOT id IN (SELECT element_id FROM {0}contents))
        {1}
        """.format(db.prefix,whereClause))


def addFile(elid,path,hash,length):
    db.query("INSERT INTO {}files (element_id,path,hash,length) VALUES (?,?,?,?)"
                .format(db.prefix),elid,path,hash,length)
                
                
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


def changeSortValue(tag, valueId, sortValue):
    db.query("UPDATE {}values_{} SET sort_value = ? WHERE tag_id = ? AND id = ?".format(db.prefix, tag.type),
             sortValue, tag.id, valueId)