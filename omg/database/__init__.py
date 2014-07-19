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

"""
The database module establishes the database connection and provides many functions to fetch data.

The actual database drivers which connect to the database using a third party connector can be found in the
SQL package. The definitions of OMG's tables can be found in the tables-module.

The easiest way to use this package is:

    from omg import database as db
    db.connect()
    db.query(...)

or, if the connection was already established in another module:

    from omg import database as db
    db.query(...)


**Threading**

Each thread must have its own connection object. This module stores all connection objects and methods like
'query' automatically choose the correct connection. However you have to initialize the connection for
each thread and use a 'with' statement to ensure the connection is finally closed again. Typically the
'run'-method of your thread will look like this:

    from omg import database as db
    
    class MyThread(threading.Thread):
        def run(self):
            with db.connect():
                # Do stuff in your thread and use the database module as usual:
                db.query(...) # These methods will use the connection of your thread
                db.tags(...)
            # Finally the thread's connection is closed by the context manager

\ """

import os, threading
import sqlalchemy

from .. import config, utils
from ..core import tags as tagsModule

type = None
prefix = None
engine = None # engine to the main database (other databases may be used during synchronization)
driver = None

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
        return FlexiDateDecorator()



def createEngine(**kwargs):
    if kwargs['type'] == 'sqlite':
        url = 'sqlite:///'+kwargs['path'] # absolute paths will have 4 slashes
    elif kwargs['port'] == 0:
        # let SqlAlchemy figure out the default port
        url = '{type}://{user}:{password}@{host}/{name}'.format(**kwargs)
    else: url = '{type}://{user}:{password}@{host}:{port}/{name}'.format(**kwargs)
    engine = sqlalchemy.create_engine(url, poolclass=sqlalchemy.pool.SingletonThreadPool)
    return engine


def connect(**kwargs):
    return createEngine(**kwargs).connect()


def init(**kwargs):
    # connect to default database with args from config
    global type, prefix, engine, driver
    if 'type' not in kwargs:
        kwargs['type'] = config.options.database.type
    if '+' in kwargs['type']:
        type, driver = kwargs['type'].split('+')
    else: type, driver = kwargs['type'], None
    prefix = kwargs.get('prefix', config.options.database.prefix)
    
    if type == 'sqlite':
        path = kwargs.get('path', config.options.database.sqlite_path).strip()
        # Replace 'config:' prefix in path
        if path.startswith('config:'):
            path = os.path.join(config.CONFDIR, path[len('config:'):])
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
                if isNull(_nextId): # this happens when elements is empty
                    _nextId = 1
                else: _nextId += 1    
            except DBException: # table does not exist yet (in the install tool, test scripts...)
                _nextId = 1         
    return engine


def shutdown():
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






def resetDatabase():
    """Drop all tables and create them without data again. All table rows will be lost!"""
    from . import tables
    tableList = tables.sortedList()
    for table in reversed(tableList):
        if table.exists():
            query("DROP TABLE {name}", name=table.name)
    for table in tableList:
        table.create()


def createTables(ignoreExisting=False):
    """Create all tables in an empty database (without inserting any data). If *ignoreExisting* is True,
    only missing tables will be created."""
    from . import tables
    for table in tables.sortedList():
        if not ignoreExisting or not table.exists():
            table.create()


def query(queryString, *args, **kwargs):
    kwargs['p'] = prefix
    queryString = queryString.format(**kwargs)
    #print(queryString)
    #print(args)
    if len(args) > 0 and driver == 'mysqlconnector':
        queryString = queryString.replace('?', '%s')
    result = engine.execute(queryString, *args)
    return SqlResult(result)

multiQuery = query # just submit tuples as *args

def transaction():
    return engine.begin()

def isNull(value):
    return value is None

def getDate(value):
    return value.replace(tzinfo=datetime.timezone.utc)



class ArrayResult:
    def __init__(self, result):
        self.rows = result.fetchall()
        self.rowcount = result.rewcount
        self.inserted_primary_key = result.inserted_primary_key
        self._index = 0
        
    def fetchone(self):
        if self._index < len(self.rows):
            row = self.rows[self._index]
            self._index += 1
            return tuple(row)
        else: return None
        
    def __iter__(self):
        return self.rows.__iter__()
        
    
class ResultIterator:
    def __init__(self, result):
        self._iter = iter(result)
        
    def __iter__(self):
        return self
    
    def __next__(self):
        return tuple(next(self._iter))
    
