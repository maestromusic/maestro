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

from .. import database as db, tags, config, logging
from . import searchparser
from . import criteria as criteriaModule

# Name of the temporary search table
# The table is created in the search thread and temporary, so that it does not conflict with other threads.
TT_HELP = 'tmp_help'

# Commands that are used by the main thread to control the search thread.
SEARCH,QUIT = 0,1

logger = logging.getLogger("omg.search")

# An internal list to store all living engines and destroy them at the end.
engines = []

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


class SearchRequest:
    def __init__(self,fromTable,resultTable,criteria,owner=None,parent=None,data=None,lockTable=False):
        self.fromTable = fromTable
        self.resultTable = resultTable
        self.criteria = criteria
        self.originalCriteria = criteria
        self.owner = owner
        self.parent = parent
        self.data = data
        self.lockTable = lockTable
        

class StopRequest:
    def __init__(self,owner):
        self.owner = owner


class SearchEngine(QtCore.QObject):
    """A SearchEngine controls a worker thread that can perform searches in the database. If you want to
    search, create a SearchEngine, use createResultTable and then use runSearch."""
    _thread = None      # Search thread
    _searchEvent = None # threading.Event that is used to wake the search thread
    _lock = None        # threading.Lock to protect the data shared between the threads
    _tables = None      # list of result tables associated to this engine

    # The following variables are shared with the search thread. Use _lock whenever accessing them
    _newRequests = None # list of SearchRequests that wait to be read from the thread
    _command = None     # command to control search thread 
    _releaseTables = None
    
    searchFinished = QtCore.pyqtSignal(SearchRequest)
    searchStopped = QtCore.pyqtSignal(StopRequest)
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        self._tables = []
        self._command = SEARCH
        self._newRequests = []
        self._releaseTables = set()
        
        self._lock = threading.Lock()
        self._searchEvent = threading.Event()
        self._thread = SearchThread(self)
        self._thread.start()
        engines.append(self)

    def createResultTable(self,part,customColumns=""):
        """Create a MySQL table that can hold search results. The table will be created in memory. *part*
        must be a string which is unique among all result tables of any engine.
        
        All tables created with this method belong to this engine and will be dropped when this engine is
        shut down.
        
        Warning: Do not change the set of elements in the result table, unless you are not going to use it for
        a search again.
        """
        tableName = "{}tmp_search_{}".format(db.prefix,part)
        if tableName in db.listTables():
            logger.warning("Table '{}' does already exist. I will drop it.".format(tableName))
            db.query("DROP TABLE {}".format(tableName))
        if len(customColumns) > 0 and customColumns[-1] != ',':
            customColumns = customColumns + ','
        db.query("""
            CREATE TABLE {} (
                id MEDIUMINT UNSIGNED,
                {}
                file BOOLEAN,
                toplevel BOOLEAN DEFAULT 0,
                direct BOOLEAN DEFAULT 1,
                major BOOLEAN DEFAULT 0,
                PRIMARY KEY(id))
                ENGINE MEMORY;
            """.format(tableName,customColumns))
        with self._lock:
            self._tables.append(tableName)
        return tableName

    def search(self,fromTable,resultTable,criteria,owner=None,parent=None,data=None,lockTable=False):
        """Search in *fromTable* for elements matching every criterion in *criteria* and store them in
        *resultTable*."""
        with self._lock:
            self._newRequests.append(SearchRequest(fromTable,resultTable,criteria,owner,parent,data,lockTable))
        self._searchEvent.set()

    def stopSearch(self,owner):
        with self._lock:
            self._newRequests.append(StopRequest(owner))
        self._searchEvent.set()

    def releaseTable(self,table):
        with self._lock:
            print("Releasing table {}".format(table))
            self._releaseTables.add(table)
        self._searchEvent.set()

    def shutdown(self):
        """Shut down this engine. In particular terminate the search thread and drop all result tables
        associated with this engine."""
        engines.remove(self)
        with self._lock:
            self._command = QUIT
        # Wake up the thread to tell it to shut down
        self._searchEvent.set()
        # Wait for the thread to finish before dropping the tables
        self._thread.join()
        self._thread = None
        for tableName in self._tables:
            db.query("DROP TABLE {}".format(tableName))


