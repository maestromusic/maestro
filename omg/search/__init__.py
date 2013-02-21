# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import threading

from PyQt4 import QtCore

from . import criteria as criteriaModule
from .. import database as db, config, logging
from ..core import tags

logger = logging.getLogger(__name__)

# Name of the temporary search table
# The table is created in the search thread and temporary, so that it does not conflict with other threads.
TT_HELP = 'tmp_help'

# An internal list to store all living engines and destroy them at the end.
engines = []


def init():
    """Initialize the search module."""
    criteriaModule.SEARCH_TAGS = set()
    for tagname in config.options.tags.search_tags:
        if tags.isInDb(tagname):
            criteriaModule.SEARCH_TAGS.add(tags.get(tagname))


def shutdown():
    """Shutdown the search module. This will destroy all result tables that are still existent!"""
    for engine in engines[:]:
        engine.shutdown()
    # Drop remaining search tables (maybe the last run of OMG crashed and did not remove them).
    for table in db.listTables():
        if table.startswith("{}tmp_search_".format(db.prefix)):
            db.query("DROP TABLE {}".format(table))


class SearchRequest:
    """A search request contains data about what to search and between which tables. A search request may only
    be used with a single search engine. 
    
    You may always read all attributes of SearchRequest, but never write to them! If you need to search for a
    changed request, then copy this request, stop it and search for the copy.
    
    The attributes are:
    
        - ''engine'': the SearchEngine
        - ''fromTable'': table name where you want to search
        - ''resultTable'': table name where the results should be stored. This table must be created by the
            SearchEngine's createResultTable method.
        - ''criterion'': The criterion the search results must match. See the criteria module.
        - ''data'': This is also not used and may contain any other data needed to process the searchFinished
            signal.
        - ''lockTable'': If True the resultTable will be locked after the search and every other search to
            that table will wait until you call releaseTable.
            
    \ """
    
    # This means that the Request was stopped and should be ignored by all receivers of the searchFinished
    # signal (it happens that the request is stopped when the event is already emitted, but not processed
    # yet).
    _stopped = False
    
    # Usually when the search is finished a searchFinished signal is emitted, but if _fireEvent is set to
    # True the engine's _finishedEvent is set instead (threading.Event). This is only used by searchAndWait.
    _fireEvent = False
    
    def __init__(self, engine, fromTable, criterion):
        self.engine = engine
        self.fromTable = fromTable
        self.result = None
        assert isinstance(criterion, criteria.Criterion)
        self.criterion = criterion
        self.stopped = False
            
    def stop(self):
        """Stop this request. Stopped requests will not be processed further and should be ignored by all
        receivers of the searchFinished signal (it might happen that the request is stopped when the event
        is already emitted, but not processed yet)."""
        self.stopped = True
        self.engine._thread.searchEvent.set()

    def releaseTable(self):
        """Release the table of this request if it is locked by this request.""" 
        with self.engine._thread.lock:
            if self.resultTable in self.engine._thread.lockedTables \
                    and self.engine._thread.lockedTables[self.resultTable] is self:
                logger.debug("Releasing table {}".format(self.resultTable))
                del self.engine._thread.lockedTables[self.resultTable]
                self.engine._thread.searchEvent.set()
                
    def __str__(self):
        return "<SearchRequest in {}: {}".format(self.fromTable, self.criterion)
        

class SearchEngine(QtCore.QObject):
    """A SearchEngine controls a worker thread that can perform searches in the database. If you want to
    search, create a SearchEngine, use createResultTable and then use search.
    """
    # Static! This lock is used to create unique names for result tables across different search engines.
    _resultTableLock = None
    
    _thread = None # Search thread
    
    _finishedEvent = None # This threading.Event is used for searchAndWait
    
    searchFinished = QtCore.pyqtSignal(SearchRequest)
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        if SearchEngine._resultTableLock is None:
            SearchEngine._resultTableLock = threading.Lock()
        self._tables = []
        self._thread = SearchThread(self)
        self._thread.start()
        self._finishedEvent = threading.Event()
        engines.append(self)
               
    def search(self,*args,**kargs):
        """Perform a search. The arguments are the same as in SearchRequest.__init__ except that the engine
        parameter must not be given (it is set to this engine). Return the generated SearchRequest.
        """
        request = SearchRequest(self,*args,**kargs)
        self.addRequest(request)
        return request

    def searchAndWait(self,*args,**kargs):
        """Perform a search and wait until it is finished. The arguments are the same as in
        SearchRequest.__init__ except that the engine parameter must not be given (it is set to this engine).
        Return the generated SearchRequest.
        """
        request = SearchRequest(self,*args,**kargs)
        request._fireEvent = True
        self._finishedEvent.clear()
        self.addRequest(request)
        self._finishedEvent.wait()
        return request
        
    def addRequest(self,request):
        """Search for *request*."""
        assert request.engine is self
        with self._thread.lock:
            if request in self._thread.requests or request.stopped:
                return
            logger.debug("Search: Got new request {}".format(request))
            self._thread.requests.append(request)
        self._thread.searchEvent.set()

    def shutdown(self):
        """Shut down this engine. In particular terminate the search thread and drop all result tables
        associated with this engine.
        """
        engines.remove(self)
        self._thread.quit = True
        # Wake up the thread to tell it to shut down
        self._thread.searchEvent.set()
        self._thread.join()
        self._thread = None


