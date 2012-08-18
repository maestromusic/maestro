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

import itertools

from .. import database as db
from ..core import tags


def createElements(data):
    """Creates elements in the database and returns their IDs.
    
    The argument *data* must be a list of
        (file, toplevel, elementcount, major)
    tuples specifying the new elements.
    """
    queryString = "INSERT INTO {}elements (file, toplevel, elements, major)\
                          VALUES (?,?,?,?)".format(db.prefix)
    if len(data) > 1:
        db.multiQuery(queryString, data[:-1])
    last = db.query(queryString, *data[-1]).insertId()
    first = last - len(data) + 1
    return list(range(first, last+1))


def createElementsWithIds(data):
    """Creates elements in the database with predefined IDs.
    
    The argument *data* must be a list of
        (id, file, toplevel, elementcount, major)
    tuples that specify the elements.
    """
    db.multiQuery("INSERT INTO {}elements (id, file,toplevel, elements, major)\
                          VALUES (?,?,?,?,?)".format(db.prefix), data)                       


def addFiles(data):
    """Adds entries to the files table.
    
    The files to add are specified by *data*, a list of
        (id, urlString, hash, length)
    tuples.
    """
    if len(data) == 0:
        return
    db.multiQuery("INSERT INTO {}files (element_id, url, hash, length) VALUES(?,?,?,?)"
                  .format(db.prefix), data)


def deleteElements(ids):
    """Delete the elements with the given ids from the database.
    
    Also updates element counters and toplevel flags. Due to the foreign keys in the database,
    this will delete all tag, flag and content relations of the deleted elements.
    """
    if len(ids) == 0:
        return
    parentIds = db.parents(ids)
    contentsIds = db.contents(ids)
    db.query("DELETE FROM {}elements WHERE id IN ({})".format(db.prefix, db.csList(ids)))
    updateElementsCounter(parentIds)
    updateToplevelFlags(contentsIds)


def addContents(data):
    """Add content relations to the database without touching existing ones.
    
    The *data* arguments is a list of
        (parentID, position, elementID)
    tuples.
    """
    if len(data) > 0:
        db.multiQuery("INSERT INTO {}contents (container_id, position, element_id) VALUES (?,?,?)"
                      .format(db.prefix), data)

def setContents(elid, contents):
    """Set contents of element with id *elid* to *contents* (instance of elements.ContentList)."""
    db.query("DELETE FROM {}contents WHERE container_id = ?".format(db.prefix), elid)
    db.multiQuery("INSERT INTO {}contents (container_id, position, element_id) VALUES(?,?,?)"
             .format(db.prefix), [(elid, pos, id) for (pos, id) in contents.items() ]) 

def removeContents(data):
    """Remove content relations from  elements.
    
    The argument is a list of
        (parentID, position)
    tuples.
    """
    db.multiQuery("DELETE FROM {}contents WHERE container_id = ? AND position = ?"
                   .format(db.prefix), data)


def removeAllContents(ids):
    """Remove *all* content relations of parents specidiefd by *ids*."""
    db.multiQuery("DELETE FROM {}contents WHERE container_id = ?".format(db.prefix), [(id,) for id in ids])


def changePositions(parentID, changes):
    """Change the positions of children of the element with ID *parentID*.
    
    The *changes* must be given by means of a list of (oldPos, newPos) tuples.
    """
    #  The operation is split in two parts to avoid errors caused by DB uniqueness constraints.
    changesOne = [ (newPos, parentID, oldPos)
                    for (oldPos, newPos) in sorted(changes, key=lambda cng: cng[1], reverse=True)
                    if newPos > oldPos ]
    changesTwo = [ (newPos, parentID, oldPos)
                    for (oldPos, newPos) in sorted(changes, key=lambda chng: chng[1])
                    if newPos < oldPos ]
    for data in changesOne, changesTwo:
        db.multiQuery("UPDATE {}contents SET position=? WHERE container_id=? AND position=?"
                      .format(db.prefix), data)