class SearchThread(threading.Thread):
    # The search thread keeps track of what it has inserted into result tables: This dict maps the names
    # of all result tables used so far by this thread to tuples consisting of
    # - the name of the table where the records came from
    # - the criteria that have been used to filter the records
    # This information sometimes allows the search thread to save work (e.g. if we've searched for 'beet'
    # and are now searching for 'beethoven').
    tables = None
    
    # The list of search requests that have to be processed
    requests = None
    
    """Each SearchEngine controls a SearchThread that does the actual searching."""
    def __init__(self,engine):
        threading.Thread.__init__(self)
        self.engine = engine
        self._parentThread = threading.current_thread()
        self.daemon = True
        self.tables = {}
        self.requests = []
        self.lockedTables = set()

    def run(self):
        """This method contains the search algorithm. It works like this::
        
            while True:
                if len(requests) == 0: wait for something to do
                
                copy data from the main thread (_command,_newRequests)
                
                if _command == QUIT: quit
                
                if len(newRequests):
                    add them to requests (append requests without key, replace existing keys, delete requests
                    when a request matches their delKey; confer processNewRequests)
                
                if currentRequest != self.requests[0]: # This means that we start processing the next request
                                                         or that the current request has changed.
                    self.prepare() # prepare result table and the request's criteria
    
                if len(currentRequest.criteria) == 0:
                    search request finished -> emit signal
                else:
                    process currentRequest.criteria[0]
                    
        """        
        with db.connect():
            db.query("""
            CREATE TEMPORARY TABLE IF NOT EXISTS {0} (
                id MEDIUMINT UNSIGNED NOT NULL,
                value MEDIUMINT UNSIGNED NULL)
                CHARACTER SET 'utf8';
            """.format(TT_HELP))
            
            currentRequest = None
        
            while True:
                if len(self.requests) == 0 or (currentRequest is not None and currentRequest.resultTable in self.lockedTables):
                    # Wait for something to do or until the result table is not locked anymore
                    self.engine._searchEvent.wait()
                    self.engine._searchEvent.clear()
                    
                    # TODO: The following condition should never be true: Either _command = QUIT or
                    # _newRequests.append(...) are called before the search event is triggered.
                    # Nevertheless it happens...
                    with self.engine._lock:
                        if self.engine._command == SEARCH and len(self.engine._newRequests) == 0 and len(self.engine._releaseTables) == 0:
                            print("Weird thing happened")
                            continue
                
                # Copy data from main thread
                with self.engine._lock:
                    command = self.engine._command
                    newRequests = self.engine._newRequests
                    self.engine._newRequests = []
                    self.lockedTables -= self.engine._releaseTables
                    self.engine._releaseTables = set()
    
                if command == QUIT or not self._parentThread.is_alive():
                    return # Terminate the thread
                
                if len(newRequests) > 0:
                    self.processNewRequests(newRequests)
                
                if len(self.requests) == 0:
                    # this happens only if newRequests contained a StopRequest
                    # and all other requests were removed.
                    continue
                
                # This has to happen before prepare
                if currentRequest is None and len(self.requests) > 0 and self.requests[0].resultTable in self.lockedTables:
                    continue # Wait for better times
                    
                if currentRequest is not self.requests[0]:
                    # This happens
                    # - if this is our first search after waiting for the search event
                    # - if we finished a criterion and begin processing the next one
                    # - if the current request was modified by processNewRequests (e.g. because a new request
                    #   with the same key appeared).
                    # We have to check whether we have to truncate the result table or whether the requests
                    # selects a subset of the stuff in the result table, so that we can keep the entries.
                    currentRequest = self.requests[0]
                    self.prepare(currentRequest)
                
                # Invalid criteria like 'date:foo' do not have results. Calling criterion.getQuery will fail.
                if any(c.isInvalid() for c in currentRequest.criteria):
                    print("Invalid criteria")
                    db.query("TRUNCATE TABLE {}".format(currentRequest.resultTable))
                    self.tables[currentRequest.resultTable][1] = []
                    print("Finished search")
                    if currentRequest.lockTable:
                        with self.engine._lock:
                            self.lockedTables.add(currentRequest.resultTable)
                    self.engine.searchFinished.emit(currentRequest)
                    self.requests.pop(0)
                    currentRequest = None
                    continue
                
                if len(currentRequest.criteria) == 0:
                    # We already finished the request in the last loop.
                    # Or the criteria were redundant and were removed by criteriaModule.reduce.
                    print("Starting post-processing...")
                    self.postProcessing(currentRequest.resultTable)
                    # After post processing forget the data we collected about this table.
                    # Any other search going to this table must first truncate it.
                    del self.tables[currentRequest.resultTable]
                    print("Finished search")
                    if currentRequest.lockTable:
                        with self.engine._lock:
                            print("Add to result locked tables: {}".format(currentRequest.resultTable))
                            self.lockedTables.add(currentRequest.resultTable)
                    self.engine.searchFinished.emit(currentRequest)
                    self.requests.pop(0)
                    currentRequest = None
                    continue
                
                # Finally do some work and process a criterion:
                criterion = currentRequest.criteria.pop(0)
                #time.sleep(2)
                self.processCriterion(currentRequest.fromTable,currentRequest.resultTable,criterion)
                self.tables[currentRequest.resultTable][1].append(criterion)
        
    def processNewRequests(self,newRequests):
        """Process the list of newRequests depending on their owners and parents (confer SearchRequest)."""
        for newRequest in newRequests:
            if isinstance(newRequest,StopRequest):
                self.requests = [r for r in self.requests if r.owner != newRequest.owner
                                                              and r.parent != newRequest.owner]
                self.engine.searchStopped.emit(newRequest)
                continue
            if newRequest.owner is None:
                self.requests.append(newRequest)
            else:
                for i,oldRequest in enumerate(self.requests):
                    # Replace the request
                    if newRequest.owner == oldRequest.owner:
                        self.requests[i] = newRequest
                        break
                else: self.requests.append(newRequest)
                # Remove requests whose parent got updated
                self.requests = [r for r in self.requests if r.parent != newRequest.owner]
                
    def prepare(self,request):
        """Prepare the result table and filter redundant criteria of the given request. This method is called
        whenever we start processing a request and whenever that request changes (i.e. a new request with the
        same key was submitted to the thread)."""
        resultTable = request.resultTable
        if (resultTable not in self.tables
            or request.fromTable != self.tables[resultTable][0]
            or not criteriaModule.isNarrower(request.criteria,self.tables[resultTable][1])):
            # Unfortunately we have to start a new search
            db.query("TRUNCATE TABLE {}".format(resultTable))
            self.tables[resultTable] = (request.fromTable,[])
        
        request.criteria = criteriaModule.reduce(request.criteria,self.tables[request.resultTable][1])
            
    def processCriterion(self,fromTable,resultTable,criterion):
        """This is where the actual search happens."""
        if len(self.tables[resultTable][1]) == 0:
            # We firstly search for the direct results of the first query... 
            print("Starting search...")
            db.query("TRUNCATE TABLE {0}".format(resultTable))
            queryData = criterion.getQuery(fromTable,columns=('id','file','major'))
            # Prepend the returned query with INSERT INTO...
            queryData[0] = "INSERT INTO {0} (id,file,major) {1}".format(resultTable,queryData[0])
            #print(*queryData)
            db.query(*queryData)
        else:
            # ...and afterwards delete those entries which do not match the other queries
            # As we cannot modify a table of which we select from, we have to store the direct
            # search results in TT_HELP. Then we remove everything from the result table that is
            # not contained in TT_HELP.
            db.query("TRUNCATE TABLE {0}".format(TT_HELP))
            queryData = criterion.getQuery(resultTable,columns=('id',))
            queryData[0] = "INSERT INTO {0} (id) {1}".format(TT_HELP,queryData[0])
            #print(*queryData)
            db.query(*queryData)
            db.query("DELETE FROM {0} WHERE id NOT IN (SELECT id FROM {1})"
                       .format(resultTable,TT_HELP))
          
    @staticmethod
    def _procContainer(processedIds,id):
        parents = db.parents(id)
        result = False
        for pid in parents:
            if pid not in processedIds:
                if SearchThread._procContainer(processedIds,pid):
                    result = True
            elif processedIds[pid][0]:
                result = True
        
        major = db.isMajor(id)
        if major:
            result = True
        processedIds[id] = (result,major)
        return result
    
    def postProcessing(self,resultTable):
        result = db.query("""
                SELECT DISTINCT {0}contents.container_id
                FROM {1} JOIN {0}contents ON {1}.id = {0}contents.element_id
                """.format(db.prefix,resultTable))
        
        if result.size() > 0:
            processedIds = {}
            for id in result.getSingleColumn():
                if not id in processedIds:
                    SearchThread._procContainer(processedIds, id)
            args = [(id,tup[1]) for id,tup in processedIds.items() if tup[0]]
            if len(args) > 0:
                db.multiQuery(
                    "INSERT IGNORE INTO {} (id,major,direct) VALUES (?,?,0)"
                    .format(resultTable),args)

        setTopLevelFlags(resultTable)


def setTopLevelFlags(table):
    db.query("TRUNCATE TABLE {0}".format(TT_HELP))
    if table == db.prefix + "elements":
        db.query("""
            INSERT INTO {1} (id)
                SELECT DISTINCT {0}contents.element_id
            """.format(db.prefix,TT_HELP))
    else:
        # in this case make sure the results as well as their parents are contained in table
        db.query("""
            INSERT INTO {1} (id)
                SELECT DISTINCT c.element_id
                FROM contents AS c JOIN {2} AS parents ON c.container_id = parents.id
                                   JOIN {2} AS children ON c.element_id = children.id
                """.format(db.prefix,TT_HELP,table))

    db.query("UPDATE {} SET toplevel = 1".format(table))
    db.query("INSERT INTO {0} (id) (SELECT id FROM {1}) ON DUPLICATE KEY UPDATE toplevel = 0"
                .format(table,TT_HELP))