class StopRequestException(Exception):
    pass


class SearchThread(threading.Thread):
    """Each SearchEngine controls a SearchThread that does the actual searching."""
    # A reference to the search engine controlling this thread
    engine = None
    
    # This threading is used to wake the search thread when work has to be done.
    searchEvent = None
    
    # This lock protects access to the shared variables requests, quit and lockedTables.
    lock = None
    
    # The search thread keeps track of what it has inserted into result tables: This dict maps the names
    # of all result tables created by the engine's createResultTable method to None (no information available)
    # or a tuple consisting of
    # - the name of the table where the records came from
    # - the criteria that have been used to filter the records
    # This information sometimes allows the search thread to save work (e.g. if we've searched for 'beet'
    # and are now searching for 'beethoven').
    tables = None
    
    # The list of search requests that have to be processed
    requests = None
    
    # This is set to True when the main thread wants the search thread to terminate.
    quit = False
    
    # Dict mapping names of locked tables to the request that locked the table. Only that request may release
    # the table.
    lockedTables = None
    
    def __init__(self,engine):
        threading.Thread.__init__(self)
        self.daemon = True # Confer threading.Thread
        self.parentThread = threading.current_thread()
        self.engine = engine
        self.lock = threading.Lock()
        self.searchEvent = threading.Event()
        self.tables = {}
        self.requests = []
        self.lockedTables = {}

    def run(self):      
        logger.debug('Search connecting with thread {}'.format(QtCore.QThread.currentThreadId()))

        with db.connect():
            if db.type == 'mysql':
                db.query("""
                    CREATE TABLE IF NOT EXISTS {} (
                        value_id MEDIUMINT UNSIGNED NOT NULL,
                        tag_id MEDIUMINT UNSIGNED NULL,
                        INDEX(value_id, tag_id))
                        CHARACTER SET 'utf8'
                    """.format(TT_HELP))
            else:
                db.query("""
                    CREATE TEMPORARY TABLE IF NOT EXISTS {} (
                        value_id  MEDIUMINT UNSIGNED NOT NULL,
                        tag_id MEDIUMINT UNSIGNED NULL)
                    """.format(TT_HELP))
                db.query("CREATE INDEX {0}_idx ON {0} (value_id, tag_id)".format(TT_HELP))
        
            while True:
                if self.quit:
                    break # Terminate the search thread
                
                self.lock.acquire()
                while len(self.requests) > 0 and self.requests[0].stopped:
                    self.requests.pop(0)
                    
                if len(self.requests) == 0:# or self.requests[0].resultTable in self.lockedTables:
                    # Wait for something to do or until the result table is not locked anymore
                    logger.debug("Waiting {}".format("(no requests)" if len(self.requests) == 0 
                                                                     else "(table locked)"))
                    self.lock.release()
                    self.searchEvent.wait()
                    self.searchEvent.clear()
                    continue # start from above (maybe quit is now true or the result table is still locked.)
                
                request = self.requests.pop(0)
                self.lock.release()
                
                try:
                    result = None
                    for criterion in request.criterion.getCriteriaDepthFirst():
                        logger.debug("Processing criterion: ".format(criterion))
                        if not isinstance(criterion, criteria.MultiCriterion):
                            for queryData in criterion.getQueries(request.fromTable):
                                #print(queryData)
                                if isinstance(queryData, str):
                                    result = db.query(queryData)
                                else: result = db.query(*queryData)
                                #print(list(db.query("SELECT value FROM new_values_varchar WHERE id IN (SELECT value_id FROM tmp_help)").getSingleColumn()))
                                self._check(request)
                            criterion.result = set(result.getSingleColumn())
                        else:
                            if criterion.junction == 'AND':
                                method = criterion.criteria[0].result.intersection
                            else: method = criterion.criteria[0].result.union
                            criterion.result = method(*[crit.result for crit in criterion.criteria[1:]])
                            self._check(request)
    
                    logger.debug("Request finished")
                    request.result = criterion.result
                    self.engine.searchFinished.emit(request)
                except StopRequestException:
                    logger.debug("StopRequestException")
                    continue
                
            for table in self.tables:
               db.query("DROP TABLE {}".format(table))
                
    def _check(self, request):
        if self.quit or request.stopped:
            raise StopRequestException()
    
    def finishRequest(self,request):
        """Finish *request*: lock the table, emit the signal..."""
        with self.lock:
            if not request.stopped:
                if request.lockTable:
                    #logger.debug("Add to locked tables: {}".format(request.resultTable))
                    self.lockedTables[request.resultTable] = request
                self.requests.remove(request)
                #logger.debug("Finished request {}".format(request))
                if request._fireEvent:
                    self.engine._finishedEvent.set()
                else: self.engine.searchFinished.emit(request)
            
    def processCriterion(self,fromTable,resultTable,criterion):
        """Process a criterion. This is where the actual search happens."""
        #logger.debug("processing criterion {}".format(criterion))
        if len(self.tables[resultTable][1]) == 0:
            # We firstly search for the direct results of the first query... 
            #logger.debug("Starting search...")
            truncate(resultTable)
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
            truncate(TT_HELP)
            queryData = criterion.getQuery(resultTable,columns=('id',))
            queryData[0] = "INSERT INTO {0} (id) {1}".format(TT_HELP,queryData[0])
            #print(*queryData)
            db.query(*queryData)
            db.query("DELETE FROM {0} WHERE id NOT IN (SELECT id FROM {1})"
                       .format(resultTable,TT_HELP))
                       
    @staticmethod
    def _procContainer(processedIds,id):
        """This is a help function for post processing. It will check if the container with id *id* has to be
        added to the search result because it is major or has a major parent. It will return the result and
        additionally store it in the dict *processedIds*. This dict will be used as cache to avoid doing the
        computation twice for the same id. The dict maps the ids of processed containers to a tuple containing
        the result (haveToAdd) in the first component and -- only if haveToAdd is true -- another tuple
        (id,file,major) in the second component (This will be used by the post processing later."""
        parents = db.parents(id)
        haveToAdd = False
        for pid in parents:
            # If we have to add the parent, we also have to add this node.
            if pid not in processedIds:
                if SearchThread._procContainer(processedIds,pid):
                    haveToAdd = True
            elif processedIds[pid][0]:
                haveToAdd = True
        
        major = db.isMajor(id)
        if major:
            haveToAdd = True
            
        processedIds[id] = (haveToAdd,(id,db.isFile(id),major) if haveToAdd else None)
        return haveToAdd
    
    def postProcessing(self,resultTable):
        """Currently post processing...
        
            - adds to the search result all parents of search results which are major or have a major parent 
            - and sets the toplevel flags correctly.
        
        \ """
        result = db.query("""
                SELECT DISTINCT {0}contents.container_id
                FROM {1} JOIN {0}contents ON {1}.id = {0}contents.element_id
                """.format(db.prefix,resultTable))
        
        if result.size() > 0:
            processedIds = {}
            for id in result.getSingleColumn():
                if not id in processedIds:
                    SearchThread._procContainer(processedIds, id)
            args = [data for haveToAdd,data in processedIds.values() if haveToAdd]
            if len(args) > 0:
                command = 'INSERT IGNORE' if db.type == 'mysql' else 'INSERT OR IGNORE' 
                db.multiQuery(
                    "{} INTO {} (id,file,major,direct) VALUES (?,?,?,0)"
                    .format(command, resultTable),args)
        
        setTopLevelFlags(resultTable)
        # Always include all children of direct results => select from elements
        addChildren(resultTable)


