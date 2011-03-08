#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation

"""
Package that contains methods to create the database, connect to it, check its integrity and even perform some corrections.

The easiest way to use this package is:

import database
db = database.connect()
db.query(...)

or, if the connection was already established in another module:

import database
db = database.get()
db.query(...)
"""

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

def connect(driver=None):
    """Connect to the database server with information from the config file. Usually the driver specified in the config file is used, but you can use the <driver>-parameter to use another one."""
    global db
    if db is None:
        if driver is None:
            driver = options.database.driver
        db = sql.newConnection(driver)
        db.connect(*[options.database.__getattr__(key) for key in ("mysql_user","mysql_password","mysql_db","mysql_host","mysql_port")])
        logger.info("Database connection is open.")
    else: logger.warning("database.connect has been called although the database connection was already open")
    return db

def get():
    """Return the database connection object or None if the connection has not yet been opened."""
    return db

def resetDatabase(tagConfiguration):
    """Drop all tables and create them without data again. All table rows will be lost! To determine which tag tables have to be created the string <tagConfiguration> is used. For its syntax confer tags.parseTagConfiguration."""
    from . import tables
    from omg import tags
    
    # First we have to reset the tagids-table...
    tables.tables['tagids'].reset()
    for tagname,tagtype in tags.parseTagConfiguration(tagConfiguration).items():
        db.query("INSERT INTO tagids (tagname,tagtype) VALUES (?,?)",tagname,tagtype)
    # ...which is necessary to compute the list of all tables
    for name,table in tables.allTables().items():
        if name != 'tagids':
            table.reset()
    # Finally remove superfluous tables
    checkSuperfluousTables(True)

def listTables():
    """Return a list of all tables in the database."""
    return list(db.query("SHOW TABLES").getSingleColumn())
    
def getCheckMethods():
    """Return all methods of this module that check the database in a dictionary using the method names as keys."""
    import types, sys
    module = sys.modules[globals()['__name__']]
    return {k:v for k,v in module.__dict__.items() if type(v) is types.FunctionType and k.startswith("check")}

def checkElementCounters(fix=False):
    """Search elements.elements for wrong entries and corrects them if fix is true. Return the number of wrong entries."""
    if "elements" not in listTables():
        return 0
        
    if fix:
        return db.query("UPDATE elements \
                         SET elements = (SELECT COUNT(*) FROM contents WHERE container_id = id)").affectedRows()
    else:
        return db.query("SELECT COUNT(*) FROM elements \
                           WHERE elements != (SELECT COUNT(*) FROM contents WHERE container_id = id)").getSingle()

def checkFileFlags(fix=False):
    """Return the number of wrong entries in elements.files and correct them if <fix> is True."""
    if "elements" not in listTables():
        return 0
    if fix:
        return db.query("UPDATE elements SET file = (id IN (SELECT element_id FROM files))").affectedRows()
    else: return db.query("SELECT COUNT(*) FROM elements WHERE file != (id IN (SELECT element_id FROM files))").getSingle()
    
def checkTopLevelFlags(fix=False):
    """Search elements.toplevel for wrong entries and corrects them if <fix> is True. Return the number of wrong entries."""
    if "elements" not in listTables():
        return 0
    
    if fix:
        return db.query("UPDATE elements SET toplevel = (NOT id IN (SELECT element_id FROM contents))").affectedRows()
    else: return db.query("SELECT COUNT(*) FROM elements \
                           WHERE toplevel != (NOT id IN (SELECT element_id FROM contents))").getSingle()

def checkMissingTables(fix=False):
    """Search the database for missing tables and create them if fix is true. Return a list of the missing tables."""
    from . import tables
    missingTables = filter(lambda t: not t.exists(),tables.allTables().values())
    if fix:
        for table in missingTables:
            table.create()
    return [table.name for table in missingTables]
    
def checkSuperfluousTables(fix=False):
    """Search the database for tables which are not used by this program (this may depend on the installed plugins) and return them as a list. If fix is true delete these tables. All table rows will be lost!"""
    from . import tables
    superfluousTables = filter(lambda t: t not in tables.allTables().keys(),listTables())
    if fix:
        for table in superfluousTables:
            db.query("DROP TABLE {0}".format(table))
    return list(superfluousTables)

