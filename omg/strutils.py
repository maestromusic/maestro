#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation

#This file contains just several useful string functions.
import re
from omg import config, constants

def replace(text,dict):
    """Replace multiple pairs at a single blow. To be exact: The keys of dict are replaced by the corresponding values."""
    regex = re.compile('|'.join(map(re.escape,dict)))
    def translate(match):
        return dict[match.group(0)]
    return regex.sub(translate, text)


def nextNonWhiteSpace(string,pos=0):
    """Return the position of the first non-whitespace character in string, beginning at pos. If no such character is found, return len(string)."""
    while pos < len(string) and string[pos].isspace():
        pos = pos + 1
    return pos


def nextWhiteSpace(string,pos=0):
    """Return the position of the first whitespace character in string, beginning at pos. If no such character is found, return len(string)."""
    while pos < len(string) and not string[pos].isspace():
        pos = pos + 1
    return pos
    
def formatLength(lengthInSeconds):
    """Convert a number of seconds in a string like '01:34', '00:05' or '1:20:00'. Hours are only displayed when <lengthInSeconds> is at least 3600. Minutes and seconds are displayed with leading zeros."""
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
    """Given a list of strings return the longest common prefix."""
    strings = list(strings)
    if len(strings) == 0:
        return ''
    i = 0
    while i < len(strings[0]) and all(strings[0][i] == string[i] for string in strings[1:]):
        i = i + 1
    return strings[0][:i]

def rstripSeparator(string):
    """Return a copy of <string> where whitespace at the end is removed. If after removing whitespace the string contains one of the separators from constants.SEPARATORS at its end, remove it together with additional whitespace."""
    string = string.rstrip()
    for sep in constants.SEPARATORS:
        if string.endswith(sep):
            string = string[:-len(sep)]
            break
    return string.rstrip()
