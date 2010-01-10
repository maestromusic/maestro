#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from omg import database, tags
from . import searchparser, matchclasses

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
            parent_id MEDIUMINT UNSIGNED NULL)
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
    
    
def textSearch(searchString,resultTable,fromTable='containers',logicalMode=CONJUNCTION,addChildren=True,addParents=True):
    """Parse the given search string to TextMatches and submit them together with all other arguments to the search-method."""
    search(searchparser.parseSearchString(searchString),resultTable,fromTable,logicalMode,addChildren,addParents)


def search(matches,resultTable,fromTable='containers',logicalMode=CONJUNCTION,addChildren=True,addParents=True):
    """Search the database and store the result in a table.
    
    Firstly this method will find all 'direct results' and write them into <resultTable> (what containers are direct results depends on <matches>, <fromTable> and <logicalMode>. If <addChildren> or <addParents> are true afterwards all children or parents, respectively, will be added to <resultTable>.
    
    Detailed parameter description:
    - <matches> is a list of matches (confer the matchclasses module). Depending on <logicalMode> only containers matching all or at least one of the matches will be found.
    - The id of each container found by the search is stored in the 'id'-column of <resultTable>. This table should be created with the createResultTempTable-method (or has to contain at least the columns created by that method and default values for all other columns. This table will be truncated before the search is performed!
    - This method will find only containers with records in <fromTable>. Since <fromTable> defaults to 'containers' usually all containers are searched but you may use this parameter to use another table. <fromTable> must contain an 'id'-column holding container-ids.
    - <logicalMode> specifies if a container must match all matches (CONJUNCTION) or only at least one match (DISJUNCTION) to be found.
    - If <addChildren> is true after performing the search all child elements of direct results and recursively all their children are added to <resultTable> (if they do not already exist in that table). Again only elements from <fromTable> are added. 
    - If <addParents> is true after performing the search all parent elements of the elements in <resultTable> and recursively all their parents are added to <resultTable> (if they do not already exist in that table). Again only elements from <fromTable> are added. If both <addChildren> and <addParents> are true, the children are added first. In that case even parents of elements which are not direct results may be added. If <addParents> is true, the 'toplevel'-column of <resultTable> will contain a 1 if and only if a container does not have any parents.
    """
    # Build a list if only one match is submitted
    if not hasattr(matches,'__iter__'):
        matches = (matches,)
    else:
        # Sort the most complicated matches to the front hoping that we get right from the beginning only a few results
        matches.sort(key=matchclasses.sortKey,reverse=True)
        
    db.query("TRUNCATE TABLE {0}".format(resultTable))
    
    # We firstly search for the direct results of the first query... 
    db.query("INSERT INTO {0} (id) {1}".format(resultTable,matches[0].getQuery(fromTable)))
    # ...and afterwards delete those entries which do not match the other queries
    for match in matches[1:]:
        db.query("TRUNCATE TABLE {0}".format(TT_HELP))
        db.query("INSERT INTO {0} (id) {1}".format(TT_HELP,match.getQuery(resultTable)))
        db.query("DELETE FROM {0} WHERE id NOT IN (SELECT id FROM {1})".format(resultTable,TT_HELP))

    # Add all children
    if addChildren:
        while True:
            db.query("TRUNCATE TABLE {0}".format(TT_HELP))
            # First store all direct results which have children in TT_HELP
            if resultTable == 'containers':
                result = db.query("INSERT INTO {0} (id) SELECT id FROM containers WHERE new = 1 AND elements > 0"
                                     .format(TT_HELP))
            else: result = db.query("""
                INSERT INTO {0} (id)
                    SELECT {1}.id
                    FROM {1} JOIN containers ON {1}.id = containers.id
                    WHERE {1}.new = 1 AND containers.elements > 0
                """.format(TT_HELP,resultTable))
            if result.affectedRows() == 0:
                break
            db.query("UPDATE {0} SET new = 0".format(resultTable))
            db.query("""
                INSERT IGNORE INTO {0} (id,new)
                    SELECT contents.element_id,1
                    FROM {1} AS parents JOIN contents ON parents.id = contents.container_id
                             JOIN {1} AS children ON children.id = contents.element_id
                    GROUP BY contents.element_id
                    """.format(resultTable,TT_HELP))
    
    # Add all parents
    if addParents:
        db.query("UPDATE {0} SET new = 1".format(resultTable))
        while True:
            db.query("TRUNCATE TABLE {0}".format(TT_HELP))
            # Warning: all parents are added from the containers-table regardless of fromTable
            result = db.query("""
                INSERT INTO {0} (id,parent_id)
                SELECT {1}.id,contents.container_id
                FROM {1} LEFT JOIN contents ON {1}.id = contents.element_id
                WHERE {1}.new = 1 AND {1}.toplevel = 0
                """.format(TT_HELP,resultTable))

            # update those elements which have no parent (these rows exist due to the left join)
            db.query("""
                REPLACE INTO {0} (id,toplevel)
                SELECT {1}.id,1
                FROM {1}
                WHERE {1}.parent_id IS NULL
                """.format(resultTable,TT_HELP))
            
            if result.affectedRows() == 0:
                break
            db.query("UPDATE {0} SET new = 0".format(resultTable))
            db.query("""
                INSERT IGNORE INTO {0} (id,new)
                    SELECT {1}.parent_id,1
                    FROM {1}
                    WHERE {1}.parent_id IS NOT NULL
                    GROUP BY {1}.parent_id
                """.format(resultTable,TT_HELP))