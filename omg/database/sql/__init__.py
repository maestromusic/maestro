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

from omg import strutils

# Identifiers of supported drivers. For each identifier there must be a module
# <drivername>.py file in this package which contains the corresponding driver.
drivers = {"mypysql","qtsql"}

# When a driver is loaded _modules[driverIdentifier] will contain the driver's module.
_modules = {}

class DBException(Exception):
    """Class for database-related exceptions in this package."""
    
def newConnection(driver):
    """Creates a new database connection object using the given driver identifier. It
       does not open the connection."""
    if not driver in drivers:
        raise Exception("driver '{0}' is not known.".format(driver))
    if not driver in _modules:
        _modules[driver] = __import__(driver,globals(),locals())
    return _modules[driver].Sql()
    

def _replaceQueryArgs(query,*args):
    if not query.count('?') == len(args):
        raise DBException("Number of '?' must match number of query parameters.")
    for arg in args:
        if isinstance(arg,str):
            arg = "'"+_escapeString(arg)+"'"
        elif isinstance(arg,int):
            arg = str(arg)
        else: raise DBException("All arguments must be either string or int, but I got one of type {0}".format(type(arg)))
        query = query.replace('?',arg,1) # Replace only first occurence
    return query

def _escapeString(s):
    """Escapes a string for insertion in MySql queries. This function escapes the characters which are listed in the documentation of mysql_real_escape_string and is used as a replacement for that function. But it doesn't emulate mysql_real_escape string correctly, which would be difficult since that function needs a database connection to determine the connection's encoding."""
    return strutils.replace(s,{
         '\\': '\\\\',
         "'": "\\'",
         '"': '\\"',
         '\x00': '\\0',
         '0x1A': '\\Z', # ASCII 26
         '\n': '\\n',
         '\r': '\\r'
         })