#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import threading, time

from PyQt4 import QtCore
from PyQt4.QtCore import Qt

from omg import database as db, tags, config
from . import searchparser
from . import criteria as criteriaModule

# If the main application terminates it will stop the search thread (confer search.shutdown). But if the main thread crashes, this will not happen. Therefore the search thread will wake every TIMEOUT seconds and check whether the main thread is still alive.
TIMEOUT = 2


engines = []

# Name of the temporary search table
TT_HELP = 'tmp_help'

# Commands that are used by the main thread to control the search thread.
PAUSE,SEARCH,QUIT = range(3)

    
def init():
    """Initialize the search module."""
    criteriaModule.SEARCH_TAGS = set()
    for tagname in config.options.tags.search_tags:
        if tags.exists(tagname):
            criteriaModule.SEARCH_TAGS.add(tags.get(tagname))


def shutdown():
    """Shutdown the search module. This will destroy all result tables that are still existent!"""
    for engine in engines[:]:
        engine.shutdown()


class SearchEngine(QtCore.QObject):
    _thread = None      # Search thread
    _searchEvent = None # threading.Event that is used to wake the search thread
    _lock = None        # threading.Lock to protect the data shared between the threads
    _tables = None      # list of result tables associated to this engine

    # The following variables are shared with the search thread. Use _lock whenever accessing them
    _criteria = None    # list of criteria
    _fromTable = None   # the algorithm will look for results in this table
    _resultTable = None # and put the results in this one
    _commend = None     # command to control search thread 
    
    searchFinished = QtCore.pyqtSignal()
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        self._tables = []
        self._criteria = []
        self._command = PAUSE
        self._lock = threading.Lock()
        self._searchEvent = threading.Event()
        self._thread = SearchThread(self)
        self._thread.start()
        engines.append(self)

    def createResultTable(self,part,customColumns=""):
        """Create a MySQL table that can hold search results. The table will be created in memory. *part* must be a string which is unique among all result tables of this engine. To create a unique table name, use *part* and the thread name of this engine's search thread. So *part* must be unique among all result tables of this engine but you may create result tables for different engines using the same *part*.
        
        All tables created with this method are belong to this engine and will be dropped when this engine is shut down.
        """
        # TODO: This breaks if one day Python uses a format for its thread names which contains characters apart from '-' that are not allowed in table names. I need a thread-safe method to create unique names, though.
        threadIdentifier = self._thread.name.replace('-','')
        tableName = "{}tmp_search_{}_{}".format(db.prefix,part,threadIdentifier)
        if tableName in db.listTables():
            raise ValueError("A table with name '{}' does already exist.".format(tableName))
        if len(customColumns) > 0 and customColumns[-1] != ',':
            customColumns = customColumns + ','
        db.query("""
            CREATE TABLE {} (
                id MEDIUMINT UNSIGNED,
                {}
                toplevel TINYINT UNSIGNED DEFAULT 0,
                new TINYINT UNSIGNED DEFAULT 1,
                PRIMARY KEY(id))
                ENGINE MEMORY;
            """.format(tableName,customColumns))
        with self._lock:
            self._tables.append(tableName)
        return tableName

    def runSearch(self,fromTable,resultTable,criteria):
        """Search in *fromTable* for elements matching every criterion in *criteria* and store them in *resultTable*."""
        with self._lock:
            self._criteria = criteria
            self._fromTable = fromTable
            self._resultTable = resultTable
            self._command = SEARCH
        self._searchEvent.set()

    def shutdown(self):
        """Shut down this engine. In particular terminate the search thread and drop all result tables associated with this engine."""
        engines.remove(self)
        self._command = QUIT
        # Wake up the thread to tell it to shut down
        self._searchEvent.set()
        # Wait for the thread to finish before dropping the tables
        self._thread.join()
        self._thread = None
        for tableName in self._tables:
            db.query("DROP TABLE {}".format(tableName))


