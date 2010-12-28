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


def contents(elids,recursive=False):
    if isinstance(elids,int):
        elids = [elids]

    newList = list(query("""
        SELECT DISTINCT element_id
        FROM contents
        WHERE container_id IN ({})
        """.format(",".join(str(id) for id in elids))).getSingleColumn())
    if not recursive:
        return newList
    resultList = newList
    while len(newList) > 0:
        newList = list(query("""
                SELECT element_id
                FROM contents
                WHERE container_id IN ({0})
                """.format(",".join(str(n) for n in newList))).getSingleColumn())
        newList = [id for id in newList if id not in resultList] # Do not add twice
        resultList.extend(newList)
    return resultList

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

def saveContainer(container):
    assert not container.isInDB() and container.isContainer()

    # Create the container
    result = query("INSERT INTO elements(name,file,toplevel,elements) VALUES (?,0,1,?)",
                        container.getTitle(),container.getChildrenCount())
    container.id = result.insertId()

    # Save the tags
    setTags(container.id,container.tags,append=True)

    # Save the contents
    for i in range(container.getChildrenCount()):
        query("INSERT INTO contents(container_id,position,element_id) VALUES (?,?,?)",
                container.id,i+1,container.getChildren()[i].id)

    # Set toplevel to 0 for all elements
    elementIds = ",".join(str(el.id) for el in container.getChildren())
    query("UPDATE elements SET toplevel = 0 WHERE id IN ({})".format(elementIds))


def deleteElements(elids):
    """Remove elements together with all of their content and tag references from the database."""
    idList = ",".join(str(id) for id in elids)
    db.query("DELETE FROM tags WHERE element_id IN ({})".format(idList))
    db.query("DELETE FROM files WHERE element_id IN ({})".format(idList))
    
    parentIds = list(db.query("SELECT container_id FROM contents WHERE element_id IN ({})"
                        .format(idList)).getSingleColumn())
    contentIds = list(db.query("SELECT element_id FROM contents WHERE container_id IN ({})"
                        .format(idList)).getSingleColumn())
    db.query("DELETE FROM contents WHERE container_id IN ({}) OR element_id IN ({})".format(idList,idList))
    
    if len(parentIds) > 0:
        # Correct element counters
        db.query("""
            UPDATE elements 
            SET elements = (SELECT COUNT(*) FROM contents WHERE container_id = id)
            WHERE id IN ({})
            """.format(",".join(str(id) for id in parentIds)))
    
    if len(contentIds) > 0:
        # Set toplevel to 1 for those elements which do not have a parent anymore
        db.query("""
            UPDATE elements LEFT JOIN contents ON elements.id=contents.element_id
            SET elements.toplevel = 1
            WHERE contents.container_id IS NULL AND elements.id IN ({})
            """.format(",".join(str(id) for id in contentIds)))

    # Finally remove the elements itself
    db.query("DELETE FROM elements WHERE id IN ({})".format(idList))


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
    """Return all values which the element with id <elid> possesses in any of the tags in tagList (which may be a list of tag-specifiers or simply a single tag-specifier)."""
    return [value for tag,value in tags(elid,tagList)] # return only the second tuple part

def allTagValues(tagSpec):
    """Return all tag values in the db for the given tag."""
    return query("SELECT value FROM tag_{}".format(tagsModule.get(tagSpec).name)).getSingleColumn()
    
def addTag(elids,tagSpec,value,recursive=False):
    """Add an entry 'tag=value' into the tags-table. If necessary the value is inserted into the correct tagvalue-table."""
    addTagById(elids,tagSpec,idFromValue(tagSpec,value,insert=True),recursive)
    
def addTagById(elids,tagSpec,valueId,recursive=False):
    tag = tagsModule.get(tagSpec)
    logger.debug("I will {}add value-id {} in tag {} to: {}"
                    .format("recursively " if recursive else "",valueId,tag.name,elids))
    if isinstance(elids,int): # Just one element
        elids = (elids,)
    elif len(elids) == 0:
        return
        
    function = lambda id: query("INSERT IGNORE INTO tags(element_id,tag_id,value_id) VALUES (?,?,?)",id,tag.id,valueId)
    if recursive:
        _mapRecursively(elids,function,[])
    else:
        for id in elids:
            function(id)

def removeTag(elids,tagSpec,value,recursive=False):
    removeTagById(elids,tagSpec,idFromValue(tagSpec,value),recursive)
    
def removeTagById(elids,tagSpec,valueId,recursive=False):
    tag = tagsModule.get(tagSpec)
    logger.debug("I will {}remove value-id {} in tag {} from: {}"
                    .format("recursively " if recursive else "",valueId,tag.name,elids))
    if isinstance(elids,int): # Just one element
        elids = (elids,)
    elif len(elids) == 0:
        return
        
    function = lambda id: query("DELETE FROM tags WHERE element_id=? AND tag_id=? AND value_id=?",id,tag.id,valueId)
    if recursive:
        _mapRecursively(elids,function,[])
    else:
        for id in elids:
            function(id)

def setTags(id,tags,append=False):
    """Set the tags of the element with the given id to the supplied tags, which is a tags.Storage object.
    
    If the optional parameter append is set to True, existing tags won't be touched, instead the 
    given ones will be added. This function will not check for duplicates in that case."""
    
    existingTags = db.query("SELECT * FROM tags WHERE element_id=?;",id)
    
    if len(existingTags) > 0 and not append:
        logger.warning("Deleting existing tags from container {0}".format(id))
        query("DELETE FROM tags WHERE element_id=?;",id)
    
    for tag in tags.keys():
        if tag.isIndexed():
            for value in tags[tag]:
                addTag(id,tag,value)

# Help methods
#=================================================
def _encodeValue(tagType,value):
    if tagType != tagsModule.TYPE_DATE:
        return value
    elif isinstance(value,FlexiDate):
        return value.SQLformat()
    else: return FlexiDate.strptime(value).SQLformat()

def _mapRecursively(ids,function,seenIds):
    for id in ids:
        if id not in seenIds:
            function(id)
            seenIds.append(id)
            _mapRecursively(contents(id),function,seenIds)
