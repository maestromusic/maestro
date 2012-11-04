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

"""
This module contains an abstraction layer for MySQL databases. It provides a common API to several third
party MySQL connector modules so that the actual connector can be exchanged without changing the project
code.

Currently the following drivers are supported:

* `qtsql`: uses the QtSql-Module of PyQt4 (http://doc.trolltech.com/latest/qtsql.html)
* `myconnpy`: uses MySQL Connector/Python (https://launchpad.net/myconnpy)
* `pymysql`: uses PyMySQL (https://github.com/petehunt/PyMySQL/)
* `sqlite`: uses the built-in sqlite3 module

The following example shows basic usage of the module::

    import sql

    db = sql.newConnection()    # this will try to find a working driver
    
    # Use ? as placeholder to insert parameters which are automatically escaped
    result = db.query("SELECT name,country FROM persons WHERE id = ?",person)   

    # When using query, this iterator yields for each person a tuple with the corresponding data.
    for row in result:
      print(row[0])  #  e.g. ("Max Mustermann","Germany")

    # An easy method to retrieve a single value from the database is getSingle:
    number = db.query("SELECT COUNT(*) FROM persons").getSingle()
    # Note that this will raise an EmptyResultException if the query returned an empty result.

The main class of the module is :class:`AbstractSQL <omg.database.sql.AbstractSQL>` which is subclassed by
every driver.
"""

import datetime

from ... import logging
from PyQt4.QtCore import QThread
transactionLogger = logging.getLogger("transaction")
logger = logging.getLogger(__name__)


# When a driver is loaded _modules[driverIdentifier] will contain the driver's module.
_modules = {}

# Database connection information in the order it must be supplied to the connect method
AUTH_OPTIONS = ["user","password","db","host","port"]


class DBException(Exception):
    """This exception is raised if something goes wrong with the database connection, or if an invalid query
    is executed.
    """
    def __init__(self,message,query=None,args=None):
        Exception.__init__(self)
        self.message = message
        self.query = query
        self.arguments = args #self.args is a property

    def __str__(self):
        if self.query is not None:
            if self.arguments is not None:
                return "\n".join((self.message,self.query,str(self.arguments)))
            else: return "\n".join((self.message,self.query))
        else: return self.message


class EmptyResultException(Exception):
    """This exception is executed if :meth:`getSingle`, :meth:`getSingleRow` or :meth:`getSingleColumn` are
    performed on a result which does not contain any row.
    """


def newConnection(drivers):
    """Create a new database connection object. *drivers* is a list of driver-module names which will be
    tried in the given order until one is loaded successfully. If no driver can be loaded, a
    :exc:`DBException <omg.database.sql.DBException>` is raised. This method does not actually open a
    connection, but only sets up the the connection object.
    """
    for driver in drivers:
        try:
            if driver not in _modules:
                import importlib
                _modules[driver] = importlib.import_module("."+driver, __package__) #__import__(driver,globals(),locals())
            return _modules[driver].Sql()
        except Exception as e:
            logger.warning("Could not load driver {}: {}".format(driver,e))
            # Try next driver...
    else: raise DBException("Couldn't load any driver from {}".format(drivers))
    
    
