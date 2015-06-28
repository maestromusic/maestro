# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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

"""
The database module establishes the database connection and provides many functions to fetch data.

The actual database drivers which connect to the database using a third party connector can be found in the
SQL package. The definitions of Maestro's tables can be found in the tables-module.

The easiest way to use this package is:

    from maestro import database as db
    db.connect()
    db.query(...)

or, if the connection was already established in another module:

    from maestro import database as db
    db.query(...)

"""

import os, threading
import datetime
import sqlalchemy

from .. import config, utils
from ..core import tags as tagsModule

type = None
prefix = None
engine = None # engine to the main database (other databases may be used during synchronization)
driver = None
tags = None # tags submodule

# Next id that will be returned by nextId() and lock to make that method threadsafe
_nextId = None
_nextIdLock = threading.Lock()


DBException = sqlalchemy.exc.DBAPIError


class EmptyResultException(Exception):
    """This exception is executed if getSingle, getSingleRow or getSingleColumn are
    performed on a result which does not contain any row.
    """


class FlexiDateType(sqlalchemy.types.TypeDecorator):
    impl = sqlalchemy.types.Integer

    def process_bind_param(self, value, dialect):
        return value.toSql()

    def process_result_value(self, value, dialect):
        return utils.FlexiDate.fromSql(value)

    def copy(self):
        return FlexiDateType()


def createEngine(**kwargs):
    """Create an SqlAlchemy-engine. Usually you should use the module-level variable 'engine'."""
    if kwargs['type'] == 'sqlite':
        url = 'sqlite:///' + kwargs['path'] # absolute paths will have 4 slashes
        def creator():
            import sqlite3, re
            connection = sqlite3.connect(kwargs['path'])
            connection.execute("PRAGMA foreign_keys = ON")
            connection.create_function('regexp', 2, lambda p, s: re.search(p, s) is not None)
            return connection
        
        return sqlalchemy.create_engine(url, creator=creator, poolclass=sqlalchemy.pool.SingletonThreadPool)
    else:
        # full url: {type}+{driver}://{user}:{password}@{host}:{port}/{name}
        # leave out driver and port parts if not specified
        url = '{type}'
        if kwargs['driver'] not in ['', None]:
            url += '+{driver}'
        url += '://{user}:{password}@{host}'
        if kwargs['port'] != 0:
            url += ':{port}'
        url += '/{name}'
        url = url.format(**kwargs)
        return sqlalchemy.create_engine(url, poolclass=sqlalchemy.pool.SingletonThreadPool)


def connect(**kwargs):
    """Return an SqlAlchemy-connection, creating the engine first if necessary. Each thread will have
    exactly one connection."""
    if engine is None:
        init()
    return engine.connect()


def init(**kwargs):
    """Initialize the database module: Create the global engine and connect to the main database using the
    information from the config file."""
    # connect to default database with args from config
    global type, prefix, engine, driver, tags
    import maestro.database.tags
    type = kwargs['type'] = kwargs.get('type', config.options.database.type)
    prefix = kwargs.get('prefix', config.options.database.prefix)
    driver = kwargs.get('driver', config.options.database.driver)
    if driver == '':
        driver = None
    # SqlAlchemy's default MySQL driver 'mysqldb' is not available for Python 3. Use mysql-connector instead.
    if type == 'mysql' and driver is None:
        driver = 'mysqlconnector'
    kwargs['driver'] = driver
    
    if type == 'sqlite':
        path = kwargs.get('path', config.options.database.sqlite_path).strip()
        print("PATH", path, kwargs.get('path'))
        # Replace 'config:' prefix in path
        if path.startswith('config:'):
            path = os.path.join(config.CONFDIR, path[len('config:'):])
        else:
            path = os.path.expanduser(path)
        kwargs['path'] = path
    else:
        args = ["user", "password", "name", "host", "port"]
        for arg in args:
            if arg not in kwargs:
                kwargs[arg] = config.options.database[arg]

    engine = createEngine(**kwargs)
    
    # Initialize nextId-stuff when the first connection is created
    with _nextIdLock:
        global _nextId
        if _nextId is None:
            try:
                _nextId = query("SELECT MAX(id) FROM {p}elements").getSingle()
                if _nextId is None: # this happens when elements is empty
                    _nextId = 1
                else: _nextId += 1    
            except DBException: # table does not exist yet (in the install tool, test scripts...)
                _nextId = 1         
    return engine


def shutdown():
    """Close database connection."""
    if type != 'sqlite':
        engine.dispose()

