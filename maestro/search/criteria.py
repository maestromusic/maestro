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

import re
import pyparsing
from pyparsing import Optional, MatchFirst, Suppress, CharsNotIn, Word
from pyparsing import Literal, Combine, ZeroOrMore, Group, Forward, OneOrMore

from .. import database as db, utils
from ..core import tags, flags

PREFIX_NEGATE = '!'
PREFIX_BINARY = '_'
PREFIX_SINGLE_WORD = '#'

# Abbreviations for tags which may be used in queries #TODO make these configurable
TAG_ABBREVIATIONS = {"t": "title",
                     "a": "artist",
                     "c": "composer",
                     "p": "performer",
                     "g": "genre",
                     "d": "date"
                     }  

MAX_MATCHING_TAGS = 20 # Maximum number of "matching tags" (feature is disabled if more tags match)


class ParseException(Exception):
    """This exceptions is raised when a search string is ill-formatted."""
    pass


def parse(string):
    """Parse a string into a criterion. If the string is ill-formatted, raise a ParseException."""
    words = parseToWords(string)
    return parseWords(words)
    
    
def _nestedExpr():
    """Return a pyparsing.ParserElement that defines the main search string syntax."""
    ignoreExpr = pyparsing.dblQuotedString
    splitChars = '(){}|'+pyparsing.ParserElement.DEFAULT_WHITE_CHARS
    
    word = Combine(OneOrMore(ignoreExpr | CharsNotIn(splitChars)))
    braces = Combine(Optional(PREFIX_NEGATE)+'{'+ZeroOrMore( CharsNotIn('}') | ignoreExpr ) + '}')
    brackets = Forward()
    
    content = ZeroOrMore( brackets | braces | '|' | word )
    brackets << Group( Suppress('(') + content + Suppress(')') )
    return Group(content)


def parseToWords(string):
    """Split string into 'words', using nested lists to handle parentheses. Most 'words' will be parsed
    into a criterion later (e.g. 'search', '"white space"', '{flag=test}', etc.). The exceptions are the
    operators '|' and PREFIX_NEGATE.
    """
    try:
        parsed = _nestedExpr().parseString(string, parseAll=True).asList()
    except pyparsing.ParseException as e:
        raise ParseException(str(e))
    while len(parsed) == 1 and isinstance(parsed[0], list):
        parsed = parsed[0]
    return parsed


def parseWords(wordOrList):
    """Parse a string or a list of nested lists and strings into a single Criterion. Transform lists into
    MultiCriterion-instances using AND and - where the operator '|' is used - 'OR'.
    
    To parse each single string call all functions in 'outerParser' with this string until one of them
    returns a Criterion.
    
    Return None if the list is empty.
    """
    if isinstance(wordOrList, str):
        negate = wordOrList.startswith('!')
        if negate:
            wordOrList = wordOrList[1:]
        for parseFunction in parsers:
            try:
                criterion = parseFunction(wordOrList)
            except ParseException as e:
                raise ParseException("Exception during parsing '{}': {}".format(wordOrList, str(e)))
            if criterion is not None:
                criterion.negate = negate
                return criterion
        else:
            raise ParseException("Could not parse '{}'".format(wordOrList))
    else:
        if len(wordOrList) == 0:
            return None
        crits = [combine('AND', list(_negatingGenerator(l))) for l in _splitList('|', wordOrList)]
        return combine('OR', crits)
       
       
def _negatingGenerator(aList):
    """Yield criteria from the items in *aList* (strings or lists). If an item is PREFIX_NEGATE, negate
    the next criterion."""
    it = iter(aList)
    while True:
        item = next(it) # this will eventually raise StopIteration and finish the generator
        if item == PREFIX_NEGATE:
            try:
                item = next(it)
            except StopIteration:
                raise ParseException("'{}' must be followed by a criterion.".format(PREFIX_NEGATE))
            negate = True
        else: negate = False
        criterion = parseWords(item)
        if criterion is not None:
            if negate:
                criterion.negate = not criterion.negate
            yield criterion


def combine(junction, criteriaList):
    """Return a MultiCriterion using the specified *junction* and criteria. If *criteriaList* contains only a
    single criterion, return it instead."""
    if len(criteriaList) == 0:
        return None
    if len(criteriaList) == 1:
        return criteriaList[0]
    else: return MultiCriterion(junction, criteriaList)


