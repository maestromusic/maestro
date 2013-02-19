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

import pyparsing
from pyparsing import Optional, MatchFirst, Suppress, CharsNotIn, Word
from pyparsing import Literal, Combine, ZeroOrMore, Group, Forward, OneOrMore

from .. import database as db
from ..core import tags, flags

# Initialized in search.init
SEARCH_TAGS = set()

PREFIX_NEGATE = '!'
PREFIX_CASE_SENSITIVE = '_'
PREFIX_SINGLE_WORD = '#'

# Abbreviations for tags which may be used in queries
TAG_ABBREVIATIONS = {"t": "title",
                     "a": "artist",
                     "c": "composer",
                     "p": "performer",
                     "g": "genre",
                     "d": "date"
                     }  


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
    """
    if isinstance(wordOrList, str):
        for parseFunction in outerParsers:
            criterion = parseFunction(wordOrList)
            if criterion is not None:
                return criterion
        else: assert False # the last parser should always return a criterion
    else:
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
        if negate:
            criterion.negate = not criterion.negate
        yield criterion

def combine(junction, criteriaList):
    """Return a MultiCriterion using the specified *junction* and criteria. If *criteriaList* contains only a
    single criterion, return it instead."""
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
        parts = (str(crit) for crit in self.criteria)
        separator = ' ' if self.junction == 'AND' else ' | '
        return _negHelper(self, '({})'.format(separator.join(parts)))
    
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

        
class BracedCriterion(Criterion):
    """Abstract base class for criteria which are enclosed by brackets."""
    @staticmethod
    def parse(string):
        """Parser function for BracedCriteria. It will split words like '{id=2000}' into a keyword and
        a data part and call the functions in 'innerParsers' with these arguments until one of them returns
        a criterion. Thus to implement your own BracedCriteria you simply need to add a function to that
        list. It will be called with
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
            

class ElementTypeCriterion(BracedCriterion):
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
    
    @staticmethod
    def parse(key, data):
        """Parser function for innerParsers."""
        if key in ('container', 'file'):
            if data is not None:
                raise ParseException("ElementTypeCriterion does not accept data.")
            return ElementTypeCriterion(key)
        else: return None
    
    
class IdCriterion(BracedCriterion):
    """Matches elements whose id is in the given interval."""
    def __init__(self, interval):
        assert isinstance(interval, Interval)
        self.interval = interval
        
    def __repr__(self):
        return _negHelper(self, '{id='+str(self.interval)+'}')
    
    def __eq__(self, other):
        return isinstance(other, IdCriterion) and other.interval == self.interval \
                and other.negate == self.negate
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def getQueries(self, fromTable):
        return ["SELECT id FROM {} WHERE id {}".format(fromTable, self.interval.queryPart())]
    
    @staticmethod
    def parse(key, data):
        """Parser function for innerParsers."""
        if key == 'id':
            if data is not None:
                interval = Interval.parse(data)
            else: interval = None
            if interval is None or not interval.isValid():
                raise ParseException("IdCriterion needs a valid interval.")
            return IdCriterion(interval)
        else: return None
        
        
class AnyCriterion(BracedCriterion):
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
    
    @staticmethod
    def parse(key, data):
        """Parser function for innerParsers."""
        if key in ('tag', 'flag', 'sticker') and data is None:
            return AnyCriterion(key)
            # if data is given, use a TagCriterion, FlagCriterion, StickerCriterion instead
        else: return None
        

