# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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
:mod:`SQL package <omg.database.sql>`. The definitions of OMG's tables can be found in the
:mod:`tables-module <omg.database.tables>`.

The easiest way to use this package is::

    from omg import database as db
    db.connect()
    db.query(...)

or, if the connection was already established in another module::

    from omg import database as db
    db.query(...)


**Threading**

Each thread must have its own connection object. This module stores all connection objects and methods like
``query`` automatically choose the correct connection. However you have to initialize the connection for
each thread and use a ``with`` statement to ensure the connection is finally closed again. Typically the
``run``-method of your thread will look like this::

    from omg import database as db
    
    class MyThread(threading.Thread):
        def run(self):
            with db.connect():
                # Do stuff in your thread and use the database module as usual:
                db.query(...) # These methods will use the connection of your thread
                db.tags(...)
            # Finally the thread's connection is closed by the context manager

\ """

import os, threading, functools

from . import sql
from .. import config, logging, utils, constants
from ..core import tags as tagsModule

# Table type and prefix
type = None
prefix = None
transactionLock = threading.Lock()

logger = logging.getLogger(__name__)

# Each thread must have its own connection object. This maps thread identifiers to the connection object
connections = {}


# Next id that will be returned by nextId() and lock to make that method threadsafe
_nextId = None
_nextIdLock = threading.Lock()

# Connection and maintenance methods
#=======================================================================
class ConnectionContextManager:
    """Connection manager that ensures that connections in threads other than the main thread are closed and
    removed from the dict ``connections`` when the thread terminates.
    """
    def __enter__(self):
        return None

    def __exit__(self,exc_type, exc_value, traceback):
        close()
        return False # If the suite was stopped by an exception, don't stop that exception


def connect(**kwargs):
    """Connect to the database server with information from the config file. This method must be called 
    exactly once for each thread that wishes to access the database. If successful, it returns a
    :class:`ConnectionContextManager` that will automatically close the connection if used in a ``with``
    statement. If the connection fails, it will raise a DBException.
    
    Keyword arguments are passed to the connect-method of the new connection.
    """
    threadId = threading.current_thread().ident
    if threadId in connections:
        logger.warning(
            "database.connect has been called although a connection for this thread was already open.")
        return connections[threadId]

    global type, prefix
    type = config.options.database.type
    prefix = config.options.database.prefix
    
    if type == 'sqlite':
        # Replace 'config:' prefix in path
        path = config.options.database.sqlite_path.strip()
        if path.startswith('config:'):
            path = os.path.join(config.CONFDIR,path[len('config:'):])
        contextManager = _connect(['sqlite'],[path], **kwargs)
    else: 
        authValues = [config.options.database["mysql_"+key] for key in sql.AUTH_OPTIONS]
        contextManager = _connect(config.options.database.mysql_drivers,authValues)
    
    # Initialize nextId-stuff when the first connection is created
    with _nextIdLock:
        global _nextId
        if _nextId is None:
            _nextId = 1 + query("SELECT MAX(id) FROM {}elements".format(prefix)).getSingle()
        
    return contextManager


def _connect(drivers,authValues, **kwargs):
    """Connect to the database using the given parameters which are submitted to the connect method of the
    driver. Throw a DBException if connection fails."""
    connection = sql.newConnection(drivers)
    connection.connect(*authValues, **kwargs)
    connections[threading.current_thread().ident] = connection
    return ConnectionContextManager()
    

def close():
    """Close the database connection of this thread, if present. If you use the context manager returned by
    :func:`connect`, this method is called automatically.
    """
    threadId = threading.current_thread().ident
    if threadId in connections:
        connection = connections[threadId]
        del connections[threadId]
        connection.close()


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
    if type == 'mysql':
        return list(query("SHOW TABLES").getSingleColumn())
    else: return list(query("SELECT name FROM sqlite_master WHERE type = 'table'").getSingleColumn())
    
    
def resetDatabase():
    """Drop all tables and create them without data again. All table rows will be lost!"""
    from . import tables
    # Some tables are referenced by other tables and must therefore be dropped last and created first
    referencedTables = [table for table in tables.tables if table.name in
        [prefix+"elements",prefix+"tagids",prefix+"flag_names"]]
    otherTables = [table for table in tables.tables if table not in referencedTables]
    for table in otherTables:
        if table.exists():
            query("DROP TABLE {}".format(table.name))
    for table in referencedTables:
        table.reset()
    for table in otherTables:
        table.create()


def createTables():
    """Create all tables in an empty database (without inserting any data)."""
    from . import tables
    # Some tables are referenced by other tables and must therefore be dropped last and created first
    referencedTables = [table for table in tables.tables if table.name in
        [prefix+"elements",prefix+"tagids",prefix+"flag_names"]]
    otherTables = [table for table in tables.tables if table not in referencedTables]
    for table in referencedTables:
        table.create()
    for table in otherTables:
        table.create()


# Standard methods which are redirected to this thread's connection object (see sql.AbstractSql)
#===============================================================================================
def query(*params):
    try:
        return connections[threading.current_thread().ident].query(*params)
    except KeyError:
        raise RuntimeError("Cannot access database before a connection for this thread has been opened.")

def multiQuery(queryString,args):
    try:
        return connections[threading.current_thread().ident].multiQuery(queryString,args)
    except KeyError:
        raise RuntimeError("Cannot access database before a connection for this thread has been opened.")

def transaction():
    try:
        connections[threading.current_thread().ident].transaction()
    except KeyError:
        raise RuntimeError("Cannot access database before a connection for this thread has been opened.")

def commit():
    try:
        connections[threading.current_thread().ident].commit()
    except KeyError:
        raise RuntimeError("Cannot access database before a connection for this thread has been opened.")

def rollback():
    try:
        connections[threading.current_thread().ident].rollback()
    except KeyError:
        raise RuntimeError("Cannot access database before a connection for this thread has been opened.")

def isNull(value):
    try:
        return connections[threading.current_thread().ident].isNull(value)
    except KeyError:
        raise RuntimeError("Cannot access database before a connection for this thread has been opened.")

def getDate(value):
    try:
        return connections[threading.current_thread().ident].getDate(value)
    except KeyError:
        raise RuntimeError("Cannot access database before a connection for this thread has been opened.")

    
# contents-table
#=======================================================================
def contents(elids,recursive=False):
    """Return the ids of all children of the elements with ids *elids* as a set. *elids* may be a list of
    element ids or a single id. If *recursive* is True, all descendants will be included. In any case the
    result list won't contain duplicates.
    """
    return _contentsParentsHelper(elids,recursive,"element_id","container_id")


def parents(elids,recursive = False):
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
        newSet = newSet - resultSet
        resultSet = resultSet.union(newSet)

    return(resultSet)


# elements-table
#=======================================================================
def isFile(elid):
    """Return whether the element with id <elid> exists and is a file."""
    return query("SELECT file FROM {}elements WHERE id = ?".format(prefix),elid).getSingle() == 1

def isContainer(elid):
    """Return whether the element with id <elid> exists and is a container."""
    return query("SELECT file FROM {}elements WHERE id = ?".format(prefix),elid).getSingle() == 0

def isMajor(elid):
    """Return whether the element with id *elid* is a major element (it should be a container then)."""
    return query("SELECT major FROM {}elements WHERE id = ?".format(prefix),elid).getSingle() == 1

def isToplevel(elid):
    """Return whether the element with id <elid> exists and is toplevel element."""
    return query("SELECT toplevel FROM {}elements WHERE id = ?".format(prefix),elid).getSingle() == 1
    
def elementCount(elid):
    """Return the number of children of the element with id <elid> or raise an sql.EmptyResultException if
    that element does not exist."""
    return query("SELECT elements FROM {}elements WHERE id  ?".format(prefix),elid).getSingle()


# Files-Table
#================================================
def url(elid):
    """Return the url of the file with id *elid* or raise an sql.EmptyResultException if that element does 
    not exist."""
    try:
        return query("SELECT url FROM {}files WHERE element_id=?".format(prefix),elid).getSingle()
    except sql.EmptyResultException:
        raise sql.EmptyResultException(
                 "Element with id {} is not a file (or at least not in the files table).".format(elid))


def hash(elid):
    """Return the hash of the file with id *elid* or raise an sql.EmptyResultException if that element does
    not exist.""" 
    try:
        return query("SELECT hash FROM {}files WHERE element_id=?".format(prefix),elid).getSingle()
    except sql.EmptyResultException:
        raise sql.EmptyResultException(
                 "Element with id {} is not a file (or at least not in the files table).".format(elid))


def idFromUrl(url):
    """Return the element_id of a file from the given url.
    
    *url* must be an instance of BackendURL or an URL string. The method returns None if no file
    with that URL exists."""
    try:
        return query("SELECT element_id FROM {}files WHERE url=?".format(prefix), str(url)).getSingle()
    except sql.EmptyResultException:
        return None


def idFromHash(hash):
    """Return the element_id of a file from its hash, or None if it is not found."""
    result = query("SELECT element_id FROM {}files WHERE hash=?".format(prefix),hash)
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
            result = query("SELECT id,value FROM {}values_varchar WHERE tag_id = ?".format(prefix),tag.id)
            _idToValue[tag] = {id: value for id,value in result}
            # do not traverse result twice
            _valueToId[tag] = {value: id for id,value in _idToValue[tag].items()}
      

def valueFromId(tagSpec,valueId):
    """Return the value from the tag *tagSpec* with id *valueId* or raise an sql.EmptyResultException if
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
                        .format(prefix,tag.type.name), tag.id,valueId).getSingle()
    except sql.EmptyResultException:
        raise KeyError("There is no value of tag '{}' for id {}".format(tag,valueId))
                    
    # Store value in cache
    if tag.type is tagsModule.TYPE_VARCHAR:
        if tag not in _idToValue:
            _idToValue[tag] = {}
        _idToValue[tag][id] = value
    elif tag.type is tagsModule.TYPE_DATE:
        value = utils.FlexiDate.fromSql(value)
    return value


def idFromValue(tagSpec,value,insert=False):
    """Return the id of the given value in the tag-table of tag *tagSpec*. If the value does not exist,
    raise an sql.EmptyResultException, unless the optional parameter *insert* is set to True. In that case
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
                 .format(prefix,tag.type.name)
        else: q = "SELECT id FROM {}values_{} WHERE tag_id = ? AND value = ?".format(prefix,tag.type)
        id = query(q,tag.id,value).getSingle()
    except sql.EmptyResultException as e:
        if insert:
            result = query("INSERT INTO {}values_{} (tag_id,value) VALUES (?,?)"
                             .format(prefix,tag.type.name),tag.id,value)
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
                """.format(prefix,elid,additionalWhereClause))
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
                 .format(prefix,tag.type.name), tag.id).getSingleColumn()
    

# flags table
#=======================================================================
def flags(elid):
    from ..core import flags
    return [flags.get(id) for id in query(
                    "SELECT flag_id FROM {}flags WHERE element_id = ?".format(prefix),elid)
              .getSingleColumn()]


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

