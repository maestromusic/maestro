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

"""Methods to parse queries of the form "Symphony composer:Haydn  title:'Le Matin'"."""

from .criteria import TextCriterion
from .. import strutils
from ..core import tags
        
# Abbreviations for tags which may be used in queries
TAG_ABBREVIATIONS = {"t": "title",
                     "a": "artist",
                     "c": "composer",
                     "p": "performer",
                     "g": "genre",
                     "d": "date"
                     }

def _removeQuotationMarks(string):
    """Removes quotation marks (" or ') from string but keeps quotation marks which are in a string delimited
    by the other sort of quotation marks. So abc"def'ghi" becomes abcdef'ghi."""
    result = ''
    quotPos = 0 # position _after_ the last closing quotation mark
    pos = 0
    while pos < len(string):
        if string[pos] in ('"',"'"):
            try:
                result += string[quotPos:pos]
                # find next quotation mark of the same type and skip it
                quotPos = string.index(string[pos],pos+1)+1
                # append the text between the quotation marks without the marks
                result += string[pos+1:quotPos-1]
                pos = quotPos
            except ValueError: # no closing quotation mark found
                return result + string[pos+1:] # so just add the rest of the string
        else: pos += 1

    if pos > quotPos: # add the remaining string to the result
        result += string[quotPos:pos]
    return result;


def _splitStringQuot(string):
    """Like the str.split functions this function returns a list of the words in string using any whitespace
    as delimiters. But unlike str.split whitespace within quotation marks (" or ') is ignored and the quotation
    marks are removed. So 'ab"cd ef" gh ij' becomes ['abcd ef','gh','ij']. If no closing quotation mark is
    found, the remaining string is regarded as one word: 'ab "cde' becomes ['ab','cde']."""
    startPos = strutils.nextNonWhiteSpace(string) # beginning of the current word
    pos = startPos # current position of parsing

    splitList = []
    while pos < len(string):
        # Check for quotation marks
        if string[pos] in ('"',"'"):
            try:
                # find next quotation mark of the same type and skip it
                pos = string.index(string[pos],pos+1)+1 
            except ValueError: # no closing quotation mark found
                # so regard the rest of string as one word and stop splitting
                splitList.append(string[startPos:]) 
                return splitList
        elif string[pos].isspace():
            splitList.append(string[startPos:pos])
            startPos = strutils.nextNonWhiteSpace(string,pos)
            pos = startPos
        else: # string[pos] is neither quotation mark nor whitespace
            pos += 1

    # If string does not end with whitespace the last word has not been appended yet
    if startPos < len(string):
        splitList.append(string[startPos:])

    return [_removeQuotationMarks(item) for item in splitList]


def _createCriterionFromString(string):
    """Splits a queryString like "composer:Beethoven" into a tuple consisting of a tag prefix and a search
    value and creates a TextCriterion-instance from it."""
    try:
        index = string.index(':')
        if index > 0:
            tagname = string[:index]
            searchValue = string[index+1:]
            if tagname in TAG_ABBREVIATIONS:
                tagname = TAG_ABBREVIATIONS[tagname]
            if tags.isInDb(tagname):
                return TextCriterion([tags.get(tagname)],searchValue)
            else: return TextCriterion(None,searchValue)
        else: return TextCriterion(None,string[1:]) # Skip the colon at the beginning
    except ValueError: # No colon found
        return TextCriterion(None,string);


def parseSearchString(searchString):
    """Parses searchString and returns a list of the queries contained in it. Queries with empty values are
    left out."""
    criteria = [_createCriterionFromString(queryString) for queryString in _splitStringQuot(searchString)]
    return [criterion for criterion in criteria if len(criterion.value) > 0]
