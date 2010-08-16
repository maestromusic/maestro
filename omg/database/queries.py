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
    """Retrieves the container_id of a file from the given path, or None if it is not found."""
    try:
        return database.get().query("SELECT container_id FROM files WHERE path=?;", filename).getSingle()
    except omg.database.sql.DBException:
        return None
    
def addContent(containerId, i, contentId):
    """Adds new content to a container in the database.
    
    The file with given contentId will be the i-th element of the container with containerId. May throw
    an exception if this container already has an element with the given fileId."""
    database.get().query('INSERT INTO contents VALUES(?,?,?);', containerId, i, contentId)
    
def addTag(cid, tag, value):
    """Add an entry 'tag=value' into the tags or othertags table (depending of the type of tag)"""
    
    db = database.get()
    if isinstance(tag, tags.IndexedTag):
        db.query("INSERT INTO tags VALUES(?,?,?);", cid, tag.id, tag.getValueId(value, insert=True))
    elif isinstance(tag, tags.OtherTag):
        db.query("INSERT INTO othertags VALUES(?,?,?);", cid, tag.name, value)
       
def setTags(cid, tags, append=False):
    """Sets the tags of container with id <cid> to the supplied tags, which is a tags.Storage object.
    
    If the optional parameter append is set to True, existing tags won't be touched, instead the 
    given ones will be added. This function will not check for duplicates in that case."""
    
    db = database.get()
    existingTags = db.query("SELECT * FROM tags WHERE 'container_id'=?;", cid)
    
    if len(existingTags) > 0 and not append:
        logger.warning("Deleting existing indexed tags from container {0}".format(cid))
        db.query("DELETE FROM tags WHERE 'container_id'=?;", cid)
        
    existing_othertags = db.query("SELECT * FROM othertags WHERE 'container_id'=?;",cid)
    if len(existing_othertags) > 0 and not append:
        logger.warning("Deleting existing othertags from container {0}".format(cid))
        database.db.query("DELETE FROM othertags WHERE 'container_id'=?;", cid)
    
    for tag in tags.keys():
        for value in tags[tag]:
            addTag(cid, tag, value)
 
def addContainer(name, tags = None, elements = 0):
    """Adds a container to the database, which can have tags and a number of elements."""
    result = database.get().query("INSERT INTO containers (name,elements) VALUES(?,?);", name,elements)
    newid = result.insertId() # the new container's ID
    if tags:
        setTags(newid, tags)
    return newid