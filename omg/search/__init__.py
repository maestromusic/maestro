# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

import threading, queue

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
        - ''criterion'': The criterion the search results must match. See the criteria module. It is allowed
          to pass a list of criteria. They will be replaced by a MultiCriterion using 'AND'.
        - ''data'': This is also not used and may contain any other data needed to process the searchFinished
            signal.
            
    \ """   
    # Usually when the search is finished a searchFinished signal is emitted, but if _fireEvent is set to
    # True the engine's _finishedEvent is set instead (threading.Event). This is only used by searchAndWait.
    _fireEvent = False
    
    def __init__(self, engine, fromTable, criterion,
                 resultTable=None, postProcessing=None, callback=None, data=None):
        self.engine = engine
        self.stopped = False
        self.fromTable = fromTable
        self.result = None
        if not isinstance(criterion, criteria.Criterion):
            if len(criterion) == 1:
                criterion = criterion[0]
            else: criterion = criteria.MultiCriterion('AND', criterion)
        self.criterion = criterion
        self.resultTable = resultTable
        assert postProcessing is None or hasattr(postProcessing, '__iter__')
        self.postProcessing = postProcessing
        self.callback = callback
        self.data = data
            
    def stop(self):
        """Stop this request. Stopped requests will not be processed further and should be ignored by all
        receivers of the searchFinished signal (it might happen that the request is stopped when the event
        is already emitted, but not processed yet)."""
        self.stopped = True
        # do not set the result to None here, because the search thread might access this variable
        # self.result = None
        self.engine._thread.searchEvent.set()
                
    def __str__(self):
        return "<SearchRequest in {}: {}".format(self.fromTable, self.criterion)
        

class SearchEngine(QtCore.QObject):
    """A SearchEngine controls a worker thread that can perform searches in the database. If you want to
    search, create a SearchEngine, use createResultTable and then use search.
    """
    # Emitted when an event is completely finished (even after callbacks have been called)
    searchFinished = QtCore.pyqtSignal(SearchRequest)
    _searchFinished = QtCore.pyqtSignal(SearchRequest) # Internal
    
    # Static! This lock is used to create unique names for result tables across different search engines.
    _resultTableLock = threading.Lock()
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        self._tables = []
        self._searchFinished.connect(self._handleSearchFinished)
        self._thread = SearchThread(self)
        self._thread.start()
        self._finishedEvent = threading.Event() # This threading.Event is used for searchAndWait
        engines.append(self)
               
    def search(self, *args, **kargs):
        """Perform a search. The arguments are the same as in SearchRequest.__init__ except that the engine
        parameter must not be given (it is set to this engine). Return the generated SearchRequest.
        """
        request = SearchRequest(self, *args, **kargs)
        self.addRequest(request)
        return request

    def searchAndBlock(self, *args, **kargs):
        """Perform a search and block until it is finished. The arguments are the same as in
        SearchRequest.__init__ except that the engine parameter must not be given (it is set to this engine).
        Return the generated SearchRequest.
        """
        request = SearchRequest(self, *args, **kargs)
        request._fireEvent = True
        self._finishedEvent.clear()
        self.addRequest(request)
        self._finishedEvent.wait()
        return request
        
    def addRequest(self, request):
        """Search for *request*."""
        assert request.engine is self
        #logger.debug("Search: Got new request {}".format(request))
        self._thread.requests.put(request)

    def _handleSearchFinished(self, request):
        if not request.stopped:
            if request.callback is not None:
                request.callback(request)
            self.searchFinished.emit(request)
            
    def createResultTable(self, part, customColumns=""):
        """Create a MySQL table that can hold search results and return its (unique) name. The table will be
        created in memory. *part* will be a part of the table name and may be used to remember who created the
        table.
        
        All tables created with this method belong to this engine and will be dropped when it is shut down.
        """
        if len(customColumns) > 0 and customColumns[-1] != ',':
            customColumns = customColumns + ','
        tableName = "{}tmp_search_{}".format(db.prefix, part)
        with SearchEngine._resultTableLock:
            i = 1
            while "{}_{}".format(tableName, i) in db.listTables():
                i += 1
            tableName = "{}_{}".format(tableName, i)
            if db.type == 'mysql':
                # Do not create a temporary table, because such a table can only be accessed from the thread
                # that created it. Use ENGINE MEMORY instead.
                createQuery = """
                    CREATE TABLE {} (
                        id MEDIUMINT UNSIGNED NOT NULL,
                        {}
                        PRIMARY KEY(id))
                        ENGINE MEMORY;
                    """.format(tableName, customColumns)
            else:
                createQuery = """
                    CREATE TABLE {} (
                        id INTEGER PRIMARY KEY
                        {})
                    """.format(tableName, ','+customColumns if len(customColumns) > 0 else '')
            db.query(createQuery)
            self._tables.append(tableName)
        return tableName
    
    def shutdown(self):
        """Shut down this engine. In particular terminate the search thread and drop all result tables
        associated with this engine.
        """
        engines.remove(self)
        self._thread.quit = True
        # Wake up the thread, if it is blocking in requests.get()
        dummyRequest = SearchRequest(self, '', criteria.Criterion())
        dummyRequest.stopped = True
        self._thread.requests.put(dummyRequest)
        self._thread.join()
        self._thread = None
        for tableName in self._tables:
            db.query("DROP TABLE {}".format(tableName))


class StopRequestException(Exception):
    pass


class SearchThread(threading.Thread):
    """Each SearchEngine controls a SearchThread that does the actual searching."""
    # A reference to the search engine controlling this thread
    engine = None
    
    # This threading is used to wake the search thread when work has to be done.
    searchEvent = None
    
    # The list of search requests that have to be processed
    requests = None
    
    # This is set to True when the main thread wants the search thread to terminate.
    quit = False
    
    def __init__(self,engine):
        threading.Thread.__init__(self)
        self.daemon = True # Confer threading.Thread
        self.parentThread = threading.current_thread()
        self.engine = engine
        self.searchEvent = threading.Event()
        self.requests = queue.Queue()

    def run(self):      
        #logger.debug('Search connecting with thread {}'.format(QtCore.QThread.currentThreadId()))

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
                
                request = self.requests.get()
                if request.stopped:
                    request.result = None
                    continue
                
                try:
                    result = None
                    for criterion in request.criterion.getCriteriaDepthFirst():
                        #logger.debug("Processing criterion: ".format(criterion))
                        if not isinstance(criterion, criteria.MultiCriterion):
                            for queryData in criterion.getQueries(request.fromTable):
                                #print(queryData)
                                if isinstance(queryData, str):
                                    result = db.query(queryData)
                                else: result = db.query(*queryData)
                                #print(list(db.query("SELECT value FROM new_values_varchar WHERE id IN (SELECT value_id FROM tmp_help)").getSingleColumn()))
                                if self.quit or request.stopped:
                                    raise StopRequestException()
                            criterion.result = set(result.getSingleColumn())
                        else:
                            #TODO: implement MultiCriterions more efficiently
                            # If the first criterion in an AND-criterion returs only a small set,
                            # this could be used to make the second criterion faster.
                            if criterion.junction == 'AND':
                                method = criterion.criteria[0].result.intersection
                            else: method = criterion.criteria[0].result.union
                            criterion.result = method(*[crit.result for crit in criterion.criteria[1:]])
                            if criterion.negate:
                                allElements = set(db.query("SELECT id FROM {}elements".format(db.prefix))
                                                  .getSingleColumn())
                                criterion.result = allElements - criterion.result
                            if self.quit or request.stopped:
                                raise StopRequestException()
    
                    #logger.debug("Request finished")
                    assert criterion.result is not None
                    request.result = criterion.result
                    if request.postProcessing is not None:
                        for method in request.postProcessing:
                            method(request)
                    if request.resultTable is not None:
                        if request.resultTable == db.prefix+'elements': # don't clear elements accidentally
                            raise RuntimeError("result table must not be elements") 
                        db.transaction()
                        db.query("DELETE FROM {}".format(request.resultTable))
                        if len(request.result) > 0:
                            db.multiQuery("INSERT INTO {} (id) VALUES (?)"
                                          .format(request.resultTable), ((id,) for id in request.result))
                        db.commit()
                    self.engine._searchFinished.emit(request)
                    if request._fireEvent:
                        self.engine._finishedEvent.set()
                except StopRequestException:
                    #logger.debug("StopRequestException")
                    if request._fireEvent:
                        self.engine._finishedEvent.set()
                    continue


def findExtendedToplevel(request):
    from ..core import elements
    if len(request.result) == 0:
        request.extendedToplevel = set()
        return
    majorContainers = set(db.query(
                            "SELECT id FROM {}elements WHERE file = 0 AND type NOT IN ({}) AND id IN ({})"
                            .format(db.prefix,
                                    db.csList(elements.MAJOR_TYPES),
                                    db.csList(request.result))).getSingleColumn())
    request.extendedToplevel = request.result.difference(db.contents(majorContainers, recursive=True))
        