class Criterion:
    """A criterion matches a subset of elements.
    This abstract base class has only one attribute 'negate'. If it is set to True, the Criterion matches
    exactly the opposite set of elements.
    The search algorithm will expect a single Criterion-instance for the search, so you must use
    MultiCriterion to build complicated queries. This can be achieved using the operators 'and' and 'or'.
    """
    negate = False
    
    def isUsingTag(self, tag):
        """Return whether this criterion uses the given tag, i.e. whether the result may change when this
        tag is changed in some elements."""
        return False
    
    def isUsingFlag(self, flag):
        """Return whether this criterion uses the given flag, i.e. whether the result may change when this
        flag is changed in some elements."""
        return False
    
    def isUsingSticker(self, stickerType):
        """Return whether this criterion uses the given sticker type, i.e. whether the result may change
        when stickers of this type are changed in some elements."""""
        return False
    
    def __and__(self, other):
        return MultiCriterion('AND', [self, other])
    
    def __or__(self, other):
        return MultiCriterion('OR', [self, other])
    
    def getCriteriaDepthFirst(self):
        """Return all criteria contained in this one in depth-first manner."""
        yield self
        
    def process(self, fromTable, domain):
        """Process this criterion: Search all elements belonging to *domain* and whose id is in the 'id'
        column of *fromTable* (usually 'elements') and which match this criterion. Store the ids of those
        elements in self.result.
        For complicated criteria this method should be implemented as a generator which yields between
        major steps. This allows the browser to abort the search (e.g. when the user has typed a new
        criterion in the mean time).
        """
        raise NotImplementedError()
    
    def getMatchingTags(self):
        """Return a list of (tagId, valueId)-tuples that match this criterion directly. Return None if
        such a list does not exist for this criterion (e.g. because it has nothing to do with tags).
        
        This feature allows the browser to render tag values which match directly in bold font.
        """
        return None


class MultiCriterion(Criterion):
    """A MultiCriterion connects several criteria via a logical operator. The operator is specified by
    junction, which must be either 'AND' or 'OR'. Note that you can create MultiCriteria using the Python
    operators 'and' and 'or'.
    """
    def __init__(self, junction, criteria):
        assert junction in ('AND', 'OR')
        assert len(criteria) > 1
        self.junction = junction
        self.criteria = criteria
            
    def __repr__(self):
        parts = []
        # Note that this method only encloses the criterion in parentheses if it is negated: "!(a b)"
        # Therefore we have to enclose child-MultiCriteria here
        for criterion in self.criteria:
            if not isinstance(criterion, MultiCriterion) or criterion.negate:
                parts.append(repr(criterion))
            else: parts.append('({})'.format(repr(criterion)))
        
        separator = ' ' if self.junction == 'AND' else ' | '
        if self.negate:
            return PREFIX_NEGATE + '({})'.format(separator.join(parts))
        else: return separator.join(parts)
    
    def __eq__(self, other):
        return isinstance(other, MultiCriterion) and other.junction == self.junction \
                and other.criteria == self.criteria and other.negate == self.negate
                
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def getCriteriaDepthFirst(self):
        for criterion in self.criteria:
            for c in criterion.getCriteriaDepthFirst():
                yield c
        yield self
        
    def getMatchingTags(self):
        if self.negate:
            return None # not implemented
        matchingTags = None
        # Find first set returned by a criterion
        i = 0
        while i < len(self.criteria) and matchingTags is None:
            matchingTags = self.criteria[i].getMatchingTags()
            i += 1
        if matchingTags is not None:
            # Merge / intersect all sets from the other criteria
            for criterion in self.criteria[i:]:
                m = criterion.getMatchingTags()
                if m is not None:
                    if self.junction == 'AND':
                        matchingTags.intersection(m)
                        if len(matchingTags) == 0: # skip other criteria
                            return []
                    else:
                        matchingTags.update(m)
        return matchingTags
        
        
class ElementTypeCriterion(Criterion):
    """Match only containers or files, depending on *type* ('container' or 'file').""" 
    def __init__(self, type):
        assert type in ('container', 'file')
        self.type = type
        
    def __repr__(self):
        return _negHelper(self, '{'+self.type+'}')
    
    def __eq__(self, other):
        return isinstance(other, ElementTypeCriterion) and other.type == self.type \
                and other.negate == self.negate
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def process(self, fromTable, domain):
        value = self.type == 'file'
        if self.negate:
            value = not value
        if fromTable == db.prefix + 'elements':
            query = "SELECT id FROM {p}elements AS el"
        else: query = "SELECT id FROM {table} JOIN {p}elements AS el USING(id)"
        # Add where clause
        query += " WHERE el.file={}".format(int(value))
        if domain is not None:
            query += " AND el.domain={}".format(domain.id)
        self.result = set(db.query(query, table=fromTable).getSingleColumn())
    
    @staticmethod
    def parse(string):
        """Parse either {container} or {file}."""
        key, operator, data = _splitBracedCriterion(string)
        if key in ('container', 'file'):
            if data is None:
                return ElementTypeCriterion(key)
            else: raise ParseException("Invalid ElementTypeCriterion")
        else: return None
    
    
