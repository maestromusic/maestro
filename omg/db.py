#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import logging

from omg import database, FlexiDate
from omg import tags as tagsModule # this module defines a method called 'tags'
db = database.get()

logger = logging.getLogger()

query = db.query


#def contentIds(elid)

def parents(elid,recursive = False):
    """Return a list containing the ids of all parents of the element with id <elid>. If <recursive> is True all ancestors will be added recursively."""
    newList = list(query("SELECT container_id FROM contents WHERE element_id = ?",elid).getSingleColumn())
    if not recursive:
        return newList
    resultList = newList
    while len(newList) > 0:
        newList = list(query("""
                SELECT container_id
                FROM contents
                WHERE element_id IN ({0})
                """.format(",".join(str(n) for n in newList))).getSingleColumn())
        newList = [id for id in newList if id not in resultList] # Do not add twice
        resultList.extend(newList)
    return resultList
        
def position(parentId,elementId):
    return query("SELECT position FROM contents WHERE container_id = ? AND element_id = ?",
                    parentId,elementId).getSingle()

# Elements-Table
#===============================================
def isFile(elid):
    """Return whether the element with id <elid> exists and is a file."""
    return query("SELECT file FROM elements WHERE id = ?",elid).getSingle() == 1

def isContainer(elid):
    """Return whether the element with id <elid> exists and is a container."""
    return query("SELECT file FROM elements WHERE id = ?",elid).getSingle() == 0
    
def isToplevel(elid):
    """Return whether the element with id <elid> exists and is toplevel element."""
    return query("SELECT toplevel FROM elements WHERE id = ?",elid).getSingle() == 1
    
def elementCount(elid):
    """Return the number of children of the element with id <elid> or None if that element does not exist."""
    return query("SELECT elements FROM elements WHERE id  ?",elid).getSingle()

# Files-Table
#================================================
def path(elid):
    """Return the path of the file with id <elid> or None if that file does not exist.""" 
    return query("SELECT path FROM files WHERE element_id=?",fileid).getSingle()

def hash(elid):
    """Return the hash of the file with id <elid> or None if that file does not exist."""
    return query("SELECT hash FROM files WHERE element_id=?",fileid).getSingle()

def length(elid):
    """Return the length of the file with id <elid> or None if that file does not exist."""
    return query("SELECT length FROM files WHERE element_id=?",fileid).getSingle()

def verified(elid):
    """Return the verified-timestamp of the file with id <elid> or None if that file does not exist."""
    return query("SELECT verified FROM files WHERE element_id=?",fileid).getSingle()
    
def idFromPath(path):
    """Return the element_id of a file from the given path, or None if it is not found."""
    return database.get().query("SELECT element_id FROM files WHERE path=?",path).getSingle()

def idFromHash(hash):
    """Return the element_id of a file from its hash, or None if it is not found."""
    result = database.db.query("SELECT element_id FROM files WHERE hash=?",hash)
    if len(result)==1:
        return result.getSingle()
    elif len(result)==0:
        return None
    else:
        raise RuntimeError("Hash not unique upon filenames!")

# tagvalue-tables
#============================================
def valueFromId(tagSpec,valueId):
    """Return the value from the tag <tagSpec> with id <valueId> or None if that id does not exist."""
    tag = tagsModule.get(tagSpec)
    if tag.type == tagsModule.TYPE_DATE:
        value = query("SELECT DATE_FORMAT(value, '%Y-%m-%d') FROM tag_{} WHERE id = ?"
                        .format(tag.name),valueId).getSingle()
        if value is not None:
            return FlexiDate.strptime(value)
        else: return None 
    else: return query("SELECT value FROM tag_{} WHERE id = ?".format(tag.name),valueId).getSingle()

def idFromValue(tagSpec,value,insert=False):
    """Return the id of the given value in the tagtable of tag <tagSpec>. If the value does not exist, return None, unless the optional parameter <insert> is set to True. In that case insert the value into the table and return its id."""
    tag = tagsModule.get(tagSpec)
    value = _encodeValue(tag.type,value)
    id = query("SELECT id FROM tag_{} WHERE value = ?".format(tag.name),value).getSingle()
    if insert and id is None:
        result = query("INSERT INTO tag_{} SET value = ?".format(tag.name),value)
        return result.insertId()
    else: return id

def addTagValue(tagSpec,value):
    tag = tagsModule.get(tagSpec)
    result = query("INSERT INTO tag_{} SET value=?".format(tag.name),_formatValue(tag.type,value))
    return result.insertId()

def removeTagValue(tagSpec,value):
    tag = tagsModule.get(tagSpec)
    result = query("DELETE FROM tag_{} WHERE value=?".format(tag.name),_formatValue(tag.type,value))
    return result.affectedRows()

def removeTagValueById(tagSpec,valueId):
    tag = tagsModule.get(tagSpec)
    result = query("DELETE FROM tag_{} WHERE id=?".format(tag.name),valueId)
    return result.affectedRows()


# tags-Table
#==============================================
def tags(elid,tagList=None):
    if tagList is not None:
        if isinstance(tagList,int) or isinstance(tagList,str) or isinstance(tagList,tagsModule.Tag):
            tagid = tagsModule.get(tagList).id
            additionalWhereClause = " AND tag_id = {0}".format(tagid)
        else:
            tagList = [tagsModule.get(tag).id for tag in tagList]
            additionalWhereClause = " AND tag_id IN ({0})".format(",".join(str(tag.id) for tag in tagList))
    else: additionalWhereClause = ''
    result = query("""
                SELECT tag_id,value_id 
                FROM tags
                WHERE element_id = {0} {1}
                """.format(elid,additionalWhereClause))
    tags = []
    for tagid,valueid in result:
        tag = tagsModule.get(tagid)
        value = valueFromId(tag,valueid)
        if value is None:
            logger.warning(("Database is corrupt: Element {0} has a {1}-tag with id {2} but "
                           +"this id does not exist in tag_{1}.").format(elid,tag.name,valueid))
        else: tags.append((tag,value))
    return tags

def tagValues(elid,tagList):
    return [value for tag,value in tags(elid,tagList)] # return only the second tuple part
        
def addTag(elids,tagSpec,value):
    """Add an entry 'tag=value' into the tags-table. If necessary the value is inserted into the correct tagvalue-table."""
    addTagById(elids,tagSpec,idFromValue(tagSpec,value,insert=True))

def addTagById(elids,tagSpec,valueId):
    tag = tagsModule.get(tagSpec)
    if isinstance(elids,int): # Just one element
        elids = (elids,)
    for elid in elids:
        query("INSERT INTO tags(element_id,tag_id,value_id) VALUES (?,?,?)",elid,tag.id,valueId)

def removeTag(elid,tagSpec,value):
    removeTagById(elid,tagSpec,idFromValue(tagSpec,value))
    
def removeTagById(elid,tagSpec,valueId):
    tag = tagsModule.get(tagSpec)
    result = query("DELETE FROM tags WHERE element_id=? AND tag_id=? AND value_id=?",elid,tag.id,valueId)
    return result.affectedRows()

# Help methods
#=================================================
def _encodeValue(tagType,value):
    if tagType != tagsModule.TYPE_DATE:
        return value
    elif isinstance(value,FlexiDate):
        return value.SQLformat()
    else: return FlexiDate.strptime(value).SQLformat()