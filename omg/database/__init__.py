#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation

"""
The database module establishes the database connection and provides many functions to fetch data.

The actual database drivers which connect to the database using a third party connector can be found in the :mod:`SQL package <omg.database.sql>`. The definitions of OMG's tables can be found in the :mod:`tables-module <omg.database.tables>`.

The easiest way to use this package is::

    from omg import database as db
    db.connect()
    db.query(...)

or, if the connection was already established in another module::

    from omg import database as db
    db.query(...)


Threading
========================================================================
Each thread must have its own connection object. This module stores all connection objects and methods like ``query`` automatically choose the correct connection. However you have to initialize the connection for each thread and use a ``with`` statement to ensure the connection is finally closed again. Typically the ``run``-method of your thread will look like this::

    from omg import database as db
    
    class MyThread(threading.Thread):
        def run(self):
            with db.connect():
                # Do stuff in your thread and use the database module as usual:
                db.query(...) # These methods will use the connection of your thread
                db.tags(...)
            # Finally the thread's connection is closed by the context manager

\ """

import sys, threading

from omg import strutils, config, logging, utils
from . import sql

# Table prefix
prefix = None

# Logger for database warnings
logger = logging.getLogger("omg.database")

# Each thread must have its own connection object. This maps thread identifiers to the connection object
connections = {}


# Connection and maintenance methods
#=======================================================================
class ConnectionContextManager:
    """Connection manager that ensures that connections in threads other than the main thread are closed and removed from the dict ``connections`` when the thread terminates."""
    def __enter__(self):
        return None

    def __exit__(self,exc_type, exc_value, traceback):
        close()
        return False # If the suite was stopped by an exception, don't stop that exception


def connect():
    """Connect to the database server with information from the config file. The drivers specified in ``config.options.database.drivers`` are tried in the given order. This method must be called exactly once for each thread that wishes to access the database. It returns a :class:`ConnectionContextManager` that will automatically close the connection if used in a ``with`` statement."""
    threadId = threading.current_thread().ident
    if threadId in connections:
        logger.warning("database.connect has been called although a connection for this thread was already open.")
        return connections[threadId]

    global prefix
    if prefix is None:
        prefix = config.options.database.prefix
    authValues = [config.options.database["mysql_"+key] for key in sql.AUTH_OPTIONS]
    return _connect(config.options.database.drivers,authValues)
        

def testConnect(driver=None):
    """Connect to the database server using the test connection information (config.options.database.test_*). If any of these options is empty, the standard option will be used instead (config.options.database.mysql_*). The table prefix will in be config.options.database.test_prefix even if it is empty. For safety this method will abort the program if prefix, db-name and host coincide with the standard values used by connect.

    As :func:`connect`, this method returns a :class:`ConnectionContextManager`."""
    threadId = threading.current_thread().ident
    if threadId in connections:
        logger.warning("database.testConnect has been called although a connection for this thread was already open.")
        return connections[threadId]
        
    authValues = []
    host = None
    dbName = None
    for option in sql.AUTH_OPTIONS:
        value = config.options.database["test_"+option]
        if not value: # Replace empty values by standard values
            value = config.options.database["mysql_"+option]
        authValues.append(value)
        if option == "host":
            host = value
        if option == "db":
            dbName = value

    global prefix
    if prefix is None:
        prefix = config.options.database.test_prefix

    # Abort if the connection information and the prefix is equal
    if (prefix == config.options.database.prefix
            and dbName == config.options.database.mysql_db
            and host == config.options.database.mysql_host):
        logger.critical("Safety stop: Test database connection information coincides with the usual information. Please supply at least a different prefix.")
        sys.exit(1)

    if driver is not None:
        drivers = [driver]
    else: drivers = config.options.database.drivers
    return _connect(drivers,authValues)


def _connect(drivers,authValues):
    try:
        connection = sql.newConnection(drivers)
        connection.connect(*authValues)
        connections[threading.current_thread().ident] = connection
        return ConnectionContextManager()
    except sql.DBException as e:
        logger.error("I cannot connect to the database. Did you provide the correct information in the config file? MySQL error: {}".format(e.message))
        sys.exit(1)
    

def close():
    """Close the database connection of this thread. If you use the context manager returned by :func:`connect`, this method is called automatically."""
    threadId = threading.current_thread().ident
    connection = connections[threading.current_thread().ident]
    del connections[threading.current_thread().ident]
    connection.close()
    
    