class IdCriterion(Criterion):
    """Matches elements whose id is in the given interval or list of ids. Exactly one argument must be given.
    """
    def __init__(self, interval=None, idList=None):
        if interval is not None:
            assert idList is None
            if not isinstance(interval, Interval) or not interval.isValid():
                raise ValueError("IdCriterion: interval argument must be a valid Interval-instance.")
        else:
            assert idList is not None
            if len(idList) == 0:
                raise ValueError("IdCriterion: idList must be non-empty")
        self.interval = interval
        self.idList = idList
        
    def __repr__(self):
        if self.interval is not None:
            return _negHelper('{id'+interval.toString(includeOperator=True)+'}')
        else:
            ids = ','.join(str(id) for id in self.idList)
            return _negHelper(self, '{id='+'ids'+'}')
    
    def __eq__(self, other):
        return isinstance(other, IdCriterion) and other.interval == self.interval \
                and other.idList == self.idList and other.negate == self.negate
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def process(self, fromTable, domain):
        if fromTable == db.prefix+"elements" or domain is None:
            query = "SELECT el.id FROM {table} AS el WHERE "
        else: query = "SELECT el.id FROM {table} JOIN {p}elements AS el WHERE "
        if domain is not None:
            query += "el.domain={} AND ".format(domain.id)
        if self.negate:
            query += "NOT "
        if self.interval is not None:
            query += '(el.id {})'.format(self.interval.queryPart())
        else: query += 'el.id IN ({})'.format(db.csList(self.idList))
        self.result = set(db.query(query, table=fromTable).getSingleColumn())
    
    @staticmethod
    def parse(string):
        """Parse e.g. {id=100-150}, {id>=2000} or {id=2,3,5,7}."""
        key, operator, data = _splitBracedCriterion(string)
        if key == 'id':
            if operator is None:
                raise ParseException("Invalid IdCriterion")
            interval = Interval.parse(operator, data)
            if interval is not None:
                if interval.isValid():
                    return IdCriterion(interval=interval)
                else: raise ParseException("IdCriterion's interval must be valid.")
            elif operator == '=':
                try:
                    idList = [int(v) for v in data.split(',')]
                except ValueError:
                    pass
                else: return IdCriterion(idList=idList)        
            raise ParseException("IdCriterion needs a valid interval or id-list.")
        else: return None
        
        
class AnyCriterion(Criterion):
    """Matches elements which have at least one tag, flag or sticker, depending on *type* ('tag', 'flag',
    or 'sticker'."""
    def __init__(self, type):
        assert type in ('tag', 'flag', 'sticker')
        self.type = type
        
    def __repr__(self):
        return _negHelper(self, '{'+self.type+'}')
    
    def __eq__(self, other):
        return isinstance(other, AnyCriterion) and other.type == self.type and other.negate == self.negate
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def isUsingTag(self):
        return self.type == 'tag'
    
    def isUsingFlag(self):
        return self.type == 'flag'
    
    def isUsingSticker(self):
        return self.type == 'sticker'
    
    def process(self, fromTable, domain):
        # fortunately there's only one common method to build a plural in English...
        joinTable = db.prefix + self.type + 's'
        if not self.negate:
            query = "SELECT DISTINCT id FROM {table} AS el JOIN {join} AS j ON el.id = j.element_id WHERE 1"
        else: query = "SELECT id FROM {table} AS el LEFT JOIN {join} AS j ON el.id = j.element_id "\
                      "WHERE j.element_id IS NULL"
        if domain is not None:
            query += " AND el.domain={}".format(domain.id)
        self.result = set(db.query(query, table=fromTable, join=joinTable).getSingleColumn())
    
    @staticmethod
    def parse(string):
        """Parse {tag}, {flag}, {sticker}."""
        key, operator, data = _splitBracedCriterion(string)
        if key in ('tag', 'flag', 'sticker') and data is None:
            return AnyCriterion(key)
        else: return None

            
class AnyTagCriterion(Criterion):
    """Search for elements that have at least one value in one tag of *tagList*. At least one tag must
    be specified.
    """
    def __init__(self, tagList):
        assert len(tagList) > 0
        self.tagList = tagList
        
    def isUsingTag(self, tag):
        return tag in self.tagList
    
    def __eq__(self, other):
        return type(other) is type(self) and other.tagList == self.tagList and other.negate == self.negate
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def __repr__(self):
        return '{tag='+','.join(tag.name for tag in self.tagList)+'}'
        
    def __repr__(self):
        tagNames = ','.join(tag.name for tag in self.tagList)
        return _negHelper(self, '{tag='+tagNames+'}')
    
    def process(self, fromTable, domain):
        joinClause = "{}tags AS t ON el.id = t.element_id AND t.tag_id IN ({})"\
                        .format(db.prefix, db.csIdList(self.tagList))
        domainWhereClause = "domain={}".format(domain.id) if domain is not None else '1'
        if not self.negate:
            query = "SELECT DISTINCT id FROM {table} AS el JOIN {join} WHERE {domain}"
        else: query = "SELECT id FROM {table} AS el LEFT JOIN {join}"\
                            " WHERE {domain} AND t.element_id IS NULL"
        self.result = set(db.query(query, table=fromTable, join=joinClause, domain=domainWhereClause)
                            .getSingleColumn())

    @staticmethod
    def parse(string):
        """Parse e.g. {tag=date,comment}."""
        key, operator, content = _splitBracedCriterion(string)
        if key == 'tag':
            if operator == '=':
                try:
                    tagList = _parseTagList(content)
                    return AnyTagCriterion(tagList)
                except ParseException:
                    return None # let AbstractParseCriterion.parse handle this. E.g. {tag=artist=B}
            elif operator is None: # '{tag}'; use AnyCriterion instead
                return None
            else:
                raise ParseException("Invalid AnyTagCriterion")
        else: return None


