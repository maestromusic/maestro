#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.

import itertools
from omg import database as db, tags


def createNewElement(file,major, id = None):
    """Insert a new element into the database and return its id. Set the file and major flag as given in the
    parameters and set the toplevel flag and elements counter to 1 and 0, respectively. If an *id* is given,
    the new element will have this id, otherwise an id is created automatically."""
    if id is not None:
        db.query("INSERT INTO {}elements (id, file, toplevel, elements, major) VALUES (?, ?, 1, 0, ?)"
                 .format(db.prefix), id, int(file), int(major))
        return id
    else:
        return db.query("INSERT INTO {}elements (file,toplevel,elements,major) VALUES (?,1,0,?)"
                        .format(db.prefix),int(file),int(major)).insertId()
                        
                        
def deleteElements(ids):
    """Delete the elements with the given ids from the database and update element counter and toplevel
    flags. Due to the foreign keys in the database, this will also delete all tag, flag and content relations
    of the elements.
    """
    if len(ids) == 0:
        return
    db.transaction()
    parentIds = db.parents(ids)
    contentsIds = db.contents(ids)
    db.query("DELETE FROM {}elements WHERE id IN ({})".format(db.prefix,db.csList(ids)))
    updateElementsCounter(parentIds)
    updateToplevelFlags(contentsIds)
    db.commit()


def setContents(data):
    """Set contents of one or more elements. *data* is a dict mapping ids to lists of contents. The lists
    of contents must contain elements with an id and a position. This method is not recursive."""
    db.transaction()
    
    # Remove old contents but remember their ids
    oldContents = db.contents(data.keys())
    db.query("DELETE FROM {}contents WHERE container_id IN ({})".format(db.prefix,db.csList(data.keys())))
    
    newContents = [element.id for element in itertools.chain.from_iterable(data.values())]
    
    # Insert new contents
    if len(newContents):
        params = ((cid,el.position,el.id) for cid,contents in data.items() for el in contents)  
        db.multiQuery("INSERT INTO {}contents (container_id,position,element_id) VALUES(?,?,?)"
                        .format(db.prefix),params)
                    
    # Update element counter of changed containers
    updateElementsCounter(data.keys())

    # Set toplevel flag of all contents to 0
    if len(newContents):
        db.query("UPDATE {}elements SET toplevel = 0 WHERE id IN ({})"
                    .format(db.prefix,db.csList(newContents)))
                
    # Finally update the toplevel flag of elements that got removed from the contents
    updateToplevelFlags((id for id in oldContents if not id in newContents))
    
    db.commit()

def addContents(data):
    """Add contents relations to the database without touching existing ones. *data* is a list of
    (parentID, position, elementID) tuples."""
    db.multiQuery("INSERT INTO {}contents (container_id, position, element_id) VALUES (?,?,?)"
                  .format(db.prefix), data)
    
def removeContents(data):
    """Remove contents of one or more elements. *data* is a list of (parentID, position) tuples."""
    db.multiQuery("DELETE FROM {}contents WHERE container_id = ? AND position = ?"
                   .format(db.prefix), data)

def changePositions(parentID, changes):
    """Change the positions of children of *parentID* as given by *changes*, which is a list of (oldPos, newPos)
    tuples."""
    db.multiQuery("UPDATE {}contents SET position=? WHERE container_id=? AND position=?"
                  .format(db.prefix), [(newPos,parentID,oldPos) for (oldPos,newPos) in changes ])
     
def updateElementsCounter(elids = None):
    """Update the elements counter. If *elids* is a list of elements-ids, the counters of those elements will
    be updated. If *elids* is None, all counters will be set to their correct value."""
    if elids is not None:
        cslist = db.csList(elids)
        if cslist == '':
            return
        whereClause = "WHERE id IN ({})".format(cslist)
    else: whereClause = '' 
    db.query("""
        UPDATE {0}elements
        SET elements = (SELECT COUNT(*) FROM {0}contents WHERE container_id = id)
        {1}
        """.format(db.prefix,whereClause))
        
        
def updateToplevelFlags(elids = None):
    """Update the toplevel flags. If *elids* is a list of elements-ids, the flags of those elements will
    be updated. If *elids* is None, all flags will be set to their correct value."""
    if elids is not None:
        cslist = db.csList(elids)
        if cslist == '':
            return
        whereClause = "WHERE id IN ({})".format(cslist)
    else: whereClause = '' 
    db.query("""
        UPDATE {0}elements
        SET toplevel = (NOT id IN (SELECT element_id FROM {0}contents))
        {1}
        """.format(db.prefix,whereClause))


def addFile(elid,path,hash,length):
    """Add a file with the given data to the file table."""
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
    
    
def removeAllTagValues(elids,tags):
    """Remove all values of the given tag from some elements. *elids* is either a single id or a list of ids.
    Analogously *tags* may be a single tag or a list of tags.
    """
    db.query("DELETE FROM {}tags WHERE element_id IN ({}) AND tag_id IN ({})"
               .format(db.prefix,db.csList(elids),db.csIdList(tags)))


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


def setTags(elid,tags):
    """Set the tags of the element with it *elid* to the tags.Storage-instance *tags*, removing all existing
    tags of that element."""
    db.query("DELETE FROM {}tags WHERE element_id = ?".format(db.prefix),elid)
    for tag in tags:
        db.multiQuery("INSERT INTO {}tags (element_id,tag_id,value_id) VALUES (?,?,?)".format(db.prefix),
                      [(elid,tag.id,db.idFromValue(tag,value,insert=True)) for value in tags[tag]])


def setSortValue(tag, valueId, sortValue):
    """Set the sort-value of the value of *tag* with id *valueId* to *sortValue*."""
    db.query("UPDATE {}values_{} SET sort_value = ? WHERE tag_id = ? AND id = ?".format(db.prefix, tag.type),
             sortValue, tag.id, valueId)

def setHidden(tagSpec, valueId, state):
    """Set the given tag value's "hidden" attribute to *state*."""
    tag = tags.get(tagSpec)
    db.query("UPDATE {}values_{} SET hide = ? WHERE tag_id = ? AND id = ?".format(db.prefix, tag.type),
             state, tag.id, valueId) 

def addFlag(elids,flag):
    """Add the given flag to the elements with the given ids, ignoring elements that already have the
    flag."""
    values = ','.join('({},{})'.format(elid,flag.id) for elid in elids)
    db.query("INSERT IGNORE INTO {}flags (element_id,flag_id) VALUES {}".format(db.prefix,values))
    
    
def removeFlag(elids,flag):
    """Remove a flag from the elements with the specified ids, ignoring elements that do not have the
    flag."""
    db.query("DELETE FROM {}flags WHERE flag_id = {} AND element_id IN ({})"
                .format(db.prefix,flag.id,db.csList(elids)))
    

def setFlags(elid,flags):
    """Give the element with the given id exactly the flags in the list *flags*."""
    db.query("DELETE FROM {}flags WHERE element_id = ?".format(db.prefix),elid)
    if len(flags) > 0:
        values = ["({},{})".format(elid,flag.id) for flag in flags]
        db.query("INSERT INTO {}flags (element_id,flag_id) VALUES {}".format(db.prefix,','.join(values)))
    
def setMajor(elid, major):
    db.query("UPDATE {}elements SET major = ? WHERE id = ?".format(db.prefix), major, elid)