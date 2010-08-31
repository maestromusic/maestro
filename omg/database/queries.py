# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""This module encapsulate common SQL queries in inside handy function calls."""


import omg.database as database
import omg.database.sql
import logging
import omg.tags as tags

logger = logging.getLogger("database.queries")


def idFromFilename(filename):
    """Retrieves the element_id of a file from the given path, or None if it is not found."""
    try:
        return database.get().query("SELECT element_id FROM files WHERE path=?;", filename).getSingle()
    except omg.database.sql.DBException:
        return None

def idFromHash(hash):
    """Retrieves the element_id of a file from its hash, or None if it is not found."""
    result =  database.db.query("SELECT element_id FROM files WHERE hash=?;", hash)
    if len(result)==1:
        return result.getSingle()
    elif len(result)==0:
        return None
    else:
        raise RuntimeError("Hash not unique upon filenames!")
    
def addContent(containerId, i, contentId):
    """Adds new content to a container in the database.
    
    The file with given contentId will be the i-th element of the container with containerId. May throw
    an exception if this container already has an element with the given fileId."""
    database.get().query('INSERT INTO contents VALUES(?,?,?);', containerId, i, contentId)
    
def addTag(cid, tag, value):
    """Add an entry 'tag=value' into the tags-table."""
    database.get().query("INSERT INTO tags VALUES(?,?,?);", cid, tag.id, tag.getValueId(value, insert=True))
       
def setTags(cid, tags, append=False):
    """Set the tags of container with id <cid> to the supplied tags, which is a tags.Storage object.
    
    If the optional parameter append is set to True, existing tags won't be touched, instead the 
    given ones will be added. This function will not check for duplicates in that case."""
    
    db = database.get()
    existingTags = db.query("SELECT * FROM tags WHERE 'element_id'=?;", cid)
    
    if len(existingTags) > 0 and not append:
        logger.warning("Deleting existing tags from container {0}".format(cid))
        db.query("DELETE FROM tags WHERE 'element_id'=?;", cid)
    
    for tag in tags.keys():
        for value in tags[tag]:
            addTag(cid, tag, value)
 
def addContainer(name, tags = None, elements = 0, toplevel = False):
    """Adds a container to the database, which can have tags and a number of elements."""
    
    if toplevel:
        top = '1'
    else:
        top = '0'
    result = database.get().query("INSERT INTO elements (name,elements,toplevel) VALUES(?,?,?);", name,elements,top)
    newid = result.insertId() # the new container's ID
    if tags:
        setTags(newid, tags)
    return newid

def delContainer(cid):
    """Removes a container together with all of its content and tag references from the database.
    
    If the content is a file, also deletes its entry from the files table."""
    db = database.get()
    db.query("DELETE FROM tags WHERE element_id=?;", cid) # delete tag references
    db.query("DELETE FROM contents WHERE container_id=? OR element_id=?;",cid,cid) # delete content relations
    db.query("DELETE FROM files WHERE element_id=?;",cid) # delete file entry, if present
    db.query("DELETE FROM elements WHERE id=?;",cid) # remove container itself

def delFile(path=None,hash=None,id=None):
    """Deletes a file from the database, either by path, hash or id."""
    
    if id:
        return delContainer(id)
    elif path:
        return delContainer(idFromFilename(path))
    elif hash:
        return delContainer(idFromHash(path))
    else:
        raise ValueError("One of the arguments must be set.")