class AbstractTagCriterion(Criterion):
    """This abstract super class provides common functions for TagCriterion and DateCriterion. Note that
    'process' can search for texts (self.value; in varchar- or text-tags) and date-intervals (self.interval;
    for date-tags). A search-string like "1799" will be parsed to a DateCriterion having set both
    self.value and self.interval, leading to both a date-search and a text-search.
    """
    
    # Name of the temporary search table
    # The table is created in the search thread and temporary, so that it does not conflict with other threads.
    HELP_TABLE = db.prefix + "tmp_help" 
    
    def process(self, fromTable, domain):
        # Prepare help table
        #===================
        if not db.engine.dialect.has_table(db.engine.connect(), self.HELP_TABLE):
            from sqlalchemy import MetaData, Integer, Table, Column, Index
            metadata = MetaData(db.engine)
            helpTable = Table(self.HELP_TABLE, metadata,
                Column('value_id', Integer, nullable=False), 
                Column('tag_id', Integer, nullable=False),     
                Index('value_id', 'tag_id'),
                prefixes=['TEMPORARY']  
            )
            helpTable.create()
        else:
            if db.type == 'mysql':
                # truncate may be much faster than delete http://dev.mysql.com/doc/refman/5.6/en/delete.html
                db.query("TRUNCATE {}".format(self.HELP_TABLE))
            else: db.query("DELETE FROM {}".format(self.HELP_TABLE))
        
        # Select matching values and put them into help table
        #====================================================
        pragmaNecessary = False
        for valueType in tags.TYPES:
            whereClauses = []
            args = []
            
            # Filter tag type
            if self.tagList is not None:
                tagList = [tag for tag in self.tagList if tag.type == valueType]
                if len(tagList) == 0:
                    continue # no search for this valueType
                else: whereClauses.append("tag_id IN ({})".format(db.csIdList(tagList)))
            
            # Filter values
            if valueType == tags.TYPE_VARCHAR:
                if self.value is None: # may happen for DateCriterion
                    continue
                if self.binary:
                   value = self.value
                else: value = utils.strings.removeDiacritics(self.value) 
                if db.type == 'mysql':
                    if not self.singleWord:
                        if self.binary:
                            whereClauses.append('INSTR(value, BINARY ?)')
                        else: whereClauses.append("INSTR(COALESCE(search_value, value), ?)")
                        args.append(value)
                    else:
                        if self.binary:
                            whereClauses.append('value REGEXP BINARY ?') # case-sensitive
                        else: whereClauses.append('COALESCE(search_value, value) REGEXP ?')
                        args.append('[[:<:]]{}[[:>:]]'.format(re.escape(value)))
                        
                else: # SQLite
                    if not self.singleWord:
                        if self.binary:
                            # INSTR exists only in SQLite 3.7.15 and later
                            pragmaNecessary = True
                            db.query('PRAGMA case_sensitive_like = 1')
                            whereClauses.append("value LIKE ?")
                        else: whereClauses.append("COALESCE(search_value, value) LIKE ?")
                        args.append('%{}%'.format(self._escapeParameter(value)))
                    else:
                        if self.binary:
                            whereClauses.append("value REGEXP ?")
                            args.append('\\b{}\\b'.format(re.escape(value)))
                        else:
                            whereClauses.append("COALESCE(search_value, value) REGEXP ?")
                            args.append('(?i)\\b{}\\b'.format(re.escape(value)))
                
            elif valueType == tags.TYPE_TEXT:
                if self.tagList is None:
                    continue # don't search for text tags unless explicitly specified
                whereClauses.append("value LIKE ?")
                args.append('%{}%'.format(self._escapeParameter(self.value)))
                
            elif valueType == tags.TYPE_DATE:
                if self.interval is None:
                    continue # can't search for dates without an interval
                whereClauses.append("value " + self.interval.toDateSql().queryPart()) 
            #perf = time.perf_counter()
            db.query("""
                    INSERT INTO {help} (value_id, tag_id)
                        SELECT id, tag_id
                        FROM {table}
                        WHERE {where}
                    """, *args,
                    help=self.HELP_TABLE, table=valueType.table,
                    where=' AND '.join(whereClauses) if len(whereClauses) > 0 else '1')
            #print("1: "+str(time.perf_counter()-perf))
            if pragmaNecessary:
                db.query('PRAGMA case_sensitive_like = 0')
                
            yield
                
        # Store values that match
        #=================================================
        if db.query("SELECT COUNT(*) FROM {help}", help=self.HELP_TABLE).getSingle() <= MAX_MATCHING_TAGS:
            self.matchingTags = set(tuple(r) for r in db.query("SELECT tag_id, value_id FROM {help}",
                                                               help=self.HELP_TABLE))
        yield
        
        # Select elements which have these values (or not)
        #=================================================
        domainWhereClause = "el.domain={}".format(domain.id) if domain is not None else "1"
        #perf = time.perf_counter()
        if not self.negate:
            self.result = set(db.query("""
                SELECT DISTINCT el.id
                FROM {table} AS el
                    JOIN {p}tags AS t ON el.id = t.element_id
                    JOIN {help} AS h USING(tag_id, value_id)
                    WHERE {where}
                """, table=fromTable, help=self.HELP_TABLE, where=domainWhereClause).getSingleColumn())
        else: 
            self.result = set(db.query("""
                SELECT el.id
                FROM {table} AS el
                    JOIN {p}tags AS t ON el.id = t.element_id
                    LEFT JOIN {help} AS h ON t.tag_id = h.tag_id AND t.value_id = h.value_id
                WHERE {where}
                GROUP BY el.id
                HAVING COUNT(h.value_id) = 0
                """, table=fromTable, help=self.HELP_TABLE, where=domainWhereClause).getSingleColumn())
        #print("2: "+str(time.perf_counter()-perf))
    
    def _escapeParameter(self, parameter):
        """Escape parameter for use in LIKE expression."""
        return parameter.replace('\\','\\\\').replace('_','\\_').replace('%','\\%')
    
    def getMatchingTags(self):
        return self.matchingTags
    
    @staticmethod
    def parse(string):   
        """Parse either a TagCriterion or a DateCriterion.
        Parse from full braced syntax {tag=<content>} or from short notation (only <content>).
        The content can first contain an optional list of tagnames (the search will be restricted to these
        tags). Afterwards it must contain either an interval, e.g.
            date>=1950     or  date=1700-1800
        in which case a DateCriterion will be created; or a text, e.g. "title=music", in which case a 
        TagCriterion is created. The text may be preceded by the prefixes '#' and '_' to set the attributes
        'singleWord' or 'binary', respectively, of TagCriterion.
        In the special case of a text like "1700" a DateCriterion will be created that has both an interval
        1700-1700 and a text "1700" set. It will perform a date- and a text-search.
        """
        if string.startswith('{'):
            key, operator, content = _splitBracedCriterion(string)
            if key != 'tag':
                return None
            if operator != '=':
                raise ParseException("Invalid TagCriterion")
        else:
            # unbraced criteria are short notations for TagCriteria
            content = string
        
        # Parse content
        tagNames, operator, value = _findOperator(content)
        
        # Determine list of tags
        if tagNames is None or len(tagNames.strip()) == 0:
            tagList = None
        else:
            tagList = _parseTagList(tagNames)
            
        # First try to parse an interval and return a DateCriterion
        if tagList is None or any(tag.type == tags.TYPE_DATE for tag in tagList):
            # Restrict to 4-digit dates to avoid false positives
            interval = Interval.parse(operator, value, digits=4)
            if interval is not None and interval.isValid():
                return DateCriterion(interval, tagList)
            elif operator in ('<=', '>=', '<', '>'):
                raise ParseException("Must specify a valid interval") 
        
        # Now parse a text value
        assert operator == '=' or operator is None
        value = _unquote(value)
        prefixes, value = _splitPrefixes(value)
        if len(value) == 0:
            raise ParseException("Empty text criterion")
        criterion = TagCriterion(value, tagList)
        if PREFIX_SINGLE_WORD in prefixes:
            criterion.singleWord = True
        if PREFIX_BINARY in prefixes:
            criterion.binary = True
        return criterion


