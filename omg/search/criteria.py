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

import re
import pyparsing
from pyparsing import Optional, MatchFirst, Suppress, CharsNotIn, Word
from pyparsing import Literal, Combine, ZeroOrMore, Group, Forward, OneOrMore

from .. import database as db, utils
from ..core import tags, flags

# Initialized in search.init
SEARCH_TAGS = set()

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
        for parseFunction in outerParsers:
            criterion = parseFunction(wordOrList)
            if criterion is not None:
                return criterion
        else: assert False # the last parser should always return a criterion
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
        query += " WHERE el.file={}".format(value)
        if domain is not None:
            query += " AND el.domain={}".format(domain.id)
        self.result = set(db.query(query, table=fromTable).getSingleColumn())
    
    @staticmethod
    def parse(key, data):
        """Parser function for innerParsers. Parses {file} and {container}."""
        if key in ('container', 'file'):
            if data is not None:
                raise ParseException("ElementTypeCriterion does not accept data.")
            return ElementTypeCriterion(key)
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
            idSpec = str(self.interval)
        else: idSpec = ','.join(str(id) for id in self.idList)
        return _negHelper(self, '{id='+idSpec+'}')
    
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
        print(query)
        self.result = set(db.query(query, table=fromTable).getSingleColumn())
    
    @staticmethod
    def parse(key, data):
        """Parser function for innerParsers. Parses {id=<interval>}, where <interval> must is handled by
        Interval.parse."""
        if key == 'id':
            if data is not None:
                interval = Interval.parse(data)
                if interval is not None:
                    if interval.isValid():
                        return IdCriterion(interval=interval)
                    else: raise ParseException("IdCriterion's interval must be valid.")
                else:
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
    def parse(key, data):
        """Parser function for innerParsers. Parses {tag}, {flag}, {sticker}."""
        if key in ('tag', 'flag', 'sticker') and data is None:
            return AnyCriterion(key)
            # if data is given, use a TagCriterion, FlagCriterion, StickerCriterion instead
        else: return None
        