def resetDatabase():
    """Drop all tables and create them without data again. All table rows will be lost!"""
    from . import tables
    # Some tables are referenced by other tables and must therefore be dropped last and created first
    referencedTables = [table for table in tables.tables if table.name in
        [prefix+"elements",prefix+"tagids",prefix+"flag_names"]]
    otherTables = [table for table in tables.tables if table not in referencedTables]
    for table in otherTables:
        if table.exists():
            query("DROP TABLE {}".format(table.name))
    for table in referencedTables:
        table.reset()
    for table in otherTables:
        table.create()


def listTables():
    """Return a list of all table names in the database."""
    return list(query("SHOW TABLES").getSingleColumn())


# Standard methods which are redirected to this thread's connection object
#=========================================================================
def query(*params):
    try:
        return connections[threading.current_thread().ident].query(*params)
    except KeyError:
        raise RuntimeError("Cannot access database before a connection for this thread has been opened.")

def multiQuery(queryString,args):
    try:
        return connections[threading.current_thread().ident].multiQuery(queryString,args)
    except KeyError:
        raise RuntimeError("Cannot access database before a connection for this thread has been opened.")

def transaction():
    try:
        connections[threading.current_thread().ident].transaction()
    except KeyError:
        raise RuntimeError("Cannot access database before a connection for this thread has been opened.")

def commit():
    try:
        connections[threading.current_thread().ident].commit()
    except KeyError:
        raise RuntimeError("Cannot access database before a connection for this thread has been opened.")

def rollback():
    try:
        connections[threading.current_thread().ident].rollback()
    except KeyError:
        raise RuntimeError("Cannot access database before a connection for this thread has been opened.")

def isNull(value):
    try:
        return connections[threading.current_thread().ident].isNull(value)
    except KeyError:
        raise RuntimeError("Cannot access database before a connection for this thread has been opened.")

        
# contents-table
#=======================================================================
def contents(elids,recursive=False):
    """Return the ids of all children of the elements with ids *elids* as a set. *elids* may be a list of element ids or a single id. If *recursive* is True, all descendants will be included. In any case the result list won't contain duplicates."""
    return _contentsParentsHelper(elids,recursive,"element_id","container_id")

def parents(elids,recursive = False):
    """Return a set containing the ids of all parents of the elements with ids *elids* (which may be a list or a single id). If *recursive* is True all ancestors will be added recursively."""
    return _contentsParentsHelper(elids,recursive,"container_id","element_id")

def _contentsParentsHelper(elids,recursive,selectColumn,whereColumn):
    if isinstance(elids,int):
        newSet = set([elids])
    else: newSet = set(elids)

    resultSet = set()
    while len(newSet) > 0:
        newSet = set(query("""
                SELECT {}
                FROM {}contents
                WHERE {} IN ({})
                """.format(selectColumn,prefix,whereColumn,",".join(str(n) for n in newSet))).getSingleColumn())
        if not recursive:
            return newSet
        newSet = newSet - resultSet
        resultSet = resultSet.union(newSet)

    return(resultSet)


def position(parentId,elementId):
    """Return the position of the element with id *elementId* within the container with id *parentId*. If the element is not contained in the container, a ValueException is raised."""
    try:
        return query("SELECT position FROM {}contents WHERE container_id = ? AND element_id = ?".format(prefix),
                        parentId,elementId).getSingle()
    except sql.EmptyResultException:
        raise ValueError("Element with ID {} is not contained in container {}.".format(elementId,parentId))


# elements-table
#=======================================================================
def isFile(elid):
    """Return whether the element with id <elid> exists and is a file."""
    return query("SELECT file FROM {}elements WHERE id = ?".format(prefix),elid).getSingle() == 1

def isContainer(elid):
    """Return whether the element with id <elid> exists and is a container."""
    return query("SELECT file FROM {}elements WHERE id = ?".format(prefix),elid).getSingle() == 0
    
def isToplevel(elid):
    """Return whether the element with id <elid> exists and is toplevel element."""
    return query("SELECT toplevel FROM {}elements WHERE id = ?".format(prefix),elid).getSingle() == 1
    
def elementCount(elid):
    """Return the number of children of the element with id <elid> or raise an sql.EmptyResultException if that element does not exist."""
    return query("SELECT elements FROM {}elements WHERE id  ?".format(prefix),elid).getSingle()


