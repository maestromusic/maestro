#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from omg import database, tags

class TextQuery:
    def __init__(self,tag,value):
        self.tag = tag
        self.value = value
        
    def getDBQuery(self,containerTable,columns=None):
        if not self.tag is None:
            if self.tag in tags.list: # TODO: currently only indexed tags may be searched
                return _buildSelectForSingleTag(self.tag,self.value,containerTable,columns)
            else: raise Exception("Currently only indexed tags may be searched.")
        else:
            # Build a query to search in all tags...or to be exact: In all tags if the search-value is a number. Otherwise exclude date-tags.
            try:
                number = int(self.value)
                tagsToSearch = tags.list()
            except ValueError:
                tagsToSearch = (tag for tag in tags.list if tag.type != 'date')
        return " UNION ".join(("({0})".format(_buildSelectForSingleTag(tag,self.value,containerTable,columns))\
                                 for tag in tagsToSearch))


class TagIdQuery:
    def __init__(self,valueIds):
        self.valueIds = valueIds
        
    def getDBQuery(self,fromTable,columns=None):
        whereExpression = " OR ".join("(tags.tag_id = {0} AND tags.value_id = {1})".format(tag.id,valueId)
                                         for tag,valueId in self.valueIds.items())
        return """
            SELECT {0}
            FROM {1} JOIN tags ON {1}.id = tags.container_id
            WHERE {2}
            GROUP BY {1}.id
            """.format(_formatColumns(columns,fromTable),fromTable,whereExpression)

    def getTags(self):
        return self.valueIds.keys()
        
def _buildSelectForSingleTag(tag,value,fromTable,columns=None):
    if tag.type == 'date':
        whereExpression = " = {0}".format(value)
    else: whereExpression = " LIKE '%{0}%'".format(database.get().escapeString(value,likeStatement=True))
    return """
        SELECT {4}
        FROM {0} JOIN tags ON {0}.id = tags.container_id
                 JOIN tag_{1} ON tags.value_id = tag_{1}.id
        WHERE tags.tag_id = {2} AND tag_{1}.value {3}
        GROUP BY {0}.id
        """.format(fromTable,tag.name,tag.id,whereExpression,_formatColumns(columns,fromTable))


def _formatColumns(columns,fromTable):
    if columns is None:
        columns = ('id',)
    return ",".join("{0}.{1}".format(fromTable,column) for column in columns)
    

def sortKey(query):
    """Compute a "complexity" value for a query.
    
    This function is used to sort the complicated querys in the front hoping that we get right from the beginning only a few results. In the current implementation complexity means basically the length of the search value. This makes sense also for a second reason: MySQLs Turbo-Boyer-Moore-algorithm for queries containing "LIKE '%<search value>%' is faster for longer search values."""
    return 1 # TODO: For debugging reasons I killed the sort comparison so that queries are performed in the given order
    if isinstance(query,TagIdQuery):
        return 1000 # Just a high value to sort TagIdQueries to the front
    else: # TextQuery
        if query.tag is None:
            return len(query.value)
        else: return SINGLE_TAG_QUERY_MULTIPLIER * len(query.value)