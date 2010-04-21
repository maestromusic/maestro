#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
# Methods to parse queries of the form "Symphony composer:Haydn  title:'Le Matin'".
#
from omg import strutils, tags
from .criteria import TextCriterion
        
# Abbreviations for tags which may be used in queries
TAG_ABBREVIATIONS = {"t": "title",
                     "a": "artist",
                     "c": "composer",
                     "p": "performer",
                     "g": "genre",
                     "d": "date"
                     }

def _removeQuotationMarks(string):
    """Removes quotation marks (" or ') from string but keeps quotation marks which are in a string delimited by the other sort of quotation marks. So abc"def'ghi" becomes abcdef'ghi."""
    result = ''
    quotPos = 0 # position _after_ the last closing quotation mark
    pos = 0
    while pos < len(string):
        if string[pos] in ('"',"'"):
            try:
                result += string[quotPos:pos]
                quotPos = string.index(string[pos],pos+1)+1 # find next quotation mark of the same type and skip it
                result += string[pos+1:quotPos-1] # append the text between the quotation marks without the marks
                pos = quotPos
            except ValueError: # no closing quotation mark found
                return result + string[pos+1:] # so just add the rest of the string
        else: pos += 1

    if pos > quotPos: # add the remaining string to the result
        result += string[quotPos:pos]
    return result;


def _splitStringQuot(string):
    """Like the str.split functions this function returns a list of the words in string using any whitespace as delimiters. But unlike str.split whitespace within quotation marks (" or ') is ignored and the quotation marks are removed. So 'ab"cd ef" gh ij' becomes ['abcd ef','gh','ij']. If no closing quotation mark is found, the remaining string is regarded as one word: 'ab "cde' becomes ['ab','cde']."""
    startPos = strutils.nextNonWhiteSpace(string) # beginning of the current word
    pos = startPos # current position of parsing

    splitList = []
    while pos < len(string):
        # Check for quotation marks
        if string[pos] in ('"',"'"):
            try:
                pos = string.index(string[pos],pos+1)+1 # find next quotation mark of the same type and skip it
            except ValueError: # no closing quotation mark found
                splitList.append(string[startPos:]) # so regard the rest of string as one word and stop splitting
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
    """Splits a queryString like "composer:Beethoven" into a tuple consisting of a tag prefix and a search value and creates a TextCriterion-instance from it."""
    try:
        index = string.index(':')
        if index > 0:
            tagname = string[:index]
            searchValue = string[index+1:]
            if tagname in TAG_ABBREVIATIONS:
                tagname = TAG_ABBREVIATIONS[tagname]
            return TextCriterion(tags.get(tagname),searchValue)
        else: return TextCriterion(None,string[1:]) # Skip the colon at the beginning
    except ValueError: # No colon found
        return TextCriterion(None,string);


def parseSearchString(searchString):
    """Parses searchString and returns a list of the queries contained in it. Queries with empty values are left out."""
    criteria = [_createCriterionFromString(queryString) for queryString in _splitStringQuot(searchString)]
    return [criterion for criterion in criteria if len(criterion.value) > 0]