class TagCriterion(Criterion):
    """This most important criterion matches elements based on their tag values. It matches elements which
    contain *value* in at least one of the tags in *tagList* (which defaults to SEARCH_TAGS). If *value*
    is None it matches tags which have at least one tag of *tagList*.
    
    Usually a tag value must simply contain *value* as substring in order to be matched by this criterion.
    With the optional arguments *singleWord* and *binary* this behavior can be changed.
    
    If the list of tags contains date-tags and value is an interval, the criterion will also search for
    matching date values.
    """
    def __init__(self, value=None, tagList=None, singleWord=False, binary=False):
        assert value is None or (isinstance(value, str) and len(value) > 0)
        self.value = value
        if tagList is None:
            self.tagList = SEARCH_TAGS
        elif len(tagList) == 0 and tagList is not SEARCH_TAGS: # empty SEACH_TAGS is a nasty corner case
            raise ValueError("TagCriterion must have at least one tag. Use AnyCriterion instead.")
        else: self.tagList = tagList
        
        self.interval = None
        if any(tag.type == tags.TYPE_DATE for tag in self.tagList):
            interval = Interval.parse(self.value)
            if interval is not None and interval.isValid() \
                    and (interval.start is None or 1000 <= interval.start <= 9999) \
                    and (interval.end is None or 1000 <= interval.end <= 9999):
                self.interval = interval
                
        self.singleWord = singleWord
        self.binary = binary
        self.matchingTags = None
        
    def isUsingTag(self, tag):
        return tag in self.tagList
        
    def __repr__(self):
        if self.value is not None and self.tagList == SEARCH_TAGS: 
            return _negHelper(self, _quoteIfNecessary(self.value)) # use short notation for this common case
        else:
            assert len(self.tagList) > 0
            tagNames = ','.join(tag.name for tag in self.tagList)
            if self.value is None:
                return _negHelper(self, '{tag='+tagNames+'}')
            else:
                prefixes = ''
                if self.singleWord:
                    prefixes += PREFIX_SINGLE_WORD
                if self.binary:
                    prefixes += PREFIX_BINARY
                return _negHelper(self, '{tag='+tagNames+'='+prefixes+_quoteIfNecessary(self.value)+'}')
            
    def __eq__(self, other):
        return type(other) is type(self) and other.value == self.value\
                and other.tagList == self.tagList and other.negate == self.negate\
                and other.binary == self.binary and other.singleWord == self.singleWord
            
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def process(self, fromTable, domain):
        # First handle the case where we search only for existence or non-existence of a given tag
        if self.value is None:
            joinClause = "{}tags AS t ON el.id = t.element_id AND t.tag_id IN ({})"\
                            .format(db.prefix, db.csIdList(self.tagList))
            if not self.negate:
                query = "SELECT DISTINCT id FROM {table} AS el JOIN {join}"
            else: query = "SELECT id FROM {table} AS el LEFT JOIN {join} WHERE t.element_id IS NULL"
            self.result = set(db.query(query, table=fromTable, join=joinClause).getSingleColumn())
            return
        
        # Truncate help table
        #==================
        from . import TT_HELP
        if db.type == 'mysql':
            # truncate may be much faster than delete http://dev.mysql.com/doc/refman/5.6/en/delete.html
            db.query("TRUNCATE {}".format(TT_HELP))
        else: db.query("DELETE FROM {}".format(TT_HELP))
        
        # Select matching values and put them into help table
        #====================================================
        pragmaNecessary = False
        for valueType in tags.TYPES:
            tagList = [tag for tag in self.tagList if tag.type == valueType]
            if len(tagList) == 0:
                continue
            if valueType == tags.TYPE_VARCHAR:
                if self.binary:
                   value = self.value
                else: value = utils.strings.removeDiacritics(self.value) 
                if db.type == 'mysql':
                    if not self.singleWord:
                        if self.binary:
                            whereClause = 'INSTR(value, BINARY ?)'
                        else: whereClause = "INSTR(COALESCE(search_value, value), ?)"
                        args = [value]
                    else:
                        if self.binary:
                            whereClause = 'value REGEXP BINARY ?' # case-sensitive
                        else: whereClause = 'COALESCE(search_value, value) REGEXP ?'
                        args = ['[[:<:]]{}[[:>:]]'.format(re.escape(value))]
                        
                else: # SQLite
                    if not self.singleWord:
                        if self.binary:
                            # INSTR exists only in SQLite 3.7.15 and later
                            pragmaNecessary = True
                            db.query('PRAGMA case_sensitive_like = 1')
                            whereClause = "value LIKE ?"
                        else: whereClause = "COALESCE(search_value, value) LIKE ?"
                        args = ['%{}%'.format(self._escapeParameter(value))]
                    else:
                        if self.binary:
                            whereClause = "value REGEXP ?"
                            args = ['\\b{}\\b'.format(re.escape(value))]
                        else:
                            whereClause = "COALESCE(search_value, value) REGEXP ?" 
                            args = ['(?i)\\b{}\\b'.format(re.escape(value))]
                
            elif valueType == tags.TYPE_TEXT:
                whereClause = "value LIKE ?"
                args = ['%{}%'.format(self._escapeParameter(self.value))]
                
            elif valueType == tags.TYPE_DATE:
                if self.interval is None:
                    continue
                whereClause = self.interval.toDateSql().queryPart()
                args = []
                
            db.query("""
                    INSERT INTO {help} (value_id, tag_id)
                        SELECT id, tag_id
                        FROM {p}values_{type}
                        WHERE tag_id IN({tags}) AND {where}
                    """, *args, help=TT_HELP, type=valueType.name,
                                tags=db.csIdList(tagList), where=whereClause)
                
            if pragmaNecessary:
                db.query('PRAGMA case_sensitive_like = 0')
                
            yield
                
        # Store values that match
        #=================================================
        if db.query("SELECT COUNT(*) FROM {help}", help=TT_HELP).getSingle() <= MAX_MATCHING_TAGS:
            self.matchingTags = set(db.query("SELECT tag_id, value_id FROM {help}", help=TT_HELP))
        yield
        
        # Select elements which have these values (or not)
        #=================================================
        domainWhereClause = "el.domain={}".format(domain.id) if domain is not None else "1"
        if not self.negate:
            self.result = set(db.query("""
                SELECT DISTINCT el.id
                FROM {table} AS el
                    JOIN {p}tags AS t ON el.id = t.element_id
                    JOIN {help} AS h USING(tag_id, value_id)
                    WHERE {where}
                """, table=fromTable, help=TT_HELP, where=domainWhereClause).getSingleColumn())
        else: 
            self.result = set(db.query("""
                SELECT el.id
                FROM {table} AS el
                    JOIN {p}tags AS t ON el.id = t.element_id
                    LEFT JOIN {help} AS h ON t.tag_id = h.tag_id AND t.value_id = h.value_id
                WHERE {where}
                GROUP BY el.id
                HAVING COUNT(h.value_id) = 0
                """, table=fromTable, help=TT_HELP, where=domainWhereClause).getSingleColum())
    
    def _escapeParameter(self, parameter):
        """Escape parameter for use in LIKE expression."""
        return parameter.replace('\\','\\\\').replace('_','\\_').replace('%','\\%')
    
    def getMatchingTags(self):
        return self.matchingTags
    
    @staticmethod
    def parse(key, data):
        """Parser function for innerParsers."""
        if key == 'tag' and data is not None: # use AnyCriterion if data is None
            if '=' in data:
                tagNames, value = data.split('=', 1)
            else: tagNames, value = data, None
            tagNames = [name.strip() for name in tagNames.split(',') if len(name) > 0]
            if len(tagNames) == 0:
                raise ParseException("TagCriterion needs at least one tag.")
            try:
                tagList = [tags.get(name) for name in tagNames] # raises ValueError if a name is invalid
                if any(not tag.isInDb() for tag in tagList):
                    raise ValueError()
            except ValueError:
                raise ParseException("TagCriterion can only use tags which are in the database.")
            
            if value is None:
                return TagCriterion(tagList=tagList)
            else:
                # Note: negate is handled by parseBracedCriterion
                return parseTextCriterion(value, tagList, negate=False)
        else:
            return None
          
            
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
    def parse(key, data):
        """Parser function for innerParsers. Parses {flag=list-of-flags}, where list-of-flags must be
        flag names separated by flags.FLAG_SEPARATOR. Currently only OR is used as junction.
        """
        if key == 'flag' and data is not None: # use AnyCriterion if data is None
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
    def parse(key, data):
        """Parser function for criteria.innerParsers. Parses {sticker=list-of-stickerTypes}."""
        if key == 'sticker' and data is not None: # use AnyCriterion if data is None
            types = [t for t in data.split(',') if len(t) > 0]
            if len(types) == 0:
                raise ParseException("StickerCriterion needs at least one type.")
            return StickerCriterion(types)
        else: return None
    
    
