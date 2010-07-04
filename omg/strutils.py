#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
# This module contains an abstraction layer for SQL databases. It provides a common API
# to several third party SQL modules so that the actual SQL module can be exchanged
# without changing the project code.
#

#This file contains just several useful string functions.
import re
from omg import config

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
