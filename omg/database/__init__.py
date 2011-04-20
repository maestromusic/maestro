#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
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
    global db
    if db is not None:
        logger.warning("database.connect has been called although the database connection was already open")
    else:
        db = sql.newConnection(config.options.database.drivers)
        try:
            db.connect(*[config.options.database[key] for key in
                         ("mysql_user","mysql_password","mysql_db","mysql_host","mysql_port")])
        except sql.DBException as e:
            logger.error("I cannot connect to the database. Did you provide the correct information in the config file? MySQL error: {}".format(e.message))
            sys.exit(1)
            
        logger.info("Database connection is open.")
        global prefix, query, multiQuery, transaction, commit, rollback
        prefix = config.options.database.prefix
        query = db.query
        multiQuery = db.multiQuery
        transaction = db.transaction
        commit = db.commit
        rollback = db.rollback


def resetDatabase():
    """Drop all tables and create them without data again. All table rows will be lost!"""
    from . import tables
    for table in tables.tables:
        table.reset()


def listTables():
    """Return a list of all tables in the database."""
    return list(db.query("SHOW TABLES").getSingleColumn())