class DateCriterion(TagCriterion):
    """Match elements which have a 'date tag' within the given interval. *interval* must be valid (see
    Interval.isValid). Usually all SEARCH_TAGS of valuetype tags.TYPE_DATE will be used, but this can be
    changed with the *tagList* argument.
    """
    def __init__(self, interval, tagList=None):
        assert interval.isValid()
        self.interval = self.value = interval  # self.value is needed by TagCriterion.getQueries
        if tagList is None:
            tagList = SEARCH_TAGS
        self.tagList = [tag for tag in tagList if tag.type == tags.TYPE_DATE]
        
    @staticmethod
    def parse(string, certainlyDate=False):
        """Parse a DateCriterion from a string. To avoid false positives, only accept valid ranges of
        4-digit dates. If no such date is found, return None. In places where you really expect a date,
        you can set *certainlyDate* to True, to change this behavior: Then all valid ranges are accepted
        and a ParseException is emitted when no date is found.
        """
        prefix, string = _splitPrefixes(string, PREFIX_NEGATE) 
        interval = Interval.parse(string)
        if interval is not None and interval.isValid():
            if not certainlyDate and not all(number is None or 1000 <= number <= 9999
                                             for number in (interval.start, interval.end)):
                # To avoid false positives, restrict DateCriteria to 4-digit numbers
                return None
            criterion = DateCriterion(interval)
            if PREFIX_NEGATE in prefix:
                criterion.negate = not criterion.negate
            return criterion
        
        if certainlyDate:
            raise ParseException("DateCriterion requires a valid interval.")
        else: return None
    
    def __repr__(self):
        return _negHelper(self, self.interval.__repr__())
    
    def __eq__(self, other):
        return isinstance(other, DateCriterion) and other.interval == self.interval \
                 and other.tagList == self.tagList

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
    

