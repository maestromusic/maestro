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

import re

from .. import database as db, utils, config
from ..core import tags

# Initialized in search.init
SEARCH_TAGS = set()


class Criterion:
    """A criterion matches a subset of elements. The search algorithm will take a list of criteria and search
    for all elements matching every criterion. This is only an abstract base."""
    def getQuery(self,fromTable,columns=None):
        """Create a MySQL query for this criterion, selecting the columns *columns* from *fromTable*.
        *columns* must not contain table names like in ''elements.id''. Check whether this criterion is valid
        before using this method!

        This method will return a list containing the query (which may contain placeholders) and optional
        parameters that should be bound to the query such that MySQL will use them to replace the
        placeholders. Simply use::

            db.query(*criterion.getQuery(...))

        \ """

    def isInvalid(self):
        """Return whether this criterion is invalid. An invalid criterion cannot create a query and does not
        match any element."""

    def isNarrower(self,other):
        """Return whether this criterion is narrower than *other*, i.e. if the set of elements matching this
        criterion is a subset (not necessarily strict) of the set of elements matching *other*."""
        
    def getFlags(self):
        """Return the list of flags used by this criterion. When the user changes the tags of some elements,
        this is used to determine whether the result set of the criterion may have changed."""
        return []
    
    def getTags(self):
        """Return the list of tags used by this criterion. When the user changes the tags of some elements,
        this is used to determine whether the result set of the criterion may have changed."""
        return []


