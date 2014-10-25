# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
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

import unittest

from maestro.search import criteria
from maestro.search.criteria import *


# These first test strings are only used to check criteria.parseToWords
# List test cases as (string, result list)
PARSER_TEST_STRINGS = [
    ("word", ["word"]),
    (" white     space ", ["white", "space"]),
    ("one two", ["one", "two"]),
    ("(one two)", ["one", "two"]),
    ("(one two) | three", [["one", "two"], "|", "three"]),
    ("one|two three | four", ["one", "|", "two", "three", "|", "four"]),
    ("((one two) | three) | four", [[["one", "two"], "|", "three"], "|", "four"]),
    ("one{two}three", ["one", "{two}", "three"])
]
# Extend this list by some words that should not be changed/splitted by the parser
PARSER_TEST_STRINGS.extend((w, [w]) for w in [
    "{word}", "{two words}", "{two (words)}", '{bc}', '!{bc}',
     '"word"', '"two words"', '"two (words)"', '"two {words}"', '!a"bc"d',
     "!word", '!"word"',
     '"word', # this should be detected without closing quotation mark
     ])

INVALID_TEST_STRINGS = [
   "(word", "word)", "{word", "word}"         
]


def _setupWords():
    """Define test strings for criteria.parseWords."""
    # do this in a function because we have to add a flag to the database first
    global TEST_WORDS, INVALID_TEST_WORDS
    TEST_WORDS = [
    ('{file}', ElementTypeCriterion('file')),
    ('{container}', ElementTypeCriterion('container')),
    ('{id=10}', IdCriterion(Interval(10,10))),
    ('{id=<20}', IdCriterion(Interval(None, 19))),
    ('{id= >=2000}', IdCriterion(Interval(2000, None))),
    ('{id=10-100}', IdCriterion(Interval(10,100))),
    ('{flag}', AnyCriterion('flag')),
    ('{flag=testflag}', FlagCriterion([flags.get('testflag')])),
    ('{sticker}', AnyCriterion('sticker')),
    ('{sticker=COVER}', StickerCriterion(['COVER'])),
    ('{tag}', AnyCriterion('tag')),
    ('{tag=artist}', TagCriterion(tagList=[tags.get('artist')])),
    ('{tag=artist=Harry}', TagCriterion('Harry', [tags.get('artist')])),
    ('{tag = artist = White space}', TagCriterion('White space', [tags.get('artist')])),
    ('{tag=artist=_Harry}', TagCriterion('Harry', [tags.get('artist')], caseSensitive=True)),
    ('{tag=artist=#Harry}', TagCriterion('Harry', [tags.get('artist')], singleWord=True)),
    ('{tag=artist=_#Harry}', TagCriterion('Harry', [tags.get('artist')], singleWord=True, caseSensitive=True)),
    ('{tag=artist=#_Harry}', TagCriterion('Harry', [tags.get('artist')], singleWord=True, caseSensitive=True)),
    
    ('artist=Harry', TagCriterion('Harry', [tags.get('artist')])),
    ('artist="Harry Potter"', TagCriterion('Harry Potter', [tags.get('artist')])),
    ('artist=Harry" Potter"', TagCriterion('Harry Potter', [tags.get('artist')])),  
    ('a=Harry', TagCriterion('Harry', [tags.get('artist')])),
    ('a=_#"Harry Potter"', TagCriterion('Harry Potter', [tags.get('artist')], singleWord=True, caseSensitive=True)),
    
    ('1600-1800', DateCriterion(Interval(1600,1800))),
    ('>1900', DateCriterion(Interval(1901, None))),
    ('<= 1750', DateCriterion(Interval(None, 1750))),
    ('{tag=date=1700}', DateCriterion(Interval(1700, 1700))),
    # Only create DateCriteria for valid ranges of 4-digit years
    ('2000-1950', TagCriterion('2000-1950')),
    ('100-200', TagCriterion('100-200')),
    ('<3', TagCriterion('<3')),
    
    ('_#abc"def"gh', TagCriterion('abcdefgh', singleWord=True, caseSensitive=True)),  
    ]

    INVALID_TEST_WORDS = [
        "{file=True}", "{id}", "{id=-20}", "{flag=noflag}", "{flag=theflag=True}", "{nokey=value}"
    ]


# This final set of test strings is fed into the actual parse function (parseWords(parseToWords(string)))
TEST_STRINGS = [
    # enclose expressions in brackets so that the negating test works
    ("(one two)", MultiCriterion('AND', [TagCriterion("one"), TagCriterion("two")])),
    ("(this | that)", MultiCriterion('OR', [TagCriterion("this"), TagCriterion("that")]))  
]

class ParseToWordsTest(unittest.TestCase):
    """Test criteria.parseToWords."""
    def runTest(self):
        for string, result in PARSER_TEST_STRINGS:
            self.assertListEqual(criteria.parseToWords(string), result)
            
        for string in INVALID_TEST_STRINGS:
            self.assertRaises(criteria.ParseException, criteria.parseToWords, string)
    
    
class ParseWordsTest(unittest.TestCase):
    """Test criteria.parseWords."""
    def setUp(self):
        from maestro.core import flags
        flags.addFlagType('testflag')
        _setupWords()
        
    def tearDown(self):
        from maestro.core import flags
        flags.deleteFlagType(flags.get('testflag'))
        
    def runTest(self):
        for string, result in TEST_WORDS:
            self.assertEqual(criteria.parseWords(string), result)
            result.negate = not result.negate
            self.assertEqual(criteria.parseWords(criteria.PREFIX_NEGATE + string), result)
        
        for string in INVALID_TEST_WORDS:
            self.assertRaises(criteria.ParseException, criteria.parseWords, string)
            self.assertRaises(criteria.ParseException, criteria.parseWords, criteria.PREFIX_NEGATE+string)
    
    
class ParseTest(unittest.TestCase):
    """Test criteria.parse."""
    def runTest(self):
        for string, result in TEST_STRINGS:
            self.assertEqual(criteria.parse(string), result)
            result.negate = not result.negate
            self.assertEqual(criteria.parse(criteria.PREFIX_NEGATE + string), result)
        