# Files-Table
#================================================
def path(elid):
    """Return the path of the file with id <elid> or raise an sql.EmptyResultException if that element does not exist.""" 
    return query("SELECT path FROM {}files WHERE element_id=?".format(prefix),fileid).getSingle()

def hash(elid):
    """Return the hash of the file with id <elid> or raise an sql.EmptyResultException if that element does not exist.""" 
    return query("SELECT hash FROM {}files WHERE element_id=?".format(prefix),fileid).getSingle()

def length(elid):
    """Return the length of the file with id <elid> or raise an sql.EmptyResultException if that element does not exist.""" 
    return query("SELECT length FROM {}files WHERE element_id=?".format(prefix),fileid).getSingle()

def verified(elid):
    """Return the verified-timestamp of the file with id <elid> or raise an sql.EmptyResultException if that element does not exist.""" 
    return query("SELECT verified FROM {}files WHERE element_id=?".format(prefix),fileid).getSingle()
    
def idFromPath(path):
    """Return the element_id of a file from the given path or raise an sql.EmptyResultException if that element does not exist.""" 
    try:
        return query("SELECT element_id FROM {}files WHERE path=?".format(prefix),path).getSingle()
    except sql.EmptyResultException:
        return None

def idFromHash(hash):
    """Return the element_id of a file from its hash, or None if it is not found."""
    result = query("SELECT element_id FROM {}files WHERE hash=?".format(prefix),hash)
    if len(result)==1:
        return result.getSingle()
    elif len(result)==0:
        return None
    else: raise RuntimeError("Hash not unique upon filenames!")


# values_* tables
#=======================================================================
def valueFromId(tagSpec,valueId):
    """Return the value from the tag *tagSpec* with id *valueId* or raise an sql.EmptyResultException if that id does not exist. Date tags will be returned as FlexiDate."""
    tag = tagsModule.get(tagSpec)
    value = query("SELECT value FROM {}values_{} WHERE tag_id = ? AND id = ?"
                    .format(prefix,tag.type), tag.id,valueId).getSingle()
    if tag.type == tagsModule.TYPE_DATE:
        value = utils.FlexiDate.fromSql(value)


def idFromValue(tagSpec,value,insert=False):
    """Return the id of the given value in the tagtable of tag *tagSpec*. If the value does not exist, raise an sql.EmptyResultException, unless the optional parameter *insert* is set to True. In that case insert the value into the table and return its id."""
    tag = tagsModule.get(tagSpec)
    value = _encodeValue(tag.type,value)
    try:
        return query("SELECT id FROM {}values_{} WHERE tag_id = ? AND value = ?"
                        .format(prefix,tag.type),tag.id,value).getSingle()
    except sql.EmptyResultException as e:
        if insert:
            result = query("INSERT INTO {}values_{} SET tag_id = ?,value = ?".format(prefix,tag.type),tag.id,value)
            return result.insertId()
        else: raise e


# tags-Table
#=======================================================================
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
                FROM {}tags
                WHERE element_id = {} {}
                """.format(prefix,elid,additionalWhereClause))
    tags = set()
    for tagid,valueid in result:
        tag = tagsModule.get(tagid)
        tags.append((tag,valueFromId(tag,valueid)))
    return tags

def tagValues(elid,tagList):
    """Return all values which the element with id *elid* possesses in any of the tags in tagList (which may be a list of tag-specifiers or simply a single tag-specifier)."""
    return [value for tag,value in tags(elid,tagList)] # return only the second tuple part

def allTagValues(tagSpec):
    """Return all tag values in the db for the given tag."""
    return query("SELECT value FROM tag_{}".format(tagsModule.get(tagSpec).name)).getSingleColumn()
    

# Help methods
#=======================================================================
def _encodeValue(tagType,value):
    if tagType == tagsModule.TYPE_VARCHAR:
        value = str(value)
        if len(value.encode()) > constants.TAG_VARCHAR_LENGTH:
            logger.error("Attempted to encode the following string for a varchar column although its encoded size exceeds constants.TAG_VARCHAR_LENGTH. The string will be truncated. '{}'.".format(value))
        return value
    elif tagType == tagsModule.TYPE_TEXT:
        return str(value)
    elif tagType == tagsModule.TYPE_DATE:
        if isinstance(value,utils.FlexiDate):
            return value.toSql()
        else: return utils.FlexiDate.strptime(value).toSql()
    else: raise ValueError("Unknown tag type '{}'.".format(tagType))
