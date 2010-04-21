#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from omg import database, tags
from . import searchparser
from . import criteria as criteriaModule

# Temporary table used by the search algorithm
TT_HELP = 'tmp_help'

# Logical modes
DISJUNCTION = 1
CONJUNCTION = 2

# Reference to the database connection
db = None

def init():
    """Initialize the search-module."""
    global db
    db = database.get()
    db.query("DROP TABLE IF EXISTS {0}".format(TT_HELP))
    db.query("""
        CREATE TABLE IF NOT EXISTS {0} (
            id MEDIUMINT UNSIGNED NOT NULL,
            value MEDIUMINT UNSIGNED NULL)
        """.format(TT_HELP))


def createResultTempTable(tableName,dropIfExists):
    """Create a temporary table of the given name which may be used as resultTable for the search- and textSearch-methods. If dropIfExists is true, an existing table of the same name will be dropped (otherwise an DBException will be raised when performing the CREATE-query)."""
    if dropIfExists:
        db.query("DROP TABLE IF EXISTS {0}".format(tableName)) # TODO: For debugging reasons a persistent table is created
    db.query("""
        CREATE TABLE IF NOT EXISTS {0} (
            id MEDIUMINT UNSIGNED,
            toplevel TINYINT UNSIGNED DEFAULT 0,
            new TINYINT UNSIGNED DEFAULT 1,
            PRIMARY KEY(id))
        """.format(tableName))


def stdTextSearch(searchString,resultTable,fromTable,logicalMode):
    stdSearch(searchparser.parseSearchString(searchString),resultTable,fromTable,logicalMode)


def stdSearch(criteria,resultTable,fromTable='containers',logicalMode=CONJUNCTION):
    search(criteria,resultTable,fromTable,logicalMode)
    addChildren(resultTable)
    addFilledParents(resultTable)
    setTopLevelFlag(resultTable)


def textSearch(searchString,resultTable,fromTable='containers',logicalMode=CONJUNCTION):
    """Parse the given search string to TextCriteria and submit them together with all other arguments to the search-method."""
    search(searchparser.parseSearchString(searchString),resultTable,fromTable,logicalMode)


def search(criteria,resultTable,fromTable='containers',logicalMode=CONJUNCTION):
    """Search the database and store the result in a table.
    
    This method finds all direct results fulfilling all or at least one of the given criteria and writes them into <resultTable>.
    
    Detailed parameter description:
    - <criteria> is a list of criteria (confer the criteria-module). Depending on <logicalMode> only containers fulfilling all or at least one of the criteria will be found.
    - The id of each container found by the search is stored in the 'id'-column of <resultTable>. This table should be created with the createResultTempTable-method (or has to contain at least the columns created by that method and default values for all other columns. This table will be truncated before the search is performed!
    - This method will find only containers with records in <fromTable>. Since <fromTable> defaults to 'containers' usually all containers are searched. <fromTable> must contain an 'id'-column holding container-ids.
    - <logicalMode> specifies if a container must fulfill all criteria (CONJUNCTION) or only at least one criterion (DISJUNCTION) to be found.
    """
    assert(logicalMode == CONJUNCTION) #TODO: Support DISJUNCTION
    
    # Build a list if only one criterion is submitted
    if not hasattr(criteria,'__iter__'):
        criteria = (criteria,)
    else:
        # Sort the most complicated criteria to the front hoping that we get right from the beginning only a few results
        criteria.sort(key=criteriaModule.sortKey,reverse=True)
        
    db.query("TRUNCATE TABLE {0}".format(resultTable))
    
    # We firstly search for the direct results of the first query... 
    db.query("INSERT INTO {0} (id) {1}".format(resultTable,criteria[0].getQuery(fromTable)))
    # ...and afterwards delete those entries which do not match the other queries
    for criterion in criteria[1:]:
        db.query("TRUNCATE TABLE {0}".format(TT_HELP))
        db.query("INSERT INTO {0} (id) {1}".format(TT_HELP,criterion.getQuery(resultTable)))
        db.query("DELETE FROM {0} WHERE id NOT IN (SELECT id FROM {1})".format(resultTable,TT_HELP))


def addChildren(resultTable,fromTable="containers"):
    while True:
        db.query("TRUNCATE TABLE {0}".format(TT_HELP))
        # First store all direct results which have children in TT_HELP
        result = db.query("""
            INSERT INTO {0} (id)
                SELECT {1}.id
                FROM {1} JOIN containers ON {1}.id = containers.id
                WHERE {1}.new = 1 AND containers.elements > 0
            """.format(TT_HELP,resultTable))
        if result.affectedRows() == 0:
            break
        db.query("UPDATE {0} SET new = 0".format(resultTable))
        # If fromTable is not containers this query part will ensure that only elements in fromTable will be added.
        if fromTable != 'containers':
            restrictToFromTablePart = "JOIN {0} ON {0}.id = contents.element_id".format(fromTable)
        else: restrictToFromTablePart = ''
        db.query("""
            INSERT IGNORE INTO {0} (id,new)
                SELECT contents.element_id,1
                FROM {1} AS parents JOIN contents ON parents.id = contents.container_id {2}
                GROUP BY contents.element_id
                """.format(resultTable,TT_HELP,restrictToFromTablePart))


def addFilledParents(resultTable,fromTable="containers"):
    db.query("TRUNCATE TABLE {0}".format(TT_HELP))
    db.query("UPDATE {0} SET new = 1".format(resultTable))
    while True:
         # If fromTable is not containers this query part will ensure that only elements in fromTable will be added.
        if fromTable != 'containers':
            restrictToFromTablePart = "JOIN {0} ON {0}.id = contents.element_id".format(fromTable)
        else: restrictToFromTablePart = ''
        result = db.query("""
            INSERT INTO {0} (id,value)
                SELECT contents.container_id, COUNT(*)
                FROM {1} JOIN contents ON {1}.id = contents.element_id {2}
                WHERE {1}.new = 1
                GROUP BY contents.container_id
                """.format(TT_HELP,resultTable,restrictToFromTablePart))
        if result.affectedRows() == 0:
            break
        db.query("UPDATE {0} SET new = 0".format(resultTable))
        db.query("""
            INSERT IGNORE INTO {0} (id,new)
                SELECT {1}.id,1
                FROM {1} JOIN containers ON {1}.id = containers.id
                WHERE containers.elements = {1}.value
                """.format(resultTable,TT_HELP))


def setTopLevelFlag(table):
    db.query("TRUNCATE TABLE {0}".format(TT_HELP))
    if table != "containers":
        restrictToTablePart = "JOIN {0} ON contents.element_id = {0}.id".format(table)
    else: restrictToTablePart = ''
    db.query("""
        INSERT INTO {0} (id)
            SELECT DISTINCT contents.element_id
            FROM {1} AS parents JOIN contents ON parents.id = contents.container_id {2}
            """.format(TT_HELP,table,restrictToTablePart))
    db.query("UPDATE {0} SET toplevel = 1".format(table))
    db.query("INSERT INTO {0} (id) (SELECT id FROM {1}) ON DUPLICATE KEY UPDATE toplevel = 0".format(table,TT_HELP))
    
    
def printResultTable(table):
    result = db.query("""
        SELECT res.id,res.toplevel,res.new,containers.name
        FROM {0} as res JOIN containers ON res.id = containers.id
        """.format(table))
    print("Printing result table "+table)
    for row in result:
        print("{0} '{3}' Toplevel: {1} New: {2}".format(*row))
                