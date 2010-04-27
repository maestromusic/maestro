#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from omg import database, tags

# When deciding which criterion should be performed first, TextCriteria where tag is not None, are favored by this factor since they tend to give less results than searches in all indexed tags.
SINGLE_TAG_MULTIPLIER = 3

class TextCriterion:
    """A TextCriterion contains a tag t and a tag-value v. If t is not None the criterion is fulfilled for a container if the container has a t-tag matching v (i.e. with value equal to v if t.type is date or containing the string v otherwise). If tag is None, the TextCriterion tries all indexed tags and is fulfilled if it at least one tag matches v.
    """
    def __init__(self,tag,value):
        """Initialize this TextCriterion with the given value in the given tag. If tag is None the criterion is fulfilled if at least one tag matches the value."""
        self.tag = tag
        self.value = value
        
    def getQuery(self,fromTable,columns=None):
        """Return a SELECT-query fetching the rows of <fromTable> which fulfill this criterion. <fromTable> must contain an 'id'-column holding container-ids. By default only the id-column of <fromTable> is selected, but you can specify a list of columns in the <column>-parameter.
        """
        if self.tag is not None:
            if self.tag in tags.tagList: # TODO: currently only indexed tags may be searched
                return _buildSelectForSingleTag(self.tag,self.value,fromTable,columns)
            else: raise Exception("Currently only indexed tags may be searched.")
        else:
            # Build a query to search in all tags...or to be exact: In all tags if the search-value is a number. Otherwise exclude date-tags.
            try:
                number = int(self.value)
                tagsToSearch = tags.tagList()
            except ValueError:
                tagsToSearch = (tag for tag in tags.tagList if tag.type != 'date')
        return " UNION ".join(("({0})".format(_buildSelectForSingleTag(tag,self.value,fromTable,columns))\
                                 for tag in tagsToSearch))


class TagIdCriterion:
    """A TagIdCriterion contains a dictionary mapping tags to value-ids. It will be fulfilled for all containers having at least one of the tags with the corresponding value. For example {tags.GENRE: 1,tags.ARTIST:2} will match all containers which have either the value of id 1 (in table tag_genre) as a genre-tag or the value of id 2 (in table tag_artist) as an artist-tag or both. TagIdCriterion works only with indexed tags.
    """
    def __init__(self,valueIds):
        """Initialize a new TagIdCriterion with the given dictionary mapping tags to value-ids."""
        assert isinstance(valueIds,dict)
        self.valueIds = valueIds
        
    def getQuery(self,fromTable,columns=None):
        """Return a SELECT-query fetching the rows of <fromTable> which fulfill this criterion. <fromTable> must contain an 'id'-column holding container-ids. By default only the id-column of <fromTable> is selected, but you can specify a list of columns in the <column>-parameter.
        """
        whereExpression = " OR ".join("(tags.tag_id = {0} AND tags.value_id = {1})".format(tag.id,valueId)
                                         for tag,valueId in self.valueIds.items())
        return """
            SELECT {0}
            FROM {1} JOIN tags ON {1}.id = tags.container_id
            WHERE {2}
            GROUP BY {1}.id
            """.format(_formatColumns(columns,fromTable),fromTable,whereExpression)

    def getTags(self):
        """Return a list of all tags appearing in this TagIdMatch."""
        return self.valueIds.keys()
        
    def add(self,valueIds):
        """Add one or more tag=>id-mappings to this criterion. It will be fulfilled if a container contains at least one tag together with a value with the corresponding id."""
        self.valueIds.update(valueIds)
        

class MissingTagCriterion:
    """A MissingTagCriterion specifies a list of tags which a container must not have in order to match this criterion."""
    
    def __init__(self,tags):
        """Initialize a new MissingTagCriterion with the given list of tags."""
        self.tags = tags
    
    def getTags(self):
        """Return the list of tags a container must not have in order to match this criterion."""
        return self.tags
    
    def getQuery(self,fromTable,columns=None):
        """Return a SELECT-query fetching the rows of <fromTable> which fulfill this criterion. <fromTable> must contain an 'id'-column holding container-ids. By default only the id-column of <fromTable> is selected, but you can specify a list of columns in the <column>-parameter.
        """
        return """
            SELECT {0}
            FROM {1} LEFT JOIN tags ON {1}.id = tags.container_id AND tags.tag_id IN ({2})
            WHERE tags.value_id IS NULL
            """.format(_formatColumns(columns,fromTable),fromTable,",".join([str(tag.id) for tag in self.tags]))
            

def _buildSelectForSingleTag(tag,value,fromTable,columns=None):
    """Build a select query that will select all containers matching a given tag-value.
    
    fromTable must be the name of a database-table containing an 'id'-column which holds container-ids. The query returned by this function will select all those containers which have a tag of the sort <tag> matching <value> (i.e. if <tag>.type is date, the tag-value must equal <value>, otherwise <value> must be contained in the tag-value). By default only the id-column of <fromTable> is selected, but you can specify a list of columns in the <column>-parameter.
    """
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
    """Generate a string which can be used after SELECT and will select the given columns from the given table. A possible result would be "containers.id,containers.position,containers.elements"."""
    if columns is None:
        columns = ('id',)
    return ",".join("{0}.{1}".format(fromTable,column) for column in columns)
    

def sortKey(criterion):
    """Compute a "complexity" value for a criterion.
    
    This function is used to sort the complicated criteria in the front hoping that we get right from the beginning only a few results. In the current implementation complexity means basically the length of the search value. This makes sense also for a second reason: MySQLs Turbo-Boyer-Moore-algorithm for queries containing "LIKE '%<search value>%' is faster for longer search values."""
    return 1 # TODO: For debugging reasons I killed the sort comparison so that criteria are performed in the given order
    if isinstance(criterion,TagIdCriterion):
        return 1000 # Just a high value to sort TagIdCriteria to the front
    else: # TextCriterion
        if criterion.tag is None:
            return len(criterion.value)
        else: return SINGLE_TAG_MULTIPLIER * len(criterion.value)