class AbstractSql:
    """Abstract base class for an SQL connection object.
    
    This class encapsulates a connection to a database. To create instances of AbstractSql use
    :func:`newConnection <omg.database.sql.newConnection>` which will create a non-abstract subclass of
    this depending on the driver.
    """
    def __init__(self):
        self._transactionDepth = 0
        
    def connect(self,username,password,database,host="localhost",port=3306,**kwargs):
        """Connect to a database using the given information."""
            
    def query(self,queryString,*args):
        """Perform a query in the database. Raise a DBException if the query fails.
        
        Execute the query *queryString* and return an :class:``AbstractSqlResult`` which yields the result's
        rows in tuples. *queryString* may contain ``'?'`` as placeholders which are replaced by the
        *args*-parameters in the given order. Note that you must not use quotation marks around string
        parameters::

            SELECT id FROM table WHERE name = ?

        works fine. You may also use FlexiDates as parameters since they will be converted automatically.

        A drawback is that you cannot use placeholders to select a table::
        
            SELECT id FROM ?

        will not work.
        """
        
    def multiQuery(self,queryString,args):
        """Perform a query several times with changing parameter sets. Raise a DBException if the query
        fails.

        Equivalent to::
        
            self.transaction()
            for parameters in args:
                self.query(queryString,*parameters)
            self.commit()

        In some drivers :func:`multiQuery` may be faster than this loop because the query has to be sent to
        the server and parsed only once.

        Finally one example::

            SQL.multiQuery("INSERT INTO persons VALUES (?,?)",(("Peter","Germany"),("Julie","France")))

    \ """
        self.transaction()
        for parameters in args:
            self.query(queryString,*parameters)
        self.commit()

    def transaction(self):
        """Start a transaction. Transactions can be nested. Only when the outermost transaction is committed,
        all changes are performed in the database. This method returns True, if the outermost transaction has
        been started.
        """
        self._transactionDepth += 1
        if self._transactionDepth == 1:
            transactionLogger.debug("OPEN {}".format(QThread.currentThread()))
        return self._transactionDepth == 1
        
    def commit(self):
        """Commit a transaction. Return True if changes have really been written to the database (and False
        if just a nested transaction was closed)."""
        self._transactionDepth -= 1
        if self._transactionDepth == 0:
            transactionLogger.debug("CLOSE {}".format(QThread.currentThread()))
        return self._transactionDepth == 0
        
    def rollback(self):
        """Rollback a transaction. Nested transactions cannot be rolled back."""
        if self._transactionDepth > 1:
            raise RuntimeError("Cannot rollback nested transactions")
        transactionLogger.debug("ROLLBACK")
        self._transactionDepth = 0

    def isNull(self,value):
        """Return whether *value* represents a NULL value from a MySQL table (how null values are
        represented in result sets depends on the driver)."""
        return value is None # default implementation for drivers that return Null as None

    def getDate(self,value):
        """Return *value* converted to a datetime.datetime. Use this method on every date returned from
        the database because different database drivers may return different date formats."""
        # default implementation for drivers that already return datetime.datetime
        return value.replace(tzinfo = datetime.timezone.utc)

    def close(self):
        """Close this driver."""


class AbstractSqlResult:
    """Abstract base class for classes which encapsulate a query result set.
    
    This class (or rather driver-dependent subclasses of it) encapsulates the result of the execution of an
    SQL query. It may contain selected rows from the database or information like the number of affected
    rows. :class:`AbstractSqlResult`-subclasses implement ``__iter__`` so they may be used in ``for``-loops
    to retrieve all rows as tuples from the result set. A short way to retrieve a single value from the
    database is getSingle.

    .. warning::
        Be careful not to mix different access methods like getSingle, getSingleColumn and iterator methods
        (e.g. next) since they all may change internal cursors and could interfere with each other.
    """
    def size(self):
        """Returns the number of rows selected in a select query. You can also use the built-in
        :func:`len`-method.
        """
    
    def next(self):
        """Yields the next row from the result set or raises a :exc:`StopIteration` if there is no such
        row."""
        
    def executedQuery(self):
        """Return the query which produced this SqlResult. The query won't contain placeholders but the
        actual values used when executing."""
        
    def affectedRows(self):
        """Return the number of rows affected by the query producing this :class:`AbstracSqlResult`.
        This method must not be used for result sets produced by multiqueries (different drivers would return
        different values)."""
    
    def insertId(self):
        """Return the last value which was used in an ``AUTO_INCREMENT``-column when this AbstractSqlResult
        was created. This method must not be used for result sets produced by multiqueries (different drivers
        would return different values)."""
    
    def getSingle(self):
        """Return the first value from the first row of the result set. Use this as a shorthand method if
        the result contains only one value. If the result set does not contain any row, an
        :exc:`EmptyResultException` is raised.
        """
        
    def getSingleColumn(self):
        """Return a generator for the first column of the result set. Use this as a shorthand method if the
        result contains only one column. Contrary to getSingeRow, this method does not raise an
        :exc:`EmptyResultException` if the result set is empty."""
        
    def getSingleRow(self):
        """Return the first row of the result set or raise an :exc:`EmptyResultException` if the result does
        not contain any rows. Use this as a shorthand if there is only one row in the result set."""
        if self.size() == 0:
            raise EmptyResultException()
        else: return self.next()
