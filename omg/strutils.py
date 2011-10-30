# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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

"""This module just contains several useful string functions."""

import re, itertools
from omg import config, constants
from difflib import SequenceMatcher

def longestSubstring(a, b):
    """Return the longest common substring of *a* and *b*."""
    sm = SequenceMatcher(None, a, b)
    result = sm.find_longest_match(0, len(a), 0, len(b))
    return a[result[0]:result[0]+result[2]]


def replace(text,dict):
    """Replace multiple pairs at a single blow. To be exact: The keys of *dict* are replaced by the
    corresponding values."""
    regex = re.compile('|'.join(map(re.escape,dict)))
    def translate(match):
        return dict[match.group(0)]
    return regex.sub(translate, text)


def nextNonWhiteSpace(string,pos=0):
    """Return the position of the first non-whitespace character in *string*, beginning at *pos*. If no such
    character is found, return the length of *string*."""
    while pos < len(string) and string[pos].isspace():
        pos = pos + 1
    return pos


def nextWhiteSpace(string,pos=0):
    """Return the position of the first whitespace character in *string*, beginning at *pos*. If no such
    character is found, return the length of *string*."""
    while pos < len(string) and not string[pos].isspace():
        pos = pos + 1
    return pos


def formatLength(lengthInSeconds):
    """Convert a number of seconds into a string like ``01:34``, ``00:05`` or ``1:20:00``. Hours are only
    displayed when *lengthInSeconds* is at least 3600. Minutes and seconds are displayed with leading zeros.
    """
    if not isinstance(lengthInSeconds,int):
        lengthInSeconds = int(lengthInSeconds)
        
    seconds = lengthInSeconds % 60
    minutes = int(lengthInSeconds / 60) % 60
    if lengthInSeconds < 3600:
        return "{0:02d}:{1:02d}".format(minutes,seconds)
    else:
        hours = int(lengthInSeconds / 3600)
        return "{0:d}:{1:02d}:{2:02d}".format(hours,minutes,seconds)


def commonPrefix(strings):
    """Given a list of string or something that can be converted to one, return the longest common prefix."""
    strings = list(strings)
    if len(strings) == 0:
        return ''
    i = 0
    while i < len(strings[0]) and all(strings[0][i] == string[i] for string in strings[1:]):
        i = i + 1
    return strings[0][:i]

        
def numberFromPrefix(string):
    """Check whether string starts with something like ``'23'``, ``'1.'``, ``'IV.  '``. To be precise: This
    method first checks whether *string* starts with an arabic or roman integer number (roman numbers are
    case-insensitive). If so, the method returns a tuple containing

        * the number (as ``int``) and
        * the prefix. This is the part at the beginning of *string* containing the number and -- if present
          -- a period directly following the number and/or subsequent whitespace.

    If no number is found, this method returns ``(None,"")``. For example::

        >>> numberFromPrefix("IV. Allegro vivace")
        (4,"IV. ")

    This method is used to find numbers in song titles. To avoid false positives, it currently finds only
    roman numbers build from I,V and X.
    """
    if len(string) == 0:
        return (None,"")

    # First try arabic numbers
    i = 0
    while string[i].isdigit():
        i += 1
    if i > 0:
        number = int(string[:i])
    else:
        # try roman numbers
        while string[i].upper() in "IVX": # other characters will just raise the chance of false positives
            i += 1
        if i > 0:
            try:
                number = romanToArabic(string[:i])
            except ValueError:
                return (None,"") # just looks like a roman number...give up
        else: return (None,"") # no number found...give up
        
    # Ok I found a prefix
    if string[i] == '.':
        i += 1
        while (string[i].isspace()):
            i += 1
    return (number,string[:i])


def rstripSeparator(string):
    """Return a copy of *string* where whitespace at the end is removed. If after removing whitespace the
    string contains one of the separators from ``constants.SEPARATORS`` at its end, remove it together with
    additional whitespace."""
    string = string.rstrip()
    for sep in constants.SEPARATORS:
        if string.endswith(sep):
            string = string[:-len(sep)]
            break
    return string.rstrip()


def isRomanNumber(string):
    """Check whether *string* is a correct roman number (case-insensitively)."""
    try:
        romanToArabic(string)
        return True
    except ValueError:
        return False


def romanToArabic(roman):
    """Return the value of the given roman number (which may contain upper and lower case letters) or raise
    a :exc:`ValueError` if *roman* is not a correct roman number."""
    roman = roman.upper()
    if not all(c in "MDCLXVI" for c in roman):
        raise ValueError("Invalid character in roman number.")

    values = {'M': 1000,'D': 500,'C': 100,'L': 50,'X': 10,'V': 5,'I': 1}

    i = 0
    result = 0
    characterIterator = iter("MDCLXVI")
    for c in characterIterator:
        count = 0
        while i < len(roman) and roman[i] == c:
            count += 1
            i += 1
        if count > 3 and c != 'M' or (c in "DLV" and count > 1):
            raise ValueError("Invalid roman number.")
        else:
            result += count * values[c]
            # Now check for something like IX where we have to subtract
            if i+1 < len(roman) and roman[i+1] == c:
                minuend = values[c]
                subtrahend = values[roman[i]]
                if subtrahend > minuend or subtrahend == minuend/2: # e.g. XXMX or VX
                    raise ValueError("Invalid roman number")
                else:
                    result += minuend - subtrahend
                    # now we have to skip all characters up to and including roman[i]  (XCXX is invalid)
                    while c != roman[i]:
                        c = next(characterIterator)
                    i += 2
                    
    if i != len(roman):
        raise ValueError("Invalid roman number") # For example XMM, XLIX
    else: return result