def _checkForeignKey(fix,table,key,refTable,refKey,additionalWhereClause = None):
    """Check whether each value in <table>.<key> is also contained in <refTable>.<refKey> and return the number of broken entries. If <fix> is true delete those entries from the database. <additionalWhereClause> may be given to check only some of the rows of <table>."""
    if additionalWhereClause is None:
        whereClause = "{0} NOT IN (SELECT {1} FROM {2})".format(key,refKey,refTable)
    else: whereClause = "{0} AND {1} NOT IN (SELECT {2} FROM {3})".format(additionalWhereClause,key,refKey,refTable)
    
    if fix:
        return db.query("DELETE FROM {0} WHERE {1}".format(table,whereClause)).affectedRows()
    else: return db.query("SELECT COUNT(*) FROM {0} WHERE {1}".format(table,whereClause)).getSingle()
    
def checkForeignKeys(fix=False):
    """Check foreign key constraints in the database.
    
     As the current MySQL doesn't support foreign key constraints by itself (at least not in MyISAM), this method checks manually all such constraints. A foreign key is a column which values must be contained in another column in another table (the referenced table). For example: Every container_id-value in the contents-table must have a corresponding entry in the elements-table. This method returns a dictionary mapping (tablename,keycolumn) to the number of broken entries (e.g. (contents,container_id):4 to indicate that 4 rows of contents.container_id are not in the elements-table)."""
    tables = listTables()
    # In a first step we check all foreign keys except for tag_id in the tags-tables.
    # Argument sets to use with _checkForeignKey
    foreignKeys = [("contents","container_id","elements","id"),
                   ("contents","element_id","elements","id"),
                   ("files","element_id","elements","id"),
                   ("tags","element_id","elements","id"),
                   ("tags","tag_id","tagids","id")
                  ]
    # Remove entries where table or refTable does not exist
    foreignKeys = filter(lambda x: x[0] in tables and x[2] in tables,foreignKeys)
    
    # Apply _check_foreign_key to each set of arguments and store the result in a dictionary
    brokenEntries = {(args[0],args[1]): _checkForeignKey(fix,*args) for args in foreignKeys}
    
    # In the second step we check that the tag_ids in the tags-tables are in the corresponding tag-table.
    if "tagids" in tables and "tags" in tables:
        brokenEntries[("tags","tag_id")] = 0
        for tagid,tagname in db.query("SELECT id,tagname FROM tagids"):
            tablename = "tag_{0}".format(tagname)
            if tablename not in tables: # If something's wrong with the tagids-table, tablename may not exist
                continue
            # Use the additionalWhereClause-argument to check only the tags corresponding to tag_id because there is a different refTable for each tag_id.
            brokenEntries[("tags","tag_id")] = _checkForeignKey(fix,"tags","value_id",tablename,"id",
                                                                "tag_id={0}".format(tagid))
    # Remove tables where zero broken entries were found
    return {k:v for k,v in brokenEntries.items() if v != 0}

def checkEmptyContainers(fix=False):
    """Return the number of empty elements which are NOT files and delete them if fix is true. These are usually there because of a crash in populate. This method uses elements.elements so you might have to use checkElementCounters before using it."""
    tables = list(db.query("SHOW TABLES").getSingleColumn())
    if "elements" not in listTables() or "files" not in listTables():
        return 0
    if fix:
        return db.query("DELETE FROM elements WHERE elements=0 \
                         AND NOT id IN (SELECT element_id FROM files)").affectedRows()
    else: return db.query("SELECT COUNT(*) FROM elements WHERE elements=0 \
                           AND NOT id IN (SELECT element_id FROM files)").getSingle()

def checkSuperfluousTags(fix=False):
    """Search the tag_*-tables for values that are never used in the tags-table. If fix is true delete these entries. Return a dictionary mapping tagnames to the number of superfluous tags with this name (but only where this number is positive)."""
    if "tagids" not in listTables():
        return {}
    result = {}
    for tagid,tagname in db.query("SELECT id,tagname FROM tagids"):
        tablename = "tag_{0}".format(tagname)
        if tablename not in listTables(): # If something's wrong with the tagids-table, tablename may not exist
            continue
        if fix:
            result[tagname] = db.query("DELETE FROM {0} \
                                        WHERE id NOT IN (SELECT value_id FROM tags WHERE tag_id = ?)"
                                        .format(tablename),tagid).affectedRows()
        else:
            result[tagname] = db.query("SELECT COUNT(*) FROM {0} \
                                        WHERE id NOT IN (SELECT value_id FROM tags WHERE tag_id = ?)"
                                        .format(tablename),tagid).getSingle()
    return {k:v for k,v in result.items() if v > 0}