def updateElementsCounter(elids=None):
    """Update the elements counter.
    
    If *elids* is a list of elements-ids, only the counters of those elements will be updated. If
    *elids* is None, all counters will be set to their correct value.
    """
    if elids is not None:
        cslist = db.csList(elids)
        if cslist == '':
            return
        whereClause = "WHERE id IN ({})".format(cslist)
    else: whereClause = '' 
    db.query("""
        UPDATE {0}elements
        SET elements = (SELECT COUNT(*) FROM {0}contents WHERE container_id = id)
        {1}
        """.format(db.prefix, whereClause))
        
        
def updateToplevelFlags(elids=None):
    """Update the toplevel flags.
    
    If *elids* is a list of elements-ids, the flags of those elements will be updated. If *elids*
    is None, all flags will be set to their correct value.
    """
    if elids is not None:
        cslist = db.csList(elids)
        if cslist == '':
            return
        whereClause = "WHERE id IN ({})".format(cslist)
    else: whereClause = '' 
    db.query("""
        UPDATE {0}elements
        SET toplevel = (NOT id IN (SELECT element_id FROM {0}contents))
        {1}
        """.format(db.prefix,whereClause))


def changeUrls(data):
    """Change the urls of files by the (id, urlString) list *data*."""
    db.multiQuery("UPDATE {}files SET url = ? WHERE element_id = ?".format(db.prefix), data)


def makeValueIDs(data):
    """Ensures that tag values are present in values_* tables.
    
    *data* must be a list of (*tag*, *value*) tuples.
    """
    valuesToAdd = {}
    for tag, value in data:
        try:
            db.idFromValue(tag, value)
        except KeyError:
            if tag.type not in valuesToAdd:
                valuesToAdd[tag.type] = set()
            valuesToAdd[tag.type].add((tag.id, tag.type.sqlFormat(value)))
    for valueType, values in valuesToAdd.items():
        values = list(values)
        queryString = "INSERT INTO {}values_{} (tag_id, value) VALUES (?,?)".format(db.prefix,valueType.name)
        if len(values) > 1:
            db.multiQuery(queryString, values[:-1])
        lastId = db.query(queryString, *(values[-1])).insertId()

        # Update cache
        if valueType == tags.TYPE_VARCHAR:
            for id, (tagId, value) in enumerate(values,start=lastId-len(values)+1):
                db._idToValue[tags.get(tagId)][id] = value
                db._valueToId[tags.get(tagId)][value] = id


def addTagValuesById(elids, tag, valueIds):
    """Add tag values given by their valueIDs to some elements.
    
    *elids* is either a single id or a list of ids, *tag* is the affected tag and *valueIds* is a
    list of values-ids for *tag*.
    
    This method does not check for duplicates!
    """
    if not hasattr(elids,'__iter__'):
        elids = [elids]
    db.multiQuery("INSERT INTO {}tags (element_id,tag_id,value_id) VALUES (?,{},?)"
                   .format(db.prefix,tag.id),
                   itertools.product(elids,valueIds))


def addTagValues(elids, tag, values):
    """Add tag values to some elements.
    
    *elids* is either a single id or a list of ids, *tag* is the affected tag and *values* is a
    list of values. If a value does not already exist in the database, it will be inserted.
    
    This method does not check for duplicates!
    """
    addTagValuesById(elids,tag,[db.idFromValue(tag,value,insert=True) for value in values])
    
    
def removeTagValuesById(elids, tag, valueIds):
    """Remove some values of one tag from some elements.
    
    *elids* is either a single id or a list of ids,
    *tag* is the affected tag, *valueIds* is a list of value-ids of *tag*.
    """
    db.query("DELETE FROM {}tags WHERE element_id IN ({}) AND tag_id = {} AND value_id IN ({})"
                .format(db.prefix,db.csList(elids),tag.id,db.csList(valueIds)))


def removeTagValues(elids, tag, values):
    """Remove tag values from some elements.
    
    *elids* is either a single id or a list of ids, *tag* is the affected tag and *values* is a
    list of values.
    """
    removeTagValuesById(elids,tag,[db.idFromValue(tag,value) for value in values])
   

