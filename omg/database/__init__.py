#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation

"""
The database module provides an abstraction layer to several Python-MySQL connectors.

The actual database drivers which connect to the database using a third party connector are found in the :mod:`SQL package <omg.database.sql>`. The definitions of Omg's tables are found in the :mod:`tables-module <omg.database.tables>`.

The easiest way to use this package is::

    from omg import database as db
    db.connect()
    db.query(...)

or, if the connection was already established in another module::

    import db
    db.query(...)

\ """

import sys
from omg import strutils, config, logging
from . import sql


class DBLayoutException(Exception):
    """Exception that occurs if the existing database layout doesn't meet the requirements."""

# Table prefix
prefix = None

# Logger for database warnings
logger = logging.getLogger("omg.database")

# Database connection object
db = None

# These methods will be replaced by the database connection object's corresponding methods once the connection has been established.
def query(*params):
    logger.error("Cannot access database before a connection was opened.")

multiQuery = query
transaction = query
commit = query
rollback = query


def connect():
    """Connect to the database server with information from the config file. The drivers specified in ``config.options.database.drivers`` are tried in the given order."""
    if db is not None:
        logger.warning("database.connect has been called although the database connection was already open")
    else:
        global prefix
        prefix = config.options.database.prefix
        authValues = [config.options.database["mysql_"+key] for key in sql.AUTH_OPTIONS]
        _connect(config.options.database.drivers,authValues)
        logger.info("Database connection is open.")
        

def testConnect(driver):
    """Connect to the database server using the test connection information (config.options.database.test_*). If any of these options is empty, the standard option will be used instead (config.options.database.mysql_*). The table prefix will in be config.options.database.test_prefix even if it is empty. For safety this method will abort the program if prefix, db-name and host coincide with the standard values used by connect."""
    authValues = []
    host = None
    dbName = None
    for option in sql.AUTH_OPTIONS:
        value = config.options.database["test_"+option]
        if not value: # Replace empty values by standard values
            value = config.options.database["mysql_"+option]
        authValues.append(value)
        if option == "host":
            host = value
        if option == "db":
            dbName = value

    global prefix
    prefix = config.options.database.test_prefix

    # Abort if the connection information and the prefix is equal
    if (prefix == config.options.database.prefix
            and dbName == config.options.database.mysql_db
            and host == config.options.database.mysql_host):
        print("Safety stop: Test database connection information coincides with the usual information. Please supply at least a different prefix.",file=sys.stderr)
        sys.exit(1)
        
    _connect([driver],authValues)


def _connect(drivers,authValues):
    global db
    try:
        db = sql.newConnection(drivers)
        db.connect(*authValues)
    except sql.DBException as e:
        logger.error("I cannot connect to the database. Did you provide the correct information in the config file? MySQL error: {}".format(e.message))
        sys.exit(1)
    
    global query, multiQuery, transaction, commit, rollback
    query = db.query
    multiQuery = db.multiQuery
    transaction = db.transaction
    commit = db.commit
    rollback = db.rollback


def close():
    """Close the current connection."""
    if db is not None:
        global db, query, multiQuery, transaction, commit, rollback
        db = None
        query = None
        multiQuery = None
        transaction = None
        commit = None
        rollback = None
    else: logger.warning("database.close has been called although no connection was opened.")


def resetDatabase():
    """Drop all tables and create them without data again. All table rows will be lost!"""
    from . import tables
    for table in tables.tables:
        table.reset()


def listTables():
    """Return a list of all table names in the database."""
    return list(query("SHOW TABLES").getSingleColumn())