class TagCriterion(AbstractTagCriterion):
    """This most important criterion matches elements based on their tag values. It matches elements which
    contain *value* in one of the tags specified in *tagList* (defaults to varchar tags).
    Usually *value* must be contained as a substring in any tag-value. If *singleWord* is True, it must
    be contained as a word on its own. Usually the search will ignore case and diacritics, but if *binary*
    is set to True, it will search for *value* exactly as given.
    """
    def __init__(self, value, tagList=None, singleWord=False, binary=False):
        assert value is not None
        self.value = value
        self.interval = None
        self.tagList = tagList
        if self.tagList is not None and len(self.tagList) == 0:
            self.tagList = None
        self.singleWord = singleWord
        self.binary = binary
        self.matchingTags = None
        
    def isUsingTag(self, tag):
        if self.tagList is not None:
            return tag in self.tagList
        else: return tag.type == tags.TYPE_VARCHAR \
                        or (self.interval is not None and tag.type == tags.TYPE_DATE)
            
    def __eq__(self, other):
        return type(other) is type(self) and other.value == self.value\
                and other.tagList == self.tagList and other.negate == self.negate\
                and other.binary == self.binary and other.singleWord == self.singleWord
            
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def __repr__(self):
        if self.tagList is not None:
            tagNames = ','.join(tag.name for name in self.tagList) + '='
        else: tagNames = ''
        value = _quoteIfNecessary(self.value)
        if self.singleWord:
            value = PREFIX_SINGLE_WORD + value
        if self.binary:
            value = PREFIX_BINARY + value
        return _negHelper(self, '{tag='+tagNames+value+'}')
    
    