class TextCriterion(Criterion):
    """A TextCriterion matches if an element contains a tag ''t'' from *tagSet* and a value ''v'' for the tag
    ''t'' that contains the search string *value*. If *tagSet* is None, config.options.tags.search_tags will
    be used.

    If *tagSet* contains tags of type date they will only be searched if *value* is of the form ''1998'' or
    ''1700-1850'', where all numbers may have 1-4 digits and in the second case the first number must be less
    or equal than the second one. Note that, as usual the TextCriterion matches also if *value* is contained
    in a non-date search tag.
    
    If *tagSet* is None and value has the form [123,256,1933], the criterion will additionally match all
    elements with one of these ids.

    A TextCriterion contains the following variables:

        - ''value'': The search value.
        - ''tagSet'': a copy of *tagSet*. If *value* does not have one of the formats described above, all
          tags of type date will be removed. In this case this might be the empty set, in which case the
          criterion is invalid.
        - ''years'': If *value* is ''1999'' this will be ''(1999,None)''; if *value* is ''1600-1700'', this
          will be ''(1600,1700)'' and if *value* has none of these formats, ''years'' will be None.
        - ''ids'': A list of ids if value has the form [123,256,1933] or None otherwise.
        
    \ """
    dateRegexp = re.compile("^(\d{1,4})(-\d{1,4})?$")
    idRegexp = re.compile("^\[\d+(,\d*)*]$")
    
    def __init__(self,tagSet,value):
        if tagSet is None:
            self.tagSet = set(SEARCH_TAGS)
        elif isinstance(tagSet,tags.Tag):
            self.tagSet = set(tagSet)
        else: self.tagSet = set(tagSet)
        self.value = value

        # Compute years if value is of the form "1999" or "1990-2000"
        self.years = None
        if tags.TYPE_DATE in self.getSearchTypes():
            match = self.dateRegexp.match(self.value)
            if match is not None:
                years = match.group(1,2)
                startYear = int(years[0])
                if years[1] is None:
                    self.years = (startYear,None)
                else:
                    endYear = int(years[1][1:]) # skip the minus sign!
                    if startYear <= endYear:
                        self.years = (startYear,endYear)
                    #else: self.years = None
        if self.years is None:
            # Warning: This may result in an empty list
            self.tagSet = set(tag for tag in self.tagSet if tag.type != tags.TYPE_DATE)
            
        # Compute IDs if value is of the form [123,48]
        valueWithoutJS = ''.join(c for c in value if not c.isspace())
        if tagSet is None and self.idRegexp.match(valueWithoutJS) is not None:
            # Remove the square brackets and empty strings (value could be "12,,234")
            self.ids = [id for id in valueWithoutJS[1:-1].split(',') if len(id) > 0]
        else: self.ids = None

    def getSearchTypes(self):
        """Return the set of tag types that appear in ''tagSet''."""
        return set(tag.type for tag in self.tagSet)

    def getTags(self):
        return self.tagSet
    
    def getQuery(self,fromTable,columns):
        if len(self.tagSet) == 0:
            raise RuntimeError("Criterion {} is not valid.".format(self))
        parameters = []
        subQueries = []
        for valueType in self.getSearchTypes():
            tagIdList = ",".join(str(tag.id) for tag in self.tagSet if tag.type == valueType)
            if valueType != tags.TYPE_DATE:
                # INSTR does not respect the collation correctly: INSTR('a','ä') = 0, INSTR('ä','á') = 1
                # whereClause = "INSTR(v.value,?)"
                # Therefore we have to use LIKE '%...%' and this means escaping...
                escapedParameter = self.value.replace('\\','\\\\').replace('_','\\_').replace('%','\\%')
                whereClause = "v.value LIKE ?"
                parameters.append('%{}%'.format(escapedParameter))
            else:
                assert self.years is not None
                if self.years[1] is None:
                    whereClause = "v.value = {}".format(utils.FlexiDate(self.years[0]).toSql())
                else:
                    whereClause = "v.value BETWEEN {} AND {}".format(
                            utils.FlexiDate(self.years[0]).toSql(),
                            utils.FlexiDate(self.years[1]).endOfYearSql())
        
            subQueries.append("""
                    SELECT DISTINCT {1}
                    FROM {2} AS el JOIN {0}tags AS t ON el.id = t.element_id
                                   JOIN {0}values_{3} AS v ON t.tag_id = v.tag_id AND t.value_id = v.id
                    WHERE t.tag_id IN ({4}) AND {5}
                """.format(db.prefix,_formatColumns(columns,"el"),fromTable,
                            valueType.name,tagIdList,whereClause))

        if self.ids is not None:
            subQueries.append("(SELECT DISTINCT {0} FROM {1} AS el WHERE id IN ({2}))"
                                .format(_formatColumns(columns,"el"),fromTable,db.csList(self.ids)))
        return [" UNION ".join(subQueries)] + parameters
            

    def isNarrower(self,other):
        if not isinstance(other,TextCriterion):
            return False
        if not self.tagSet <= other.tagSet:
            return False
        # if self has ids, other must contain more
        if self.ids is not None and (other.ids is None or not set(self.ids) <= set(other.ids)):
            return False
        # Note that it is not possible to build strictly narrower queries if other.years is not None, since
        # the old string must be a substring of the new one.
        return self.years == other.years and self.value.find(other.value) > -1

    def isInvalid(self):
        return len(self.tagSet) == 0

    def __str__(self):
        if self.tagSet != SEARCH_TAGS:
            return "{}:{}".format([tag.name for tag in self.tagSet],self.value)
        else: return self.value

    def __eq__(self,other):
        return isinstance(other,TextCriterion) and other.tagSet == self.tagSet and other.value == self.value

    def __ne__(self,other):
        return not isinstance(other,TextCriterion) or other.tagSet != self.tagSet or other.value != self.value
        

class TagIdCriterion(Criterion):
    """A TagIdCriterion contains a dictionary mapping tag-ids to value-ids. It will be fulfilled for all
    elements having at least one of the tags with the corresponding value. For example
    ''{<id of genre-tag>: 1,<id of artist-tag>:2}'' will match all elements which have either the value of id
    1 as a genre-tag or the value of id 2 as an artist-tag or both.
    """
    def __init__(self,valueIds):
        """Initialize a new TagIdCriterion with the given dictionary mapping tags-ids to value-ids."""
        assert isinstance(valueIds,dict)
        self.valueIds = valueIds
        
    def getQuery(self,fromTable,columns):
        whereExpression = " OR ".join("(t.tag_id = {0} AND t.value_id = {1})".format(tagId,valueId)
                                         for tagId,valueId in self.valueIds.items())
        return ["""
            SELECT {1}
            FROM {2} AS el JOIN {0}tags AS t ON el.id = t.element_id
            WHERE {3}
            GROUP BY el.id
            """.format(db.prefix,_formatColumns(columns,"el"),fromTable,whereExpression)] # return as list!

    def getTags(self):
        """Return a list of all tags appearing in this TagIdMatch."""
        return [tags.get(tagId) for tagId in self.valueIds.keys()]
        
    def add(self,valueIds):
        """Add one or more tag=>id-mappings to this criterion. It will be fulfilled if a container contains at
        least one tag together with a value with the corresponding id."""
        self.valueIds.update(valueIds)

    def isNarrower(self,other):
        if not isinstance(other,TagIdCriterion):
            return False
        else:
            # self is narrower if and only if it contains only k,v pairs from other
            return set(self.valueIds.items()) <= set(other.valueIds.items())

    def isInvalid(self):
        return len(self.valueIds) == 0

    def __eq__(self,other):
        return isinstance(other,TagIdCriterion) and other.valueIds == self.valueIds

    def __ne__(self,other):
        return not isinstance(other,TagIdCriterion) or other.valueIds != self.valueIds

    def __str__(self):
        return "<TagIdCriterion {}>".format(self.valueIds)


class FlagsCriterion(Criterion):
    """A FlagsCriterion specifies a list of flags and depending on the parameter *useAnd* an element must
    have either all of these flags or at least one."""
    def __init__(self,flags,useAnd = True):
        self.flags = set(flags)
        assert len(self.flags) > 0
        self.useAnd = useAnd
    
    def getFlags(self):
        """Return the set of flagtypes a container must have in order to match this criterion."""
        return self.flags
    
    def isInvalid(self):
        return False
    
    def getQuery(self,fromTable,columns):
        if self.useAnd:
            return ["""
                SELECT {0}
                FROM {1}elements AS el JOIN {1}flags AS fl ON el.id = fl.element_id
                WHERE fl.flag_id IN ({2})
                GROUP BY el.id
                HAVING COUNT(fl.element_id) = {3}
                """.format(_formatColumns(columns,'el'),db.prefix,db.csIdList(self.flags),len(self.flags))]
        else: # use or
            return ["""]
                SELECT {0}
                FROM {1}elements AS el JOIN {1}flags AS fl ON el.id = fl.element_id
                WHERE fl.flag_id IN ({2})
                GROUP BY el.id
                """.format(_formatColumns(columns,'el'),db.prefix,db.csIdList(self.flags))]

    def isNarrower(self,other):
        return isinstance(other,FlagsCriterion) and self.flags <= other.flags
    
    def __eq__(self,other):
        return isinstance(other,FlagsCriterion) and self.flags == other.flags
    
    def __ne__(self,other):
        return not isinstance(other,FlagsCriterion) or self.flags != other.flags


class MissingTagCriterion(Criterion):
    """A MissingTagCriterion specifies a list of tags which an element must not have in order to match this
    criterion."""
    
    def __init__(self,tags):
        """Initialize a new MissingTagCriterion with the given set of tags."""
        self.tags = set(tags)
    
    def getTags(self):
        """Return the set of tags a container must not have in order to match this criterion."""
        return self.tags
    
    def getQuery(self,fromTable,columns):
        # return a list!
        return ["""
            SELECT {1}
            FROM {2} AS el LEFT JOIN {0}tags AS t ON el.id = t.element_id AND t.tag_id IN ({3})
            WHERE t.value_id IS NULL
            """.format(db.prefix,_formatColumns(columns,'el'),fromTable,db.csIdList(self.tags))]

    def isNarrower(self,other):
        return isinstance(other,MissingTagCriterion) and self.tags >= other.tags

    def isInvalid(self):
        return len(self.tags) == 0

    def __eq__(self,other):
        return isinstance(other,MissingTagCriterion) and self.tags == other.tags

    def __ne__(self,other):
        return not isinstance(other,MissingTagCriterion) or self.tags != other.tags


def isNarrower(aList,bList):
    """Return whether the set of elements matching each criterion in *aList* is a subset of the elements
    matching each criterion in *bList*."""
    # :-) For each b \in bList there must be an a \in aList that is narrower than b
    return all(any(a.isNarrower(b) for a in aList) for b in bList)


def getNonRedundantCriterion(criteria,processed):
    """Get the first criterion from *criteria* that is redundant on the set of elements matching the criteria
    in *processed*. A criterion is regarded redundant when it matches every element in the result set of
    *processed*. If for example *processed* contains 'hello', then 'hell' is redundant."""
    for c in criteria:
        if not any(p.isNarrower(c) for p in processed):
            return c
    return None


def _formatColumns(columns,fromTable):
    """Generate a string which can be used after SELECT and will select the given columns from the given
    table. A possible result would be "elements.id,elements.position,elements.elements"."""
    return ",".join("{0}.{1}".format(fromTable,column) for column in columns)
