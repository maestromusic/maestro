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

from .. import database as db
from ..core import tags

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
        

def changeUrls(data):
    """Change the urls of files by the (urlString, id) list *data*."""
    db.multiQuery("UPDATE {}files SET url=? WHERE element_id=?".format(db.prefix), data)




def setTags(elid,tags):
    """Set the tags of the element with it *elid* to the tags.Storage-instance *tags*.
    
    Removes all existing tags of that element."""
    db.query("DELETE FROM {}tags WHERE element_id = ?".format(db.prefix),elid)
    for tag in tags:
        db.multiQuery("INSERT INTO {}tags (element_id,tag_id,value_id) VALUES (?,?,?)".format(db.prefix),
                      [(elid,tag.id,db.idFromValue(tag,value,insert=True)) for value in tags[tag]])


# Used in CreateDBElementsCommand
def setFlags(elid,flags):
    """Give the element with the given id exactly the flags in the list *flags*."""
    db.query("DELETE FROM {}flags WHERE element_id = ?".format(db.prefix),elid)
    if len(flags) > 0:
        values = ["({},{})".format(elid,flag.id) for flag in flags]
        db.query("INSERT INTO {}flags (element_id,flag_id) VALUES {}".format(db.prefix,','.join(values)))

def setStickers(elid, stickers):
    """Set *stickers* on the element with *elid*, removing any previous stickers."""
    db.query("DELETE FROM {}stickers WHERE element_id = ?".format(db.prefix), elid)
    for type, values in stickers.items():
        db.multiQuery("INSERT INTO {}stickers (element_id, type, sort, data) VALUES (?, ?, ?, ?)"
                      .format(db.prefix), [(elid, type, i, val) for i, val in enumerate(values)])
