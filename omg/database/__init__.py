#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation

"""
The database module provides an abstraction layer to several Python-MySQL connectors. Furthermore it contains methods to extract information about the database, check its integrity and correct minor errors.

The actual database drivers which connect to the database using a third party connector are found in the :mod:`SQL package <omg.database.sql>`. The definitions of Omg's tables are found in the :mod:`tables-module <omg.database.tables>`.

The easiest way to use this package is::

    import database
    db = database.connect()
    db.query(...)

or, if the connection was already established in another module::

    import database
    db = database.get()
    db.query(...)

\ """

import logging
from omg import strutils
from omg.config import options
from . import sql


class DBLayoutException(Exception):
    """Exception that occurs if the existing database layout doesn't meet the requirements."""

# Database connection object
db = None

# Logger for database warnings
logger = logging.getLogger("omg.database")

def connect():
    """Connect to the database server with information from the config file. The drivers specified in ``options.database.drivers`` are tried in the given order."""
    global db
    if db is None:
        db = sql.newConnection(options.database.drivers)
        db.connect(*[options.database.__getattr__(key) for key in
                     ("mysql_user","mysql_password","mysql_db","mysql_host","mysql_port")])
        logger.info("Database connection is open.")
    else: logger.warning("database.connect has been called although the database connection was already open")
    return db

def get():
    """Return the database connection object or None if the connection has not yet been opened."""
    return db

def resetDatabase():
    """Drop all tables and create them without data again. All table rows will be lost!"""
    from . import tables
    for table in tables.tables:
        table.reset()

def listTables():
    """Return a list of all tables in the database."""
    return list(db.query("SHOW TABLES").getSingleColumn())
    
def getCheckMethods():
    """Return all methods of this module that check the database in a dictionary using the method names as keys."""
    import types, sys
    module = sys.modules[globals()['__name__']]
    return {k:v for k,v in module.__dict__.items() if type(v) is types.FunctionType and k.startswith("check")}

def checkElementCounters(fix=False):
    """Search elements.elements for wrong entries and correct them if *fix* is true. Return the number of wrong entries."""
    if "elements" not in listTables():
        return 0
        
    if fix:
        return db.query("UPDATE elements \
                         SET elements = (SELECT COUNT(*) FROM contents WHERE container_id = id)").affectedRows()
    else:
        return db.query("SELECT COUNT(*) FROM elements \
                           WHERE elements != (SELECT COUNT(*) FROM contents WHERE container_id = id)").getSingle()

def checkFileFlags(fix=False):
    """Return the number of wrong entries in elements.file and correct them if *fix* is True."""
    if "elements" not in listTables():
        return 0
    if fix:
        return db.query("UPDATE elements SET file = (id IN (SELECT element_id FROM files))").affectedRows()
    else: return db.query("SELECT COUNT(*) FROM elements WHERE file != (id IN (SELECT element_id FROM files))").getSingle()
    
def checkTopLevelFlags(fix=False):
    """Search elements.toplevel for wrong entries and correct them if *fix* is True. Return the number of wrong entries."""
    if "elements" not in listTables():
        return 0
    
    if fix:
        return db.query("UPDATE elements SET toplevel = (NOT id IN (SELECT element_id FROM contents))").affectedRows()
    else: return db.query("SELECT COUNT(*) FROM elements \
                           WHERE toplevel != (NOT id IN (SELECT element_id FROM contents))").getSingle()

def checkMissingTables(fix=False):
    """Search the database for missing tables and create them if fix is true. Return a list of the missing tables."""
    from . import tables
    missingTables = filter(lambda t: not t.exists(),tables.tables)
    if fix:
        for table in missingTables:
            table.create()
    return [table.name for table in missingTables]
    
def checkSuperfluousTables(fix=False):
    """Search the database for tables which are not used by this program (this may depend on the installed plugins) and return them as a list. If *fix* is true delete these tables. All table rows will be lost!"""
    from . import tables
    tableNames = [table.name for table in tables.tables]
    superfluousTables = list(filter(lambda t: t not in tableNames,listTables()))
    if fix:
        for table in superfluousTables:
            db.query("DROP TABLE {0}".format(table))
    return superfluousTables

def checkValueIds(fix=False):
    """Search for rows in tags whose value_id does not exist in the corresponding value_*-table. If *fix* is true, remove those rows. Return a dictionary mapping tagnames to the number of broken rows (only if nonzero)."""
    if not "tagids" in listTables():
        return None
    result = db.query("SELECT id,tagname,tagtype FROM tagids")
    brokenEntries = {}
    for id,name,type in result:
        if fix:
            result2 = db.query("""
                DELETE FROM tags
                WHERE tag_id = ? AND NOT value_id IN (SELECT id FROM values_{} WHERE tag_id=?)
                """.format(type),id,id)
            brokenEntries[name] = result2.affectedRows()
        else:
            brokenEntries[name] = db.query("""
                    SELECT COUNT(*)
                    FROM tags 
                    WHERE tag_id = ? AND NOT value_id IN (SELECT id FROM values_{} WHERE tag_id=?)
                    """.format(type),id,id).getSingle()
    return {k:v for k,v in brokenEntries.items() if v > 0}

def checkEmptyContainers(fix=False):
    """Return the number of empty elements which are NOT files and delete them if *fix* is true. These are usually there because of a crash in the populate code. This method uses elements.elements so you might have to use checkElementCounters before using it."""
    if "elements" not in listTables() or "files" not in listTables():
        return 0
    if fix:
        return db.query("DELETE FROM elements WHERE elements=0 \
                         AND NOT id IN (SELECT element_id FROM files)").affectedRows()
    else: return db.query("SELECT COUNT(*) FROM elements WHERE elements=0 \
                           AND NOT id IN (SELECT element_id FROM files)").getSingle()

def checkSuperfluousTags(fix=False):
    """Search the values_*-tables for values that are never used in the tags-table. If *fix* is true, delete these entries. Return a dictionary mapping names to the number of superfluous tags with this name (but only where this number is positive)."""
    result = {}
    for id,name,type in db.query("SELECT id,tagname,tagtype FROM tagids"):
        tablename = "values_{0}".format(type)
        if tablename not in listTables(): # If something's wrong with the tagids-table, tablename may not exist
            continue
        if fix:
            result[name] = db.query("DELETE FROM {} \
                                     WHERE tag_id=? AND id NOT IN (SELECT value_id FROM tags WHERE tag_id = ?)"
                                        .format(tablename),id,id).affectedRows()
        else:
            result[name] = db.query("SELECT COUNT(*) FROM {0} \
                                     WHERE tag_id=? AND id NOT IN (SELECT value_id FROM tags WHERE tag_id = ?)"
                                        .format(tablename),id,id).getSingle()
    return {k:v for k,v in result.items() if v > 0}