def addChildren(resultTable):
    """Add to *resultTable* all descendants of direct results."""
    # In the first step select direct results which have children, in the other steps select new results.
    attribute = 'direct'
    while True:
        truncate(TT_HELP)
        result = db.query("""
            INSERT INTO {2} (id)
                SELECT res.id
                FROM {1} AS res JOIN {0}elements USING(id)
                WHERE res.{3} = 1 AND {0}elements.elements > 0
            """.format(db.prefix,resultTable,TT_HELP,attribute))
        if result.affectedRows() == 0:
            return
        db.query("UPDATE {} SET new = 0".format(resultTable))
        db.query("""
            REPLACE INTO {1} (id,file,toplevel,direct,major,new)
                SELECT       c.element_id,el.file,0,0,el.major,1
                FROM {2} AS p JOIN {0}contents AS c ON p.id = c.container_id
                              JOIN {0}elements AS el ON el.id = c.element_id
                GROUP BY c.element_id
                """.format(db.prefix,resultTable,TT_HELP))
        attribute = 'new'


def setTopLevelFlags(table):
    """Set the toplevel flags in *table* to 1 if and only if the element has no parent in *table*. Of course
    *table* must have at least the columns ''id'' and ''toplevel''."""
    truncate(TT_HELP)
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
                FROM {0}contents AS c JOIN {2} AS parents ON c.container_id = parents.id
                                      JOIN {2} AS children ON c.element_id = children.id
                """.format(db.prefix,TT_HELP,table))

    db.query("UPDATE {} SET toplevel = id NOT in (SELECT id FROM {})".format(table,TT_HELP))


def truncate(tableName):
    if db.type == 'mysql':
        # truncate may be much faster than delete
        db.query('TRUNCATE {}'.format(tableName))
    else: db.query('DELETE FROM {}'.format(tableName))