class SqlResult:
    def __init__(self, result):
        self._result = result
            
    def __iter__(self):
        return ResultIterator(self._result)
        
    def __len__(self):
        return self.size()
    
    def size(self):
        """Returns the number of rows selected in a select query. You can also use the built-in
        'len'-method.
        """
        self._result = ArrayResult(self._result)
        return len(self._result.rows)
    
    def next(self):
        row = self._result.fetchone()
        if row is not None:
            return tuple(row)
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
        return self._result.inserted_primary_key
    
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
            return tuple(row)
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
def isFile(elid):
    """Return whether the element with id *elid* exists and is a file."""
    return query("SELECT file FROM {p}elements WHERE id = ?", elid).getSingle() == 1

def isContainer(elid):
    """Return whether the element with id *elid* exists and is a container."""
    return query("SELECT file FROM {p}elements WHERE id = ?", elid).getSingle() == 0

def isToplevel(elid):
    """Return whether the element with id *elid* exists and is a toplevel element."""
    return bool(query("""
        SELECT COUNT(*)
        FROM {p}elements AS el LEFT JOIN {p}contents AS c ON el.id = c.element_id
        WHERE el.id = ? AND c.element_id IS NULL
        """, elid).getSingle())
    
def elementCount(elid):
    """Return the number of children of the element with id *elid* or raise an EmptyResultException if
    that element does not exist."""
    return query("SELECT elements FROM {p}elements WHERE id = ?", elid).getSingle()

def elementType(elid):
    """Return the type of the element with id *elid* or raise an EmptyResultException if
    that element does not exist."""
    return query("SELECT type FROM {p}elements WHERE id = ?", elid).getSingle()

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
def url(elid):
    """Return the url of the file with id *elid* or raise an EmptyResultException if that element does 
    not exist."""
    try:
        return query("SELECT url FROM {p}files WHERE element_id=?", elid).getSingle()
    except EmptyResultException:
        raise EmptyResultException(
                 "Element with id {} is not a file (or at least not in the files table).".format(elid))


def hash(elid):
    """Return the hash of the file with id *elid* or raise an EmptyResultException if that element does
    not exist.""" 
    try:
        return query("SELECT hash FROM {p}files WHERE element_id=?", elid).getSingle()
    except EmptyResultException:
        raise EmptyResultException(
                 "Element with id {} is not a file (or at least not in the files table).".format(elid))


def idFromUrl(url):
    """Return the element_id of a file from the given url.
    
    *url* must be an instance of BackendURL or an URL string. The method returns None if no file
    with that URL exists."""
    try:
        return query("SELECT element_id FROM {p}files WHERE url=?", str(url)).getSingle()
    except EmptyResultException:
        return None


def idFromHash(hash):
    """Return the element_id of a file from its hash, or None if it is not found."""
    result = query("SELECT element_id FROM {p}files WHERE hash=?", hash)
    if len(result)==1:
        return result.getSingle()
    elif len(result)==0:
        return None
    else: raise RuntimeError("Hash not unique upon filenames!")


# values_* tables
#=======================================================================
_idToValue = {}
_valueToId = {}

def cacheTagValues():
    """Cache all id<->value relations from the values_varchar table."""
    for tag in tagsModule.tagList:
        if tag.type == tagsModule.TYPE_VARCHAR:
            result = query("SELECT id,value FROM {p}values_varchar WHERE tag_id = ?", tag.id)
            _idToValue[tag] = {id: value for id,value in result}
            # do not traverse result twice
            _valueToId[tag] = {value: id for id,value in _idToValue[tag].items()}
      

def valueFromId(tagSpec, valueId):
    """Return the value from the tag *tagSpec* with id *valueId* or raise an EmptyResultException if
    that id does not exist. Date tags will be returned as FlexiDate.
    """
    tag = tagsModule.get(tagSpec)
    
    # Check cache
    if tag in _idToValue:
        value = _idToValue[tag].get(valueId)
        if value is not None:
            return value
        
    # Look up value
    try:
        value = query("SELECT value FROM {}values_{} WHERE tag_id = ? AND id = ?"
                        .format(prefix, tag.type.name), tag.id,valueId).getSingle()
    except EmptyResultException:
        raise KeyError("There is no value of tag '{}' for id {}".format(tag,valueId))
                    
    # Store value in cache
    if tag.type is tagsModule.TYPE_VARCHAR:
        if tag not in _idToValue:
            _idToValue[tag] = {}
        _idToValue[tag][id] = value
    elif tag.type is tagsModule.TYPE_DATE:
        value = utils.FlexiDate.fromSql(value)
    return value