def nextId():
    """Reserve the next free element id and return it."""
    return nextIds(1)[0]


def nextIds(count):
    """Reserve the next *count* free element ids and return a generator containing them."""
    with _nextIdLock:
        global _nextId
        if _nextId is None:
            raise RuntimeError('Cannot create an ID before a database connection is established.')
        result = range(_nextId, _nextId+count)
        _nextId += count
        return result


def listTables():
    """Return a list of all table names in the database."""
    return engine.table_names()


def createTables():
    """Create all tables which do not exist yet."""
    from . import tables
    tables.metadata.create_all(checkfirst=True)
    
    
def query(queryString, *args, **kwargs):
    """Execute an SQL query. *queryString* may contain two kinds of placeholders:
    
        - {name}: Named arguments in braces will be replaced by the corresponding *kwargs*. One argument is
          always defined: {p} will be replaced by the database prefix.
        - '?' remain in the query and mark a place where the database needs to insert a parameter.
          The list of parameters is provided by *args* and is sent to the database separately. Thus, this
          is faster than inserting *args* into *queryString* and letting the database parse the parameters
          out of the query again. 
    
    In general you should use '?' for data and {...} to insert variable parts of the query logic.
    """
    kwargs['p'] = prefix
    queryString = queryString.format(**kwargs)
    if len(args) > 0 and driver == 'mysqlconnector':
        queryString = queryString.replace('?', '%s')
    if 'print' in kwargs:
        print(queryString, args)
    result = engine.execute(queryString, *args)
    return SqlResult(result)

def multiQuery(queryString, args, **kwargs):
    """Like 'query', but *args* is an iterable of argument list. The method will execute one query per
    argument list."""
    return query(queryString, *args, **kwargs)# = query # just submit tuples as *args

def transaction():
    """Start a database transaction."""
    return engine.begin()

def getDate(value):
    if isinstance(value, str):
        value = datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    return value.replace(tzinfo=datetime.timezone.utc)


class SqlResult:
    """Query and multiQuery return instances of this class to encapsulate SqlAlchemy ProxyResult objects.
    Be careful not to mix different access methods like getSingle, getSingleColumn and iterator methods
    (e.g. next) since they all may change internal cursors and could interfere with each other.
    """
    def __init__(self, result):
        self._result = result
            
    def __iter__(self):
        return self._result.__iter__()

    def next(self):
        """Yields the next row from the result set or raises a StopIteration if there is no such row."""
        row = self._result.fetchone()
        if row is not None:
            return row
        else: raise StopIteration()
        
    def affectedRows(self):
        """Return the number of rows affected by the query producing this AbstracSqlResult.
        This method must not be used for result sets produced by multiqueries (different drivers would return
        different values)."""
        return self._result.rowcount
    
    def insertId(self):
        """Return the last value which was used in an 'AUTO_INCREMENT'-column when this AbstractSqlResult
        was created. This method must not be used for result sets produced by multiqueries (different drivers
        would return different values)."""
        return self._result.lastrowid
    
    def getSingle(self):
        """Return the first value from the first row of the result set. Use this as a shorthand method if
        the result contains only one value. If the result set does not contain any row, an
        EmptyResultException is raised.
        """
        row = self._result.fetchone()
        if row is not None:
            return row[0]
        else: raise EmptyResultException()
        
    def getSingleColumn(self):
        """Return a generator for the first column of the result set. Use this as a shorthand method if the
        result contains only one column. Contrary to getSingeRow, this method does not raise an
        EmptyResultException if the result set is empty."""
        row = self._result.fetchone()
        while row is not None:
            yield row[0]
            row = self._result.fetchone()
        
    def getSingleRow(self):
        """Return the first row of the result set or raise an EmptyResultException if the result does
        not contain any rows. Use this as a shorthand if there is only one row in the result set."""
        row = self._result.fetchone()
        if row is not None:
            return row
        else: raise EmptyResultException()


# contents-table
#=======================================================================
def contents(elids,recursive=False):
    """Return the ids of all children of the elements with ids *elids* as a set. *elids* may be a list of
    element ids or a single id. If *recursive* is True, all descendants will be included. In any case the
    result list won't contain duplicates.
    """
    return _contentsParentsHelper(elids,recursive,"element_id","container_id")


def parents(elids,recursive=False):
    """Return a set containing the ids of all parents of the elements with ids *elids* (which may be a list
    or a single id). If *recursive* is True all ancestors will be added recursively.
    """
    return _contentsParentsHelper(elids,recursive,"container_id","element_id")


