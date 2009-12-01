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

def replace(text,dict):
    """Replaces multiple pairs at a single blow. To be exact: The keys of dict are replaced by the corresponding values."""
    regex = re.compile('|'.join(map(re.escape,dict)))
    def translate(match):
        return dict[match.group(0)]
    return regex.sub(translate, text)


def nextNonWhiteSpace(string,pos=0):
    """Returns the position of the first non-whitespace character in string, beginning at pos. If no such character is found len(string) will be returned."""
    while pos < len(string) and string[pos].isspace():
        pos = pos + 1
    return pos


def nextWhiteSpace(string,pos=0):
    """Returns the position of the first whitespace character in string, beginning at pos. If no such character is found len(string) will be returned."""
    while pos < len(string) and not string[pos].isspace():
        pos = pos + 1
    return pos