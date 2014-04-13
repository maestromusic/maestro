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

"""This module just contains several useful string functions."""

import re, string, unicodedata

from PyQt4 import QtCore
translate = QtCore.QCoreApplication.translate

from .. import constants


def replace(text, dict):
    """Replace multiple pairs at a single blow. To be exact: The keys of *dict* are replaced by the
    corresponding values."""
    regex = re.compile('|'.join(map(re.escape, dict)))
    def translate(match):
        return dict[match.group(0)]
    return regex.sub(translate, text)


def nextNonWhiteSpace(string, pos=0):
    """Return the position of the first non-whitespace character in *string*, beginning at *pos*. If no such
    character is found, return the length of *string*."""
    while pos < len(string) and string[pos].isspace():
        pos = pos + 1
    return pos


def nextWhiteSpace(string, pos=0):
    """Return the position of the first whitespace character in *string*, beginning at *pos*. If no such
    character is found, return the length of *string*."""
    while pos < len(string) and not string[pos].isspace():
        pos = pos + 1
    return pos


def formatLength(lengthInSeconds):
    """Convert a number of seconds into a string like "01:34", "00:05", "1:20:00" or "2 days 14:25:30".
    Display days and hours are only when necessary. Display minutes and seconds with leading zeros.
    """
    if not isinstance(lengthInSeconds, int):
        lengthInSeconds = int(lengthInSeconds)
        
    seconds = lengthInSeconds % 60
    minutes = int(lengthInSeconds / 60) % 60
    if lengthInSeconds < 3600:
        return "{0:02d}:{1:02d}".format(minutes, seconds)
    else:
        hours = int(lengthInSeconds / 3600)
        timeString = "{0:d}:{1:02d}:{2:02d}".format(hours % 24, minutes, seconds)
        if hours < 24:
            return timeString
        else: return translate("formatLength", "%n days", '', QtCore.QCoreApplication.CodecForTr,
                               int(hours/24)) + ' ' + timeString


def formatSize(size):
    """Return a human-readable representation of the given amount of bytes."""
    if not isinstance(size, int):
        size = int(size)
    units = ['Bytes', 'kB', 'MB', 'GB', 'TB']
    unitIndex = 0
    # Note that we use decimal prefixes
    while size >= 1000:
        size /= 1000
        unitIndex += 1
    return "{:.1f} {}".format(size, units[unitIndex])


def commonPrefix(strings, separated=False):
    """Given a list of string or something that can be converted to one, return the longest common prefix.
    If *separated* is True, shorten the prefix so that it ends with whitespace/punctuation (exception: do
    not shorten prefix, if all strings are equal). Note: In particular this fixes the problem that the common
    prefix of ["Part I.", "Part II.", "Part III."] includes a part of the numbers and that the numbers
    cannot be recognized without it.
    """
    strings = list(strings)
    if len(strings) == 0:
        return ''
    i = 0
    try:
        while i < len(strings[0]) and all(strings[0][i] == string[i] for string in strings[1:]):
            i += 1
    except IndexError:
        pass
    prefix = strings[0][:i]
    if not separated or all(len(prefix) == len(string) for string in strings):
        return prefix
    else:
        while i > 0 and prefix[i-1] not in string.whitespace + string.punctuation:
            i -= 1
        return prefix[:i]

        
def numberFromPrefix(string):
    """Check whether string starts with something like ``'23'``, ``'1.'``, ``'IV.  '``. To be precise: This
    method first checks whether *string* starts with an arabic or roman integer number (roman numbers are
    case-insensitive). If so, the method returns a tuple containing

        * the number (as ``int``) and
        * the prefix. This is the part at the beginning of *string* containing the number and -- if present
          -- a period directly following the number and/or subsequent whitespace.

    If no number is found, this method returns ``(None, "")``. For example::

        >>> numberFromPrefix("IV. Allegro vivace")
        (4, "IV. ")

    This method is used to find numbers in song titles. To avoid false positives, it only detects numbers if
    they are followed by whitespace or a period or a colon and finds only roman numbers build from I, V and X.
    """
    if len(string) == 0:
        return (None, "")

    # First try arabic numbers
    i = 0
    while i < len(string) and string[i].isdigit():
        i += 1
    if i > 0:
        number = int(string[:i])
    else:
        # try roman numbers. Other characters than 'IVX' would just raise the chance of false positives
        i = 0
        while i < len(string) and string[i].upper() in "IVX":
            i += 1
        if i > 0:
            try:
                number = romanToArabic(string[:i])
            except ValueError:
                return (None, "") # just looks like a roman number...give up
        else: return (None, "") # no number found...give up
        
    # Ok I found a prefix that looks like a number
    if i == len(string):
        return (number, string)
    indexWhereNumberEnds = i
    if string[i] in '.:':
        i += 1
    while i < len(string) and string[i].isspace():
        i += 1
    # Only detect a number if at least one whitespace or a period was found
    if indexWhereNumberEnds < i:
        return (number, string[:i])
    else: return (None, '')

    
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

    values = {'M': 1000, 'D': 500, 'C': 100, 'L': 50, 'X': 10, 'V': 5, 'I': 1}

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


def removeDiacritics(s):
    """Return *s* with all diacritics removed: Replace 'ä' -> 'a', 'é' -> 'e' etc."""  
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.combining(c) == 0)