class DateCriterion(AbstractTagCriterion):
    """Search for elements which have a date-tag in the given interval. Unless restricted with *tagList*
    all tags of valuetype date are searched.
    If *additionalTextSearch* is True and the interval consists of a single year, the
    criterion will also perform a text search for this year. All varchar/text-tags in *tagList* will be
    searched. If *tagList* is None, then all varchar-tags will be searched.
    """
    def __init__(self, interval, tagList=None, additionalTextSearch=True):
        self.interval = interval
        if additionalTextSearch and interval.start == interval.end:
            self.value = str(interval.start)
        else: self.value = None
        self.tagList = tagList
        self.binary = True
        self.singleWord = False
        self.matchingTags = None
        
    def isUsingTag(self, tag):
        if self.tagList is not None:
            return tag in self.tagList
        else: return tag.type == tags.TYPE_DATE
            
    def __eq__(self, other):
        return type(other) is type(self) and other.interval == self.interval \
                and other.tagList == self.tagList and other.negate == self.negate \
                and other.value == self.value
            
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def __repr__(self):
        if self.tagList is not None:
            tagNames = '=' + ','.join(tag.name for name in self.tagList)
        else: tagNames = ''
        return _negHelper(self, '{tag'+tagNames+interval.toString(includeOperator=True)+'}')
    

class FlagCriterion(Criterion):
    """Match elements which have at least one (or all) of the given flags. *junction* must be either 'AND'
    or 'OR', the latter being the default."""
    def __init__(self, flags, junction='OR'):
        assert len(flags) > 0 # otherwise use AnyFlagCriterion
        self.flags = flags
        assert junction in ('OR', 'AND')
        if len(flags) == 1:
            self.junction = 'OR' # or query is faster
        else: self.junction = junction
    
    def isUsingFlag(self, flag):
        return flag in self.flags
    
    def process(self, fromTable, domain):
        domainClause = " AND el.domain={}".format(domain.id) if domain is not None else ''
        if self.junction == 'AND':
            self.result = set(db.query("""
                SELECT el.id
                FROM {table} AS el JOIN {p}flags AS fl ON el.id = fl.element_id
                WHERE fl.flag_id IN ({flags}) {domain}
                GROUP BY el.id
                HAVING COUNT(fl.element_id) = {count}
                """, table=fromTable, domain=domainClause,
                     flags=db.csIdList(self.flags), count=len(self.flags)).getSingleColumn())
        else: # use or
            self.result = set(db.query("""
                SELECT DISTINCT el.id
                FROM {table} AS el JOIN {p}flags AS fl ON el.id = fl.element_id
                WHERE fl.flag_id IN ({flags}) {domain}
                """, table=fromTable, domain=domainClause, flags=db.csIdList(self.flags)).getSingleColumn())

    def __eq__(self, other):
        return isinstance(other, FlagCriterion) and self.flags == other.flags \
                and self.negate == other.negate
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def __repr__(self):
        if self.junction == 'OR':
            return _negHelper(self, '{flag='+flags.FLAG_SEPARATOR.join(flag.name for flag in self.flags)+'}')
        else:
            parts = ['{flag='+flag.name+'}' for flag in self.flags]
            return _negHelper(self, '({})'+' '.join(parts))
    
    @staticmethod
    def parse(string):
        """Parser function for innerParsers. Parses {flag=list-of-flags}, where list-of-flags must be
        flag names separated by flags.FLAG_SEPARATOR. Currently only OR is used as junction.
        """
        key, operator, data = _splitBracedCriterion(string)
        if key == 'flag' and data is not None:
            if operator != '=':
                raise ParseException("Invalid FlagCriterion")
            flagNames = data.split(flags.FLAG_SEPARATOR)
            try:
                theFlags = [flags.get(name) for name in flagNames if len(name) > 0]
                if len(theFlags) == 0:
                    raise KeyError()
            except KeyError:
                raise ParseException("FlagCriterion got an invalid flag list: '{}'".format(data))
            return FlagCriterion(theFlags)
        else: return None


