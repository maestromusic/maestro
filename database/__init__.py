#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
# The database-package contains methods to create the database, connect to it, check its
# integrity and perform some minor corrections.
#
# The easiest way to use this package is:
# import database
# db = database.connect()
#
import config
import logging
from . import sql

class DBLayoutException(Exception):
    """Exception that occurs if the existing database layout doesn't meet the requirements."""

# Database connection object
db = None

# Logger for database warnings
logger = logging.getLogger("database")

def connect():
    """Connects to the database server with information from the config file."""
    global db
    db = sql.newConnection(config.get("database","driver"))
    db.connect(*[config.get("database",key) for key in ("mysql_user","mysql_password","mysql_db","mysql_host","mysql_port")])
    logger.debug("Database connection is open.")
    return db
    
def resetDatabase():
    """Drops all tables and creates them without data again. All table rows will be lost!"""
    from . import tables
    for table in tables.tables.values():
        table.reset()

def listTables():
    """Returns a list of all tables in the database."""
    return list(db.query("SHOW TABLES").getSingleColumn())
    
def getCheckMethods():
    """Returns all methods of this module that check the database."""
    import types, sys
    module = sys.modules[globals()['__name__']]
    return {k:v for k,v in module.__dict__.items() if type(v) is types.FunctionType and k.startswith("check")}

def checkElementCounters(fix=False):
    """Searches containers.elements for wrong entries and corrects them if fix is true. The number of wrong entries is returned."""
    if fix:
        return db.query("UPDATE containers \
                         SET elements = (SELECT COUNT(*) FROM contents WHERE container_id = id)").affectedRows()
    else: return db.query("SELECT COUNT(*) FROM containers \
                           WHERE elements != (SELECT COUNT(*) FROM contents WHERE container_id = id)").getSingle()
    
def checkTagIds(fix=False):
    """Compares the tagids-table with the 'indexed-tags'-option from the config-file and returns a tuple with two lists. The first list contains the tags which are in only the config-file, the second one contains the tags which are only in the tagids-table. If fix is true the tagids-table is corrected to contain exactly the tags from the config-file."""
    from . import tables
    if "tagids" not in listTables():
        return 0
    tags = _parseIndexedTags()
    existingTags = set(db.query("SELECT tagname FROM tagids").getSingleColumn())
    necessaryTags = set(tags.keys())
    missingTags = necessaryTags - existingTags
    superfluousTags = existingTags - necessaryTags
    if fix:
        for tag in superfluousTags:
            db.query("DELETE FROM tagids WHERE tagname = ?",tag)
        for tag in missingTags:
            db.query("INSERT INTO tagids(tagname,tagtype) VALUES(?,?)",tag,tags[tag])
    return (missingTags,superfluousTags)
    
def checkMissingTables(fix=False):
    """Searches the database for missing tables and creates them if fix is true. Returns a list of the missing tables."""
    from . import tables
    missingTables = filter(lambda t: not t.exists(),tables.tables.values())
    if fix:
        for table in missingTables:
            table.create()
    return [table.name for table in missingTables]
    
def checkSuperfluousTables(fix=False):
    """Searches the database for tables which are not used by this program (this depends on the config-file option 'indexed_tags' and on the installed plugins) and returns them as a list. If fix is true these tables are deleted. All table rows will be lost!"""
    from . import tables
    superfluousTables = filter(lambda t: t not in tables.tables.keys(),listTables())
    if fix:
        for table in superfluousTables:
            db.query("DROP TABLE {0}".format(table))
    return superfluousTables

def _checkForeignKey(fix,table,key,refTable,refKey,additionalWhereClause = None):
    """Checks whether each value in <table>.<key> is also contained in <refTable>.<refKey> and returns the number of broken entries. If fix is true those entries are also deleted from the database. <additionalWhereClause> may be given to check only some of the rows of <table>."""
    if additionalWhereClause == None:
        whereClause = "{0} NOT IN (SELECT {1} FROM {2})".format(key,refKey,refTable)
    else: whereClause = "{0} AND {1} NOT IN (SELECT {2} FROM {3})".format(additionalWhereClause,key,refKey,refTable)
    
    if fix:
        return db.query("DELETE FROM {0} WHERE {1}".format(table,whereClause)).affectedRows()
    else: return db.query("SELECT COUNT(*) FROM {0} WHERE {1}".format(table,whereClause)).size()
    
def checkForeignKeys(fix=False):
    """Checks foreign key constraints in the database as the current MySQL doesn't support such constraints by itself (at least not in MyISAM). A foreign key is a column which values must be contained in another column in another table (the referenced table). For example: Every container_id-value in the contents-table must have a corresponding entry in the container-table. This method returns a dictionary mapping (tablename,keycolumn) to the number of broken entries (e.g. (contents,container_id):4 to indicate that 4 rows of contents.container_id are not in the container-table)."""
    tables = listTables()
    # In a first step we check all foreign keys except for tag_id in the tags-tables.
    # Argument sets to use with _checkForeignKey
    foreignKeys = [("contents","container_id","containers","id"),
                   ("contents","element_id","containers","id"),
                   ("files","container_id","containers","id"),
                   ("othertags","container_id","containers","id"),
                   ("tags","container_id","containers","id"),
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
    # Remove tables where zero broken entries where found
    return {k:v for k,v in brokenEntries.items() if v != 0}


def checkEmptyContainers(fix=False):
    """Returns the number of empty containers which are NOT files and deletes them if fix is true. These are usually there because of a crash in populate. This method uses containers.elements so you might have to use checkElementCounters before using it."""
    tables = list(db.query("SHOW TABLES").getSingleColumn())
    if "containers" not in listTables() or "files" not in listTables():
        return 0
    if fix:
        return db.query("DELETE FROM containers WHERE elements=0 \
                        AND NOT id IN (SELECT container_id FROM files)").affectedRows()
    else: return db.query("SELECT COUNT(*) FROM containers WHERE elements=0 \
                           AND NOT id IN (SELECT container_id FROM files)").getSingle()

def checkSuperfluousTags(fix=False):
    """Searches the tag_*-tables for values that are never used in the tags-table. If fix is true these entries are deleted."""
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
    
    
# TODO:
# The following code actually doesn't belong to this module.
def _parseIndexedTags():
    """Parses the given string. This option should contain a comma-separated list of strings of the form tagname(tagtype) where the part in brackets is optional and defaults to 'varchar'. It checks whether the syntax is correct and all types have a corresponding CREATE_TAG_TABLE_CMDS-command and returns a dictionary {tagname : tagtype}. Otherwise an exception is raised."""
    import re
    string = config.get("tags","indexed_tags")
    # Matches strings like "   tagname (   tagtype   )   " (the part in brackets is optional) and stores the interesting parts in the first and third group.
    prog = re.compile('\s*(\w+)\s*(\(\s*(\w*)\s*\))?\s*$')
    tags = {}
    for tagstring in string.split(","):
        result = prog.match(tagstring)
        if result == None:
            raise Exception("Invalid syntax in the indexed_tags-option of the config-file ('{0}').".format(tagstring))
        tagname = result.groups()[0]
        tagtype = result.groups()[2]
        if not tagtype:
            tagtype = "varchar"
        tags[tagname] = tagtype
    return tags