def parseBracedCriterion(string):
    """Parser function for criteria enclosed in braces. It will split words like '{id=2000}' into a
    keyword and a data part and call the functions in 'innerParsers' with these arguments until one of
    them returns a criterion. Thus to implement your own BracedCriteria you simply need to add a function
    to that list. It will be called with
        - the keyword (lower case, whitespace stripped),
        - the data part (whitespace stripped, None if no data, or only whitespace is given).
    """ 
    prefix, string = _splitPrefixes(string, PREFIX_NEGATE)
    if not string.startswith('{') or not string.endswith('}'):
        return None
    string = string[1:-1] # remove { and }
    if '=' in string:
        keyWord, data = string.split('=', 1)
        data = data.strip()
        if len(data) == 0:
            data = None
    else:
        keyWord, data = string, None
    keyWord = keyWord.strip().lower()

    for parseFunction in innerParsers:
        criterion = parseFunction(keyWord, data)
        if criterion is not None:
            if PREFIX_NEGATE in prefix:
                criterion.negate = not criterion.negate
            return criterion
    else: raise ParseException("No inner parser returned a criterion for '{}'."
                               .format(prefix+'{'+string+'}'))
        
        
def parseTagShortNotation(string): 
    """Parse a Criterion from a string using tag short notation (e.g. 'composer=Beethoven'). If *string*
    does not match this short notation, return None.
    Instead of the full tag name an abbreviation from TAG_ABBREVIATIONS may be used.
    """
    if '=' in string:
        prefix, string = _splitPrefixes(string, PREFIX_NEGATE)
        tagName, string = string.split('=', 1)
        if len(string) == 0:
            raise ParseException("Tag short notation requires a value.")
        if tagName in TAG_ABBREVIATIONS:
            tagName = TAG_ABBREVIATIONS[tagName]
        try:
            tag = tags.get(tagName)
            if not tag.isInDb():
                raise ValueError()
        except ValueError:
            raise ParseException("Tag short notation requires a tag which is in the database.")
        
        return parseTextCriterion(string, [tag], negate=PREFIX_NEGATE in prefix)
    else:
        return None
        
        