class SearchThread(threading.Thread):
    """Each SearchEngine controls a SearchThread that does the actual searching."""
    def __init__(self,engine):
        threading.Thread.__init__(self)
        self.engine = engine
        self._parentThread = threading.current_thread()

    def run(self):
        engine = self.engine
        tables = {}
        fromTable = None
        resultTable = None
        criteria = []
        command = PAUSE
        
        with db.connect():
            db.query("""
            CREATE TEMPORARY TABLE IF NOT EXISTS {0} (
                id MEDIUMINT UNSIGNED NOT NULL,
                value MEDIUMINT UNSIGNED NULL)
                CHARACTER SET 'utf8';
            """.format(TT_HELP))
        
            while True:
                # Copy data criteria from main thread
                with self.engine._lock:
                    command = self.engine._command
                    newFromTable = self.engine._fromTable
                    newResultTable = self.engine._resultTable
                    newCriteria = self.engine._criteria[:]

                if command == QUIT or not self._parentThread.is_alive():
                    print("Quit search thread")
                    return # Terminate the thread

                if command == PAUSE:
                    criteria = []
                    if engine._searchEvent.wait(TIMEOUT):
                        engine._searchEvent.clear()
                    continue # Start again copying data
                
                if newFromTable != fromTable or newResultTable != resultTable:
                    print("Switch from {} -> {} to {} -> {}".format(fromTable,resultTable,newFromTable,newResultTable))
                    fromTable = newFromTable
                    resultTable = newResultTable
                    # Start a new search
                    db.query("TRUNCATE TABLE {}".format(resultTable))
                    tables[resultTable] = []
                    criteria = newCriteria
                else:
                    if not criteriaModule.isNarrower(newCriteria,tables[resultTable]):
                        print("I got new criteria which are not narrower than the old ones. I'll start a new search.")
                        db.query("TRUNCATE TABLE {}".format(resultTable))
                        tables[resultTable] = []
                        criteria = newCriteria
                    else:
                        criteria = criteriaModule.reduce(newCriteria,tables[resultTable])
    
                if len(criteria) == 0:
                    # Nothing to do
                    self.engine.searchFinished.emit()
                    if engine._searchEvent.wait(TIMEOUT):
                        engine._searchEvent.clear()
                    continue # Start again copying data

                if len(criteria) > 0:
                    criteria.sort(key=criteriaModule.sortKey)

                if any(c.isInvalid() for c in criteria):
                    print("Invalid criteria")
                    db.query("TRUNCATE TABLE {}".format(resultTable))
                    self.engine.searchFinished.emit()
                    print("Finished search")
                    if engine._searchEvent.wait(TIMEOUT):
                        engine._searchEvent.clear()
                    continue # Start again copying data
                    
                # Process criteria
                #=====================
                criterion = criteria.pop(0)
                if len(tables[resultTable]) == 0:
                    # We firstly search for the direct results of the first query... 
                    print("Starting search...")
                    db.query("TRUNCATE TABLE {0}".format(resultTable))
                    queryData = criterion.getQuery(fromTable)
                    queryData[0] = "INSERT INTO {0} (id) {1}".format(resultTable,queryData[0])
                    #print(*queryData)
                    db.query(*queryData)
                else:
                    # ...and afterwards delete those entries which do not match the other queries
                    db.query("TRUNCATE TABLE {0}".format(TT_HELP))
                    queryData = criterion.getQuery(resultTable)
                    queryData[0] = "INSERT INTO {0} (id) {1}".format(TT_HELP,queryData[0])
                    #print(*queryData)
                    db.query(*queryData)
                    db.query("DELETE FROM {0} WHERE id NOT IN (SELECT id FROM {1})".format(resultTable,TT_HELP))

                tables[resultTable].append(criterion)

                if len(criteria) == 0:
                    print("Finished search")
                    self.engine.searchFinished.emit()
    

def addChildren(resultTable,fromTable="elements"):
    while True:
        db.query("TRUNCATE TABLE {0}".format(TT_HELP))
        # First store all direct results which have children in TT_HELP
        result = db.query("""
            INSERT INTO {0} (id)
                SELECT {1}.id
                FROM {1} JOIN elements ON {1}.id = elements.id
                WHERE {1}.new = 1 AND elements.elements > 0
            """.format(TT_HELP,resultTable))
        if result.affectedRows() == 0:
            break
        db.query("UPDATE {0} SET new = 0".format(resultTable))
        db.query("""
            INSERT IGNORE INTO {0} (id,file,new)
                SELECT contents.element_id,{2}.file,1
                FROM {1} AS parents JOIN contents ON parents.id = contents.container_id
                                    JOIN {2} ON {2}.id = contents.element_id
                GROUP BY contents.element_id
                """.format(resultTable,TT_HELP,fromTable))


def addFilledParents(resultTable,fromTable="elements"):
    db.query("TRUNCATE TABLE {0}".format(TT_HELP))
    db.query("UPDATE {0} SET new = 1".format(resultTable))
    while True:
         # If fromTable is not elements this query part will ensure that only elements in fromTable will be added.
        if fromTable != 'elements':
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
            INSERT IGNORE INTO {0} (id,file,new)
                SELECT {1}.id,0,1
                FROM {1} JOIN elements ON {1}.id = elements.id
                WHERE elements.elements = {1}.value
                """.format(resultTable,TT_HELP))


def setTopLevelFlag(table):
    db.query("TRUNCATE TABLE {0}".format(TT_HELP))
    if table != "elements":
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
        SELECT res.id,res.file,res.toplevel,res.new,elements.name
        FROM {0} as res JOIN elements ON res.id = elements.id
        """.format(table))
    print("Printing result table "+table)
    for row in result:
        print("{0} '{4}' File: {1} Toplevel: {2} New: {3}".format(*row))
