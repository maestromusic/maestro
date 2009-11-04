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

# Identifiers of supported drivers. For each identifier there must be a module
# <drivername>.py file in this package which contains the corresponding driver.
drivers = {"mypysql","qtsql"}

# When a driver is loaded _modules[driverIdentifier] will contain the driver's module.
_modules = {}

def newDatabase(driver):
    """Creates a new database connection object using the given driver identifier. It
       does not open the connection."""
    if not driver in drivers:
        raise Exception("driver '{0}' is not known.".format(driver))
    if not driver in _modules:
        _modules[driver] = __import__(driver,globals(),locals())
    return _modules[driver].Sql()
    
    
class DBException(Exception):
    """Class for database-related exceptions in this package."""