class StickerCriterion(Criterion):
    """Match elements which have at least one (or all) of the given sticker types. *junction* must be either
    'AND' or 'OR', the latter being the default."""
    def __init__(self, types, junction='OR'):
        assert len(types) > 0 # otherwise use AnyFlagCriterion
        self.types = types
        assert junction in ('OR', 'AND')
        if len(types) == 1:
            self.junction = 'OR' # or query is faster
        else: self.junction = junction
        
    def isUsingSticker(self, stickerType):
        return stickerType in self.types
        
    def __repr__(self):
        return _negHelper(self, '{sticker=' + ','.join(self.types) + '}')
    
    def __eq__(self, other):
        return isinstance(other, StickerCriterion) and self.types == other.types \
                and other.negate == self.negate
    
    def __ne__(self, other):
        return not self.__eq__(other)   
    
    def process(self, fromTable, domain):
        # Currently there is no restriction on the strings in self.types. Thus use SQL placeholders '?'
        # to make sure that strings are correctly escaped.
        joinClause = "{}stickers AS j ON el.id = j.element_id AND j.type IN ({})"\
                        .format(db.prefix, ','.join(['?']*len(self.types)))
        if not self.negate:
            query = "SELECT DISTINCT id FROM {table} AS el JOIN {join} WHERE 1"
        else: query = "SELECT id FROM {table} AS el LEFT JOIN {join} WHERE j.element_id IS NULL"
        if domain is not None:
            query += " AND el.domain={}".format(domain.id)
        self.result = set(db.query(query, table=fromTable, join=joinClause).getSingleColumn())
        
    @staticmethod
    def parse(string):
        """Parser function for criteria.innerParsers. Parses {sticker=list-of-stickerTypes}."""
        key, operator, data = _splitBracedCriterion(string)
        if key == 'sticker' and data is not None:
            if operator != '=':
                raise ParseException("Invalid StickerCriterion")
            types = [t.strip() for t in data.split(',') if len(t.strip()) > 0]
            if len(types) == 0:
                raise ParseException("StickerCriterion needs at least one type.")
            return StickerCriterion(types)
        else: return None
    
    
    def __ne__(self, other):
        return not self.__eq__(other)


class TagIdCriterion(Criterion):
    """A TagIdCriterion contains a list of (tag, value-id) tuples. It matches elements which have at
    least one of these tags. TagIdCriteria are faster than most other criteria because the search only needs
    the tags-table for lookup.
    """
    def __init__(self, tagPairs):
        self.tagPairs = tagPairs
        
    def process(self, fromTable, domain):
        whereClause = " OR ".join("(t.tag_id = {} AND t.value_id = {})".format(*p) for p in self.tagPairs)
        if domain is not None:
            whereClause = "el.domain={} AND ({})".format(domain.id, whereClause)
        self.result = set(db.query("""
            SELECT DISTINCT el.id
            FROM {table} AS el JOIN {p}tags AS t ON el.id = t.element_id
            WHERE {where}
            """, table=fromTable, where=whereClause).getSingleColumn())

    def isUsingTag(self, tag):
        return tag in self.valueIds

    def __eq__(self,other):
        return isinstance(other, TagIdCriterion) and other.tagPairs == self.tagPairs

    def __ne__(self,other):
        return not self.__eq__(other)

    def __repr__(self):
        return "<TagIdCriterion {}>".format(self.tagPairs)
    
        
def _findOperator(string):
    """Split a string like date>=2000 into three parts: *key* ('date'), *operator* ('>=') and *value*
    ('2000') and return these three parts. Ignore whitespace around parts. If no operator is found,
    *key* and *operator* will be None.
    """
    operators = ('=', '>=', '<=', '>', '<')
    for i in range(len(string)):
        for op in operators:
            if string[i:].startswith(op):
                key = string[:i].strip().lower()
                value = string[i+len(op):].strip()
                return (key, op, value)
    else: return (None, None, string)
    
    
def _splitBracedCriterion(string):
    """Split a braced criterion like {id>=2000} into three parts: key ('id'), operator ('>=') and value
    ('2000') and return these three parts. Ignore whitespace around parts. Return the key always in lower
    case. Value and operator may be None (only simultaneously). If the criterion is not a braced criterion
    all parts will be None.
    """
    if not string.startswith('{') or not string.endswith('}'):
        return (None, None, None)
    string = string[1:-1].strip() # remove braces
    key, operator, value = _findOperator(string)
    if operator is None: # special case, e.g. {file}
        return value.strip().lower(), None, None
    
    key = key.strip().lower()
    if len(key) == 0:
        raise ParseException("Invalid braced criterion")
    if operator is not None:
        assert value is not None
        value = value.strip()
        if len(value) == 0:
            raise ParseException("'{}' must be followed by a value".format(operator))
    return key, operator, value