class TagCriterion(BracedCriterion):
    """This most important criterion matches elements based on their tag values. It matches elements which
    contain *value* in at least one of the tags in *tagList* (which defaults to SEARCH_TAGS). If *value*
    is None it matches tags which have at least one tag of *tagList*.
    
    The other arguments specify whether *value* must be found as a single word or must be matched
    case-sensitively.
    """
    def __init__(self, value=None, tagList=None, singleWord=False, caseSensitive=False):
        assert value is None or (isinstance(value, str) and len(value) > 0)
        self.value = value
        if tagList is None:
            self.tagList = SEARCH_TAGS
        elif len(tagList) == 0 and tagList is not SEARCH_TAGS: # empty SEACH_TAGS is a nasty corner case
            raise ValueError("TagCriterion must have at least one tag. Use AnyCriterion instead.")
        else: self.tagList = tagList
        self.singleWord = singleWord
        self.caseSensitive = caseSensitive
        
    def isUsingTag(self, tag):
        return tag in self.tagList
        
    def __repr__(self):
        if self.value is not None and self.tagList == SEARCH_TAGS: 
            return _negHelper(self, _quote(self.value)) # use the short notation for this common case
        else:
            assert len(self.tagList) > 0
            tagNames = ','.join(tag.name for tag in self.tagList)
            if self.value is None:
                return _negHelper(self, '{tag='+tagNames+'}')
            else:
                prefixes = ''
                if self.singleWord:
                    prefixes += PREFIX_SINGLE_WORD
                if self.caseSensitive:
                    prefixes += PREFIX_CASE_SENSITIVE
                return _negHelper(self, '{tag='+tagNames+'='+prefixes+_quote(self.value)+'}')
            
    def __eq__(self, other):
        return isinstance(other, TagCriterion) and other.value == self.value\
                and other.tagList == self.tagList and other.negate == self.negate
            
    def __ne__(self, other):
        return not self.__eq__(other)
    
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
                # Note: negate is handled by BracedCriterion.parse
                return parseTextCriterion(value, tagList, negate=False)
        else:
            return None
          
            
class FlagCriterion(BracedCriterion):
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
    
    def getQuery(self,fromTable,columns):
        if self.junction == 'AND':
            return ["""
                SELECT {0}
                FROM {1}elements AS el JOIN {1}flags AS fl ON el.id = fl.element_id
                WHERE fl.flag_id IN ({2})
                GROUP BY el.id
                HAVING COUNT(fl.element_id) = {3}
                """.format(_formatColumns(columns,'el'),db.prefix,db.csIdList(self.flags),len(self.flags))]
        else: # use or
            return ["""
                SELECT {0}
                FROM {1}elements AS el JOIN {1}flags AS fl ON el.id = fl.element_id
                WHERE fl.flag_id IN ({2})
                GROUP BY el.id
                """.format(_formatColumns(columns,'el'),db.prefix,db.csIdList(self.flags))]

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
        """Parser function for innerParsers."""
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


class StickerCriterion(BracedCriterion):
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
        
    @staticmethod
    def parse(key, data):
        """Parser function for innerParsers."""
        if key == 'sticker' and data is not None: # use AnyCriterion if data is None
            types = [t for t in data.split(',') if len(t) > 0]
            if len(types) == 0:
                raise ParseException("StickerCriterion needs at least one type.")
            return StickerCriterion(types)
        else: return None
    
    
class DateCriterion(Criterion):
    """Match elements which have a 'date tag' within the given interval. *interval* must be valid (see
    Interval.isValid). Usually all SEARCH_TAGS of value-type tags.TYPE_DATE will be used, but this can be
    changed with the *tagList* argument.
    """
    def __init__(self, interval, tagList=None):
        assert interval.isValid()
        self.interval = interval
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
            if not certainlyDate and not all(number is None or 1000 <= number < 10000
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
    
    def isUsingTag(self, tag):
        return tag in self.tagList
    
    def __eq__(self, other):
        return isinstance(other, DateCriterion) and other.interval == self.interval \
                and other.negate == self.negate
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def __repr__(self):
        return _negHelper(self, self.interval.__repr__())
        

def parseTagShortNotation(string): 
    """Parse a Criterion from a string using tag short notation (e.g. 'composer=Beethoven'). If *string*
    does not match this short notation, return None.
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
    """
    if tagList is None:
        tagList = SEARCH_TAGS
    string = origString.strip()
    prefixes = PREFIX_SINGLE_WORD + PREFIX_CASE_SENSITIVE
    if negate is None:
        prefixes += PREFIX_NEGATE
    prefixes, string = _splitPrefixes(string, prefixes)
    string = _unquote(string)
    if len(string) == 0:
        raise ParseException("TagCriterion got an invalid value: '{}'".format(origString))
    
    if len(tagList) > 0 and all(tag.type == tags.TYPE_DATE for tag in tagList):
        # in this special case this method creates a DateCriterion
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
    if PREFIX_CASE_SENSITIVE in prefixes:
        criterion.caseSensitive = True
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


def _quote(string):
    """Safely wrap a string in double quotes."""
    return '"{}"'.format(string.replace('"','\\"'))


def _unquote(string):
    """Restore a string quoted with _unquote: Remove double quotes except if they are escaped. Unescape
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
    BracedCriterion.parse,
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
    