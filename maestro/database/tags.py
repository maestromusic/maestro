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

from maestro import database as db, utils
from maestro.core import tags as tagsModule
 
_idToValue = {}
_valueToId = {}


def cacheValues():
    """Cache all id<->value relations, except for text-tags (which are mostly not displayed)."""
    for tag in tagsModule.tagList:
        if tag.type != tagsModule.TYPE_TEXT:
            values = getIdsAndValues(tag)
            _idToValue[tag] = {id: value for id, value in values}
            # do not traverse *values* twice
            _valueToId[tag] = {value: id for id,value in _idToValue[tag].items()}
      

def getIdsAndValues(tagSpec, whereClause='1', *args, **kwargs):
    tag = tagsModule.get(tagSpec)
    result = db.query("SELECT id, value FROM {} WHERE tag_id = ? AND {}".format(tag.type.table, whereClause),
                      tag.id, *args, **kwargs)
    if tag.type != tagsModule.TYPE_DATE:
        return (tuple(row) for row in result)
    else:
        return ((id, utils.FlexiDate.fromSql(date)) for id, date in result)
    

def getValues(tagSpec, whereClause='1', *args, **kwargs):
    tag = tagsModule.get(tagSpec)
    result = db.query("SELECT value FROM {} WHERE tag_id = ? AND {}".format(tag.type.table, whereClause),
                      tag.id, *args, **kwargs)
    if tag.type != tagsModule.TYPE_DATE:
        return result.getSingleColumn()
    else:
        return (utils.FlexiDate.fromSql(date) for date in result.getSingleColumn())


def value(tagSpec, valueId):
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
    values = list(getValues(tag, "id={}".format(valueId)))
    if len(values) > 0:
        value = values[0]
    else: raise KeyError("There is no value of tag '{}' for id {}".format(tag,valueId))
    
    # Store value in cache
    if tag.type != tagsModule.TYPE_TEXT:
        if tag not in _idToValue:
            _idToValue[tag] = {}
        _idToValue[tag][id] = value
    return value


def id(tagSpec, value, insert=False):
    """Return the id of the given value in the tag-table of tag *tagSpec*. If the value does not exist,
    raise an EmptyResultException, unless the optional parameter *insert* is set to True. In that case
    insert the value into the table and return its id.
    """
    tag = tagsModule.get(tagSpec)
    
    # Check cache
    if tag in _valueToId:
        id = _valueToId[tag].get(value)
        if id is not None:
            return id

    # Look up id
    if tag.type in (tagsModule.TYPE_VARCHAR, tagsModule.TYPE_TEXT) and type == 'mysql':
        whereClause = "value COLLATE utf8_bin = ?"
    else:
        whereClause = "value = ?"
    args = [tag.sqlFormat(value)]
        
    ids = list(getIdsAndValues(tag, whereClause, *args))
    if len(ids) > 0:
        id = ids[0][0]
    elif insert:
        if tag.type == tagsModule.TYPE_VARCHAR:
            columns = 'tag_id, value, search_value'
            args = [tag.id, tag.sqlFormat(value), _makeSearchValue(value)]
        else:
            columns = 'tag_id, value'
            args = [tag.id, tag.sqlFormat(value)]
        result = db.query("INSERT INTO {} ({}) VALUES ({})"
                          .format(tag.type.table, columns, ','.join(['?']*len(args))),
                          *args)
        id = result.insertId()
    else:
        raise KeyError("No value id for tag '{}' and value '{}'".format(tag, value))
    
    # Store id in cache
    if tag.type != tagsModule.TYPE_TEXT:
        if tag not in _valueToId:
            _valueToId[tag] = {}
        _valueToId[tag][value] = id
    return id


def _makeSearchValue(value):
    """Return the search value for value (may be None)."""
    searchValue = utils.strings.removeDiacritics(value)
    if searchValue == value:
        searchValue = None
    return searchValue


def deleteSuperfluousValues():
    """Remove unused entries from the values_* tables."""
    tables = set(valueType.table for valueType in tagsModule.TYPES)
    for table in tables:
        # This is complicated because we need different queries for MySQL and SQLite.
        # Neither query works in both.
        mainPart = """ FROM {1} LEFT JOIN {0}tags ON {1}.tag_id = {0}tags.tag_id
                                                 AND {1}.id = {0}tags.value_id
                    WHERE element_id IS NULL
                    """.format(db.prefix, table)
        if db.type == 'mysql':
            # Cannot use DELETE together with JOIN in SQLite
            db.query("DELETE {} {}".format(table, mainPart))
        else:
            # Cannot delete from a table used in a subquery in MySQL
            db.query("DELETE FROM {0} WHERE id IN (SELECT {0}.id {1})".format(table, mainPart))
    

def isHidden(tagSpec, valueId):
    """Returns True iff the given tag value is set hidden."""
    tag = tagsModule.get(tagSpec)
    return db.query("SELECT hide FROM {} WHERE tag_id = ? AND id = ?".format(tag.type.table),
                    tag.id, valueId).getSingle() 


def sortValue(tagSpec, valueId, valueIfNone=False):
    """Returns the sort value for the given tag value, or None if it is not set.
    
    If *valueIfNone=True*, the value itself is returned if no sort value is set."""
    tag = tagsModule.get(tagSpec)
    value, sortValue = db.query("SELECT value, sort_value FROM {} WHERE tag_id = ? AND id = ?"
                                .format(tag.type.table), tag.id, valueId).getSingleRow()
    if sortValue is not None:
        return sortValue
    elif valueIfNone:
        return value
    else: return None
    

def getStorage(elid):
    """Return a tags.Storage object filled with the tags of the element with the given id."""
    result = db.query("SELECT tag_id, value_id FROM {p}tags WHERE element_id = ?", elid)
    storage = tagsModule.Storage()
    for tagId, valueId in result:
        tag = tagsModule.get(tagId)
        storage.add(tag, value(tag, valueId))
    return storage