def parseTextCriterion(origString, tagList=None, negate=None):
    """Parse a Criterion from *origString*. Usually this returns a TagCriterion which matches elements
    with *origString* in at least one of their SEARCH_TAGS. The list of tags may be specified with
    *tagList*. If all tags are of type tags.TYPE_DATE, a DateCriterion will be created instead.
    
    *negate* specifies whether the created criterion should be negated. It may be True, False or None. In
    the last case the criterion is negated if it is prefixed with PREFIX_NEGATE.
    
    This parser never returns None. It might raise a ParseException, though.
    """
    if tagList is None:
        tagList = SEARCH_TAGS
    string = origString.strip()
    prefixes = PREFIX_SINGLE_WORD + PREFIX_BINARY
    if negate is None:
        prefixes += PREFIX_NEGATE
    prefixes, string = _splitPrefixes(string, prefixes)
    string = _unquote(string)
    if len(string) == 0:
        raise ParseException("TagCriterion got an invalid value: '{}'".format(origString))
    
    if len(tagList) > 0 and all(tag.type == tags.TYPE_DATE for tag in tagList):
        # in this special case this method creates a DateCriterion
        # Note that this only happens if *tagList* is explicitly specified, e.g. when this method is called
        # from TagCriterion.parse or parseTagShortNotation.
        criterion = DateCriterion.parse(string, certainlyDate=True)
        criterion.tagList = tagList
        if negate or PREFIX_NEGATE in prefixes:
            criterion.negate = True
        return criterion
    
    criterion = TagCriterion(string, tagList)
    if negate or PREFIX_NEGATE in prefixes:
        criterion.negate = True
    if PREFIX_SINGLE_WORD in prefixes:
        criterion.singleWord = True
    if PREFIX_BINARY in prefixes:
        criterion.binary = True
    return criterion
        
    
class Interval:
    """An interval defined by a start integer and an end integer. One of them may be None, indicating that
    the interval stretches to infinity in this direction.
    """
    DATE_CRITERION = Word(pyparsing.nums)
    CRITERION1 = Optional(MatchFirst([Literal(s) for s in ['>=', '<=', '>', '<']])) + DATE_CRITERION
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
    def parse(string):
        """Parse an interval from strings like '1800-1900', '>=100' or simply '123'. Return None if this 
        is not possible."""
        try:
            result = Interval.CRITERION1.parseString(string, parseAll=True)
            if len(result) == 1:
                date = int(result[0])
                return Interval(date, date)
            else: prefix, date = result[0], int(result[1])
            if prefix == '>=':
                return Interval(date, None)
            elif prefix == '<=':
                return Interval(None, date)
            elif prefix == '>':
                return Interval(date+1, None)
            else: return Interval(None, date-1)
        except pyparsing.ParseException:
            pass
        try:
            start, end = Interval.CRITERION2.parseString(string, parseAll=True)
            return Interval(int(start), int(end)) # allow invalid intervals! (start > end)
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
        
    def __repr__(self):
        if self.start is not None and self.end is not None:
            return "{}-{}".format(self.start, self.end)
        elif self.start is None:
            return "<={}".format(self.end)
        else: return ">={}".format(self.start)
        
    def __eq__(self, other):
        return isinstance(other, Interval) and other.start == self.start and other.end == self.end
            
    def __ne__(self, other):
        return not self.__eq__(other)


def _splitPrefixes(string, allowed):
    """Look whether any of the prefixes in *allowed* appear at the beginning of *string*. Return a tuple
    consisting of the prefixes as string (or the empty string) and the rest of the string. Multiple prefixes
    are possible."""
    i = 0
    while i < len(string) and string[i] in allowed:
        i += 1
    return string[:i], string[i:]


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
    parts = string.split('"')
    for i, part in enumerate(parts[:-1]):
        if len(part) > 0 and part[-1] == '\\':
            parts[i] = part[:-1]+'"'
    return ''.join(parts)


def _negHelper(criterion, string):
    """Helper function for the __repr__ functions of all criteria."""
    if criterion.negate:
        return PREFIX_NEGATE + string
    else: return string


# These functions will be invoked with a single search criterion string (len > 0, no whitespace) to create
# a Criterion-instance. As soon as a function returns not None, this criterion is used.
outerParsers = [
    parseBracedCriterion,
    DateCriterion.parse,
    parseTagShortNotation,
    parseTextCriterion
]

innerParsers = [
    ElementTypeCriterion.parse,
    IdCriterion.parse,
    AnyCriterion.parse,
    TagCriterion.parse,
    FlagCriterion.parse,
    StickerCriterion.parse
]
    