def changeTagValueById(elids, tag, oldId, newId):
    """Change a tag value in some elements.
    
    *elids* is either a single id or a list of ids, *tag* is the affected tag, *oldId* and *newId*
    are the ids of the old and new value, respectively.
    """
    db.query("UPDATE {}tags SET value_id = ? WHERE element_id IN ({}) AND tag_id = ? AND value_id = ?"
               .format(db.prefix,db.csList(elids)),newId,tag.id,oldId)


def changeTagValue(elids, tag, oldValue, newValue):
    """Change a tag value in some elements.
    
    *elids* is either a single id or a list of ids, *tag* is the affected tag, *oldValue* and
    *newValue* are the old and new value, respectively. If the new value does not already exist
    in the database, it will be created.
    """
    oldId = db.idFromValue(tag,oldValue)
    newId = db.idFromValue(tag,newValue,insert=True)
    changeTagValueById(elids,tag,oldId,newId)


def setTags(elid,tags):
    """Set the tags of the element with it *elid* to the tags.Storage-instance *tags*.
    
    Removes all existing tags of that element."""
    db.query("DELETE FROM {}tags WHERE element_id = ?".format(db.prefix),elid)
    for tag in tags:
        db.multiQuery("INSERT INTO {}tags (element_id,tag_id,value_id) VALUES (?,?,?)".format(db.prefix),
                      [(elid,tag.id,db.idFromValue(tag,value,insert=True)) for value in tags[tag]])


def setSortValue(tag, valueId, sortValue):
    """Set the sort-value of the value of *tag* with id *valueId* to *sortValue*."""
    db.query("UPDATE {}values_{} SET sort_value = ? WHERE tag_id = ? AND id = ?".
             format(db.prefix, tag.type), sortValue, tag.id, valueId)


def setHidden(tagSpec, valueId, state):
    """Set the given tag value's "hidden" attribute to *state*."""
    tag = tags.get(tagSpec)
    db.query("UPDATE {}values_{} SET hide = ? WHERE tag_id = ? AND id = ?".format(db.prefix, tag.type),
             state, tag.id, valueId) 


def addFlag(elids,flag):
    """Add the given flag to the elements with the given ids.
    
    Ignores elements that already have the flag set.
    """
    values = ','.join('({},{})'.format(elid,flag.id) for elid in elids)
    db.query("REPLACE INTO {}flags (element_id,flag_id) VALUES {}".format(db.prefix,values))
    
    
def removeFlag(elids,flag):
    """Remove a flag from the elements with the specified ids.
    
    Ignores elements that do not have the flag.
    """
    db.query("DELETE FROM {}flags WHERE flag_id = {} AND element_id IN ({})"
                .format(db.prefix,flag.id,db.csList(elids)))


def addFlags(data):
    """Add entries to the flags table.  *data* is a list of (elementid, flagid) tuples."""
    db.multiQuery("INSERT INTO {}flags (element_id,flag_id) VALUES (?,?)".format(db.prefix), data)
    
    
def removeFlags(data):
    """Remove entries from the flags table. *data* is a list of (elementid, flagid) tuples."""
    db.multiQuery("DELETE FROM {}flags WHERE flag_id = ? AND element_id = ?"
                .format(db.prefix), data)
    

def setFlags(elid,flags):
    """Give the element with the given id exactly the flags in the list *flags*."""
    db.query("DELETE FROM {}flags WHERE element_id = ?".format(db.prefix),elid)
    if len(flags) > 0:
        values = ["({},{})".format(elid,flag.id) for flag in flags]
        db.query("INSERT INTO {}flags (element_id,flag_id) VALUES {}".format(db.prefix,','.join(values)))

def setData(elid, data):
    """Set *data* on the element with *elid*, removing any previous data."""
    db.query("DELETE FROM {}data WHERE element_id = ?".format(db.prefix), elid)
    for type, values in data.items():
        db.multiQuery("INSERT INTO {}data (element_id, type, sort, data) VALUES (?, ?, ?, ?)"
                      .format(db.prefix), [(elid, type, i, val) for i, val in enumerate(values)])

def setMajor(data):
    """Changes the "major" flag of elements. *data* is a list of (id, newMajor) tuples."""
    db.multiQuery("UPDATE {}elements SET major = ? WHERE id = ?".format(db.prefix), [(b,a) for a,b in data])
    
