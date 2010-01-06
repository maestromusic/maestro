#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from omg import database, tags
from . import searchparser, queryclasses

# Temporary table used by the search algorithm
TT_HELP = 'tmp_help'

# When deciding which query should be performed first, queries with tag prefix are favored by this factor since they tend to give less results than searches in all indexed tags.
SINGLE_TAG_QUERY_MULTIPLIER = 3

# Logical modes
DISJUNCTION = 1
CONJUNCTION = 2

db = None

def init():
    global db
    db = database.get()
    db.query("DROP TABLE IF EXISTS {0}".format(TT_HELP))
    db.query("""
        CREATE TABLE IF NOT EXISTS {0} (
            id MEDIUMINT UNSIGNED NOT NULL,
            parent_id MEDIUMINT UNSIGNED NULL)
        """.format(TT_HELP))


def createResultTempTable(tableName,dropIfExists):
    if dropIfExists:
        db.query("DROP TABLE IF EXISTS {0}".format(tableName))
    db.query("""
        CREATE TABLE IF NOT EXISTS {0} (
            id MEDIUMINT UNSIGNED,
            toplevel TINYINT UNSIGNED DEFAULT 0,
            new TINYINT UNSIGNED DEFAULT 1,
            PRIMARY KEY(id))
        """.format(tableName))
    
    
def textSearch(searchString,resultTable,fromTable='containers',addChildren=True,addParents=True):
    search(searchparser.parseSearchString(searchString),CONJUNCTION,resultTable,fromTable,addChildren,addParents)


def search(queries,logicalMode,resultTable,fromTable='containers',addChildren=True,addParents=True):
    # Build a list if only one query is submitted
    if not hasattr(queries,'__iter__'):
        queries = (queries,)
        
    # Sort the most complicated queries to the front hoping that we get right from the beginning only a few results
    queries.sort(key=queryclasses.sortKey,reverse=True)
        
    db.query("TRUNCATE TABLE {0}".format(resultTable))
    
    # We firstly search for the direct results of the first query... 
    db.query("INSERT INTO {0} (id) {1}".format(resultTable,queries[0].getDBQuery(fromTable)))
    # ...and afterwards delete those entries which do not match the other queries
    for query in queries[1:]:
        db.query("TRUNCATE TABLE {0}".format(TT_HELP))
        db.query("INSERT INTO {0} (id) {1}".format(TT_HELP,query.getDBQuery(resultTable)))
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
            # Then insert their children in resultTable and set their toplevel-value to 0
            # Warning: all children are added from the containers-table regardless of fromTable
            db.query("""
                INSERT IGNORE INTO {0} (id,new)
                    SELECT contents.element_id,1
                    FROM {1} JOIN contents ON {1}.id = contents.container_id
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