class Interval:
    """An interval defined by a start integer and an end integer. One of them may be None, indicating that
    the interval stretches to infinity in this direction.
    """
    DATE_CRITERION = Word(pyparsing.nums)
    CRITERION1 = Optional(MatchFirst([Literal(s) for s in ['>=', '<=', '=', '>', '<']])) + DATE_CRITERION
    CRITERION2 = DATE_CRITERION + Suppress('-') + DATE_CRITERION
    
    def __init__(self, start, end):
        assert start is not None or end is not None
        self.start = start
        self.end = end
        
    def isValid(self):
        """Return whether this interval is valid. It is invalid, if both start and end are given, but
        start > end."""
        return self.start is None or self.end is None or self.start <= self.end

    @staticmethod
    def parse(operator, string, digits=None):
        """Parse a valid interval from strings like '1800-1900' or '12'. If operator is one of 
        ('<=', '>=', '>', '<'), only a single number will be parsed and an open interval will be constructed.
        If the optional paramater *digits* is specified, only numbers having exactly this number of digits
        will be considered.
        """
        string = string.strip()
        if digits is not None:
            number = Word(pyparsing.nums, exact=digits)
        else: number = Word(pyparsing.nums)
        try:
            if operator not in ('<=', '>=', '>', '<'):
                # the ^ means xor. | does not work together with parseAll=True (bug in pyparsing?)
                parser = number ^ (number + Suppress('-') + number)
                result = parser.parseString(string, parseAll=True).asList()
                result = [int(r) for r in result]
                if len(result) == 1:
                    return Interval(result[0], result[0])
                else: return Interval(result[0], result[1])
            else:
                result = number.parseString(string)
                date = int(result[0])
                if operator == '>=':
                    return Interval(date, None)
                elif operator == '<=':
                    return Interval(None, date)
                elif operator == '>':
                    return Interval(date+1, None)
                elif operator == '<':
                    return Interval(None, date-1)
                else: assert False
        except pyparsing.ParseException:
            return None
        
    def queryPart(self):
        """Return a piece of SQL which will select values from this interval in a WHERE-clause."""
        assert self.isValid()
        if self.start == self.end:
            return "={}".format(self.start)
        elif self.start is None:
            return "<={}".format(self.end)
        elif self.end is None:
            return ">={}".format(self.start)
        else: return "BETWEEN {} AND {}".format(self.start, self.end)
        
    def toDateSql(self):
        """Return an interval which, if this interval specifies a range of years, will specify the same
        range but in the internal database format used by utils.FlexiDate."""
        from .. import utils
        start = utils.FlexiDate(self.start).toSql() if self.start is not None else None
        end = utils.FlexiDate(self.end).toSql() if self.end is not None else None
        return Interval(start, end)
    
    def toString(self, includeOperator=False):
        """Return a string representation of this interval. If *includeOperator* is True, it will always
        start with an operator ('=' when in doubt).
        """
        if self.start is not None and self.end is not None:
            if self.start != self.end:
                return ('=' if includeOperator else '') + "{}-{}".format(self.start, self.end)
            else: return ('=' if includeOperator else '') + str(self.start)
        elif self.start is None:
            return "<={}".format(self.end)
        else: return ">={}".format(self.start)
        
    def __repr__(self):
        return self.toString()
        
    def __eq__(self, other):
        return isinstance(other, Interval) and other.start == self.start and other.end == self.end
            
    def __ne__(self, other):
        return not self.__eq__(other)


def _splitPrefixes(string):
    """Look whether any of the prefixes in *allowed* appear at the beginning of *string*. Return a tuple
    consisting of the prefixes as string (or the empty string) and the rest of the string. Multiple prefixes
    are possible."""
    i = 0
    while i < len(string) and string[i] in PREFIX_BINARY + PREFIX_SINGLE_WORD:
        i += 1
    return string[:i], string[i:]


# These functions will be invoked with a single search criterion string (len > 0, no whitespace) to create
# a Criterion-instance. As soon as a function returns not None, this criterion is used.
parsers = [
    ElementTypeCriterion.parse,
    IdCriterion.parse,
    AnyCriterion.parse,
    AnyTagCriterion.parse,
    FlagCriterion.parse,
    StickerCriterion.parse,
    AbstractTagCriterion.parse # must be last, because this handles non-braced criteria
]


#=================
# Helper functions
#=================

def _splitList(token, theList):
    """Split *theList* at each item which equals *token* and return a generator that yields the resulting
    sublists."""
    result = []
    for item in theList:
        if item != token:
            result.append(item)
        else:
            yield result
            result = []
    yield result


def _parseTagList(string):
    """Parse a list of tag names, e.g. 'title, album,artist' to a list of tags. Raise a ParseException
    if the list is empty or contains external tags.
    Allow a fixed set of one-letter abbreviations (e.g. 'g' for 'genre').
    """
    tagNames = [name.strip() for name in string.split(',') if len(name.strip()) > 0]
    # Replace abbreviations. Do not use abbreviations if they would hide an internal tag.
    tagNames = [TAG_ABBREVIATIONS.get(name, name) if not tags.isInDb(name) else name for name in tagNames]
    if len(tagNames) == 0:
        raise ParseException("Invalid list of tags")
    try:
        tagList = [tags.get(name) for name in tagNames]
    except ValueError:
        raise ParseException("Invalid tagname")
    if not all(tag.isInDb() for tag in tagList):
        raise ParseException("Cannot search for tags which are not in the database.")
    return tagList


def _quoteIfNecessary(string):
    """Wrap a string in double quotes unless it is a single word of alphanumeric characters."""
    if string.isalnum():
        return string
    else: return _quote(string)
    
    
def _quote(string):
    """Safely wrap a string in double quotes."""
    return '"{}"'.format(string.replace('"','\\"'))


def _unquote(string):
    """Restore a string quoted with _quote: Remove double quotes except if they are escaped. Unescape
    the latter."""
    result = ''
    escape = False
    for c in string:
        if escape:
            result += c
            escape = False
        elif c == '\\':
            escape = True
        elif c == '"':
            escape = False
        else:
            result += c
            escape = False
    return result
        
def _negHelper(criterion, string):
    """Helper function for the __repr__ functions of all criteria."""
    if criterion.negate:
        return PREFIX_NEGATE + string
    else: return string