def _contentsParentsHelper(elids,recursive,selectColumn,whereColumn):
    if isinstance(elids,int):
        newSet = set([elids])
    else: newSet = set(elids)

    resultSet = set()
    while len(newSet) > 0:
        newSet = set(query("""
            SELECT {}
            FROM {}contents
            WHERE {} IN ({})
            """.format(selectColumn,prefix,whereColumn,csList(newSet))).getSingleColumn())
        if not recursive:
            return newSet
        newSet -= resultSet
        resultSet = resultSet.union(newSet)

    return resultSet


# elements-table
#=======================================================================
# def isFile(elid):
#     """Return whether the element with id *elid* exists and is a file."""
#     return query("SELECT file FROM {p}elements WHERE id = ?", elid).getSingle() == 1

# def isContainer(elid):
#     """Return whether the element with id *elid* exists and is a container."""
#     return query("SELECT file FROM {p}elements WHERE id = ?", elid).getSingle() == 0

# def isToplevel(elid):
#     """Return whether the element with id *elid* exists and is a toplevel element."""
#     return bool(query("""
#         SELECT COUNT(*)
#         FROM {p}elements AS el LEFT JOIN {p}contents AS c ON el.id = c.element_id
#         WHERE el.id = ? AND c.element_id IS NULL
#         """, elid).getSingle())
    
# def elementCount(elid):
#     """Return the number of children of the element with id *elid* or raise an EmptyResultException if
#     that element does not exist."""
#     return query("SELECT elements FROM {p}elements WHERE id = ?", elid).getSingle()

# def elementType(elid):
#     """Return the type of the element with id *elid* or raise an EmptyResultException if
#     that element does not exist."""
#     return query("SELECT type FROM {p}elements WHERE id = ?", elid).getSingle()

def updateElementsCounter(elids=None):
    """Update the elements counter.
    
    If *elids* is a list of elements-ids, only the counters of those elements will be updated. If
    *elids* is None, all counters will be set to their correct value.
    """
    if elids is not None:
        cslist = csList(elids)
        if cslist == '':
            return
        whereClause = "WHERE id IN ({})".format(cslist)
    else: whereClause = '' 
    query("""
        UPDATE {0}elements
        SET elements = (SELECT COUNT(*) FROM {0}contents WHERE container_id = id)
        {1}
        """.format(prefix, whereClause))
    

# Files-Table
#================================================
# def url(elid):
#     """Return the url of the file with id *elid* or raise an EmptyResultException if that element does
#     not exist."""
#     try:
#         return query("SELECT url FROM {p}files WHERE element_id=?", elid).getSingle()
#     except EmptyResultException:
#         raise EmptyResultException(
#                  "Element with id {} is not a file (or at least not in the files table).".format(elid))


# def hash(elid):
#     """Return the hash of the file with id *elid* or raise an EmptyResultException if that element does
#     not exist."""
#     try:
#         return query("SELECT hash FROM {p}files WHERE element_id=?", elid).getSingle()
#     except EmptyResultException:
#         raise EmptyResultException(
#                  "Element with id {} is not a file (or at least not in the files table).".format(elid))


def idFromUrl(url):
    """Return the element_id of a file from the given url.
    
    *url* must be an instance of BackendURL or an URL string. The method returns None if no file
    with that URL exists."""
    try:
        return query("SELECT element_id FROM {p}files WHERE url=?", str(url)).getSingle()
    except EmptyResultException:
        return None


# def idFromHash(hash):
#     """Return the element_id of a file from its hash, or None if it is not found."""
#     result = list(query("SELECT element_id FROM {p}files WHERE hash=?", hash))
#     if len(result) == 1:
#         return result[0][0]
#     elif len(result) == 0:
#         return None
#     else: raise RuntimeError("Hash not unique upon filenames!")


# flags table
#=======================================================================
# def flags(elid):
#     from ..core import flags
#     return [flags.get(id) for id in query(
#                     "SELECT flag_id FROM {p}flags WHERE element_id = ?", elid).getSingleColumn()]


# Help methods
#=======================================================================  
def csList(values):
    """Return a comma-separated list of the string-representation of the given values. If *values* is not
    iterable, return simply its string representation."""
    if hasattr(values,'__iter__'):
        return ','.join(str(value) for value in values)
    else: return str(values)


def csIdList(objects):
    """Return a comma-separated list of the string-representation of the ids of given *objects*. If *objects*
    is not iterable, return simply its id (assuming it is a single object) as string."""
    if hasattr(objects,'__iter__'):
        return ','.join(str(object.id) for object in objects)
    else: return str(objects.id)

