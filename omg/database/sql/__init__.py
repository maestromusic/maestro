#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""This module contains an abstraction layer for SQL databases. It provides a common API to several third party SQL modules so that the actual SQL module can be exchanged without changing the project code.

Currently the following drivers are supported:
"mypysql": uses the mysql-python module (http://sourceforge.net/projects/mypysql/)
"qtsql": uses the QtSql-Module of PyQt4 (http://doc.trolltech.com/4.2/qtsql.html)
The supported drivers are stored in the module-variable drivers.

Usage of the module:
=====================================
import sql

db = sql.newConnection(drivername)    # use the driver's string identifier above

result = db.query("SELECT name,country FROM persons WHERE id = ?",person)   # Use ? as placeholder to insert parameters which are automatically escaped

# When using query, this iterator yields for each person a tuple with the corresponding data.
for row in result:
  print(row[0])  #  e.g. ("Max Mustermann","Germany")

# Another way is to use queryDict. The iterator will then return a dictionary {columnname => data} for each person
result = db.queryDict("SELECT name,country FROM persons WHERE id = ?",person)

for row in result:
  print(row[0])  #  e.g. {"name": "Max Mustermann","country": "Germany"}

# An easy method to retrieve a single value from the database is getSingle:
number = db.query("SELECT COUNT(*) FROM persons").getSingle()
"""

from omg import strutils

# Identifiers of supported drivers. For each identifier there must be a module
# <drivername>.py file in this package which contains the corresponding driver.
drivers = {"mypysql","qtsql"}

# When a driver is loaded _modules[driverIdentifier] will contain the driver's module.
_modules = {}


class DBException(Exception):
    """Class for database-related exceptions in this package."""


def newConnection(driver):
    """Create a new database connection object using the given driver identifier. This method does not open a connection."""
    if driver not in drivers:
        raise Exception("driver '{0}' is not known.".format(driver))
    if driver not in _modules:
        _modules[driver] = __import__(driver,globals(),locals())
    return _modules[driver].Sql()
    
    
class AbstractSql:
    """Abstract base class for an SQL connection object.
    
    This class encapsulates a connection to a database. To create instances of AbstractSql use newConnection and specify a driver.
    """
    def connect(self,username,password,database,host="localhost",port=3306):
        """Connect to a database using the given information."""
            
    def query(self,queryString,*args):
        """Perform a query in the database.
        
        Execute the query queryString and return an AbstractSqlResult-instance which yields the result's rows in tuples. The queryString may contain ? as placeholders which are replaced by the args-parameters in the given order. Those parameters must be either string or integer and strings are escaped before replacing. In particular you must not use quotation marks around string parameters: "SELECT id FROM table WHERE name = ?" works fine. A drawback is that you cannot use placeholders to select a table: "SELECT id FROM ?" will not work.
        """
        
    def queryDict(self,queryString,*args):
        """Perform a query in the database.
        
        Execute the query queryString and return an SqlResult object which yields the result's rows in dictionaries with the column names as keys. The queryString may contain ? as placeholders which are replaced by the args-parameters in the given order. Those parameters must be either string or integer and strings are escaped before replacing. In particular you must not use quotation marks around string parameters: "SELECT id FROM table WHERE name = ?" works fine. A drawback is that you cannot use placeholders to select a table: "SELECT id FROM ?" will not work.
        """

    def getDate(self,date):
        """Convert a date value retrieved from the database to a Python date-object. This function must be used since the QtSql database-driver returns QDate-objects from date-columns."""
        
    def escapeString(self,string,likeStatement=False):
        """Escape a string for insertion in MySql queries.
        
        This function escapes the characters which are listed in the documentation of mysql_real_escape_string and is used as a replacement for that function. But it doesn't emulate mysql_real_escape string correctly, which would be difficult since that function needs a database connection to determine the connection's encoding. If <likeStatement> is true this method also escapes '%' and '_' so that the return value may safely be used in LIKE-statements.
        """
        return _escapeString(self,string,likeStatement)


class AbstractSqlResult:
    """Abstract base class for classes which encapsulate a query result set.
    
    This class (or rather driver-dependent subclasses of it) encapsulates the result of the execution of an SQL query. It may contain selected rows from the database or information like the number of affected rows. SqlResult-subclasses implement __iter__ so they may be used in for-loops to retrieve all rows from the result set. Depending on whether query or queryDict was used to create an SqlResult-instance the rows are returned as tuple or as dictionary. In the latter case the column-names are used as keys unless the query specified an alias. A short way to retrieve a single value from the database is getSingle. But be careful not to mix different access methods like getSingle, getSingleColumn and iterator methods (e.g. next) since they may change internal cursors and could interfere with each other.
    """
    def size(self):
        """Returns the number of rows selected in a select query. You can also use the built-in len-method."""
    
    def next(self):
        """Yields the next row from the result set or raises a StopIteration if there is no such row."""
        
    def executedQuery(self):
        """Return the query which produced this SqlResult. The query won't contain placeholders but the actual values used when executing."""
        
    def affectedRows(self):
        """Return the number of rows affected by the query producing this SqlResult."""
    
    def insertId(self):
        """Return the last value which was used in an AUTO_INCREMENT-column when this SqlResult was created."""
    
    def getSingle(self):
        """Returns the first value from the first row of the result set and should be used as a shorthand method if the result contains only one value. Do not use this method together with iterators or getSingleColumn as both of them may move the internal cursor."""
        
    def getSingleColumn(self):
        """Returns a generator for the first column of the result set and should be used as a shorthand method if the result contains only one column. Do not use this method together with iterators or getSingle as both of them may move the internal cursor."""


def _escapeString(string,likeStatement=False):
        """Escape a string for insertion in MySql queries.
        
        This function escapes the characters which are listed in the documentation of mysql_real_escape_string and is used as a replacement for that function. But it doesn't emulate mysql_real_escape string correctly, which would be difficult since that function needs a database connection to determine the connection's encoding. If <likeStatement> is true this method also escapes '%' and '_' so that the return value may safely be used in LIKE-statements.
        """
        escapeDict = {
             '\\': '\\\\',
             "'": "\\'",
             '"': '\\"',
             '\x00': '\\0',
             '0x1A': '\\Z', # ASCII 26
             '\n': '\\n',
             '\r': '\\r'
             }
        if likeStatement:
            escapeDict.update({'%':'\%','_':'\_'})
        return strutils.replace(string,escapeDict)
        
def _replaceQueryArgs(query,*args):
    """Replace occurences of '?' in query by the arguments which must be either string or int. String arguments are escaped."""
    if query.count('?') != len(args):
        raise DBException("Number of '?' must match number of query parameters.")
    for arg in args:
        if isinstance(arg,str):
            arg = "'"+_escapeString(arg)+"'"
        elif isinstance(arg,int):
            arg = str(arg)
        else: raise DBException("All arguments must be either string or int, but I got one of type {0}".format(type(arg)))
        query = query.replace('?',arg,1) # Replace only first occurence
    return query