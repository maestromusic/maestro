# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""This module encapsulate common SQL queries in inside handy function calls."""

import logging

from omg import db, tags
import omg.database.sql

logger = logging.getLogger("database.queries")

    
def addContent(containerId, i, contentId):
    """Adds new content to a container in the database.
    
    The file with given contentId will be the i-th element of the container with containerId. May throw
    an exception if this container already has an element with the given fileId."""
    db.query('INSERT INTO contents VALUES(?,?,?);', containerId, i, contentId)

def delContents(containerId):
    """Deletes all contents relations where containerId is the parent."""
    db.query("DELETE FROM contents WHERE container_id=?;", containerId) 
    
def setTags(cid, tags, append=False):
    """Set the tags of container with id <cid> to the supplied tags, which is a tags.Storage object.
    
    If the optional parameter append is set to True, existing tags won't be touched, instead the 
    given ones will be added. This function will not check for duplicates in that case."""
    
    existingTags = db.query("SELECT * FROM tags WHERE element_id=?;", cid)
    
    if len(existingTags) > 0 and not append:
        logger.warning("Deleting existing tags from container {0}".format(cid))
        db.query("DELETE FROM tags WHERE element_id=?;", cid)
    
    for tag in tags.keys():
        if tag.isIndexed():
            for value in tags[tag]:
                db.addTag(cid, tag, value)
 
def addContainer(name, tags = None, file = False, elements = 0, toplevel = False):
    """Adds a container to the database, which can have tags and a number of elements."""
    
    if toplevel:
        top = '1'
    else:
        top = '0'
    if file:
        file = '1'
    else:
        file = '0'
    result = db.query("INSERT INTO elements (name,file,toplevel,elements) VALUES(?,?,?,?);", name, file, top, elements)
    newid = result.insertId() # the new container's ID
    if tags:
        setTags(newid, tags)
    return newid

def delContainer(cid):
    """Removes a container together with all of its content and tag references from the database.
    
    If the container is a file, also deletes its entry from the files table."""
    db.query("DELETE FROM tags WHERE element_id=?;", cid) # delete tag references
    db.query("DELETE FROM contents WHERE container_id=? OR element_id=?;",cid,cid) # delete content relations
    db.query("DELETE FROM files WHERE element_id=?;",cid) # delete file entry, if present
    db.query("DELETE FROM elements WHERE id=?;",cid) # remove container itself

def delFile(path=None,hash=None,id=None):
    """Deletes a file from the database, either by path, hash or id."""
    
    if id:
        return delContainer(id)
    elif path:
        return delContainer(db.idFromPath(path))
    elif hash:
        return delContainer(db.idFromHash(path))
    else:
        raise ValueError("One of the arguments must be set.")

def updateElementCounter(containerId):
    """Sets the element conuter of given containerId to the correct number."""
    db.query('UPDATE elements SET elements = (SELECT COUNT(*) FROM contents WHERE container_id = ?) WHERE id = ?', containerId, containerId)