def idFromValue(tagSpec, value, insert=False):
    """Return the id of the given value in the tag-table of tag *tagSpec*. If the value does not exist,
    raise an EmptyResultException, unless the optional parameter *insert* is set to True. In that case
    insert the value into the table and return its id.
    """
    tag = tagsModule.get(tagSpec)
    value = tag.sqlFormat(value)
    
    # Check cache
    if tag in _valueToId:
        id = _valueToId[tag].get(value)
        if id is not None:
            return id

    # Look up id
    try:
        if type == 'mysql' and tag.type in (tagsModule.TYPE_VARCHAR,tagsModule.TYPE_TEXT):
            # Compare exactly (using binary collation)
            q = "SELECT id FROM {}values_{} WHERE tag_id = ? AND value COLLATE utf8_bin = ?"\
                 .format(prefix, tag.type.name)
        else: q = "SELECT id FROM {}values_{} WHERE tag_id = ? AND value = ?".format(prefix,tag.type)
        id = query(q,tag.id,value).getSingle()
    except EmptyResultException:
        if insert:
            if tag.type is tagsModule.TYPE_VARCHAR:
                searchValue = utils.strings.removeDiacritics(value)
                if searchValue == value:
                    searchValue = None
                result = query("INSERT INTO {p}values_varchar (tag_id,value,search_value) VALUES (?,?,?)",
                               tag.id, value, searchValue)
            else:
                result = query("INSERT INTO {}values_{} (tag_id, value) VALUES (?,?)"
                              .format(prefix, tag.type.name), tag.id, value)
            id = result.insertId()
        else: raise KeyError("No value id for tag '{}' and value '{}'".format(tag, value))
    
    # Store id in cache
    if tag.type is tagsModule.TYPE_VARCHAR:
        if tag not in _valueToId:
            _valueToId[tag] = {}
        _valueToId[tag][value] = id
    return id


def hidden(tagSpec, valueId):
    """Returns True iff the given tag value is set hidden."""
    tag = tagsModule.get(tagSpec)
    return query("SELECT hide FROM {}values_{} WHERE tag_id = ? AND id = ?".format(prefix, tag.type),
                 tag.id, valueId).getSingle() 


def sortValue(tagSpec, valueId, valueIfNone = False):
    """Returns the sort value for the given tag value, or None if it is not set.
    
    If *valueIfNone=True*, the value itself is returned if no sort value is set."""
    tag = tagsModule.get(tagSpec)
    ans = query("SELECT sort_value FROM {}values_{} WHERE tag_id = ? AND id = ?".format(prefix, tag.type),
                 tag.id, valueId).getSingle()
    if isNull(ans):
        ans = None
    if ans or not valueIfNone:
        return ans
    elif valueIfNone:
        return valueFromId(tag, valueId)
    
    
# tags-Table
#=======================================================================
def tags(elid):
    result = tagsModule.Storage()
    for (tagId,value) in listTags(elid):
        result.add(tagId,value)
    return result


def listTags(elid,tagList=None):
    if tagList is not None:
        if isinstance(tagList,int) or isinstance(tagList,str) or isinstance(tagList,tagsModule.Tag):
            tagid = tagsModule.get(tagList).id
            additionalWhereClause = " AND tag_id = {0}".format(tagid)
        else:
            tagList = [tagsModule.get(tag).id for tag in tagList]
            additionalWhereClause = " AND tag_id IN ({0})".format(csList(tagList))
    else: additionalWhereClause = ''
    result = query("""
                SELECT tag_id,value_id 
                FROM {}tags
                WHERE element_id = {} {}
                """.format(prefix, elid,additionalWhereClause))
    tags = []
    for tagid,valueid in result:
        tag = tagsModule.get(tagid)
        val = valueFromId(tag, valueid)
        if val is None:
            print('value for tag {} with id {} not found'.format(tag, valueid))
        else: tags.append((tag,val))
    return tags


def allTagValues(tagSpec):
    """Return all tag values in the database for the given tag."""
    tag = tagsModule.get(tagSpec)
    return query("SELECT value FROM {}values_{} WHERE tag_id = ?"
                 .format(prefix, tag.type.name), tag.id).getSingleColumn()
    

# flags table
#=======================================================================
def flags(elid):
    from ..core import flags
    return [flags.get(id) for id in query(
                    "SELECT flag_id FROM {p}flags WHERE element_id = ?", elid).getSingleColumn()]


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

