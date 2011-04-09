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

    import database
    db = database.connect()
    db.query(...)

or, if the connection was already established in another module::

    import database
    db = database.get()
    db.query(...)

\ """

import sys
from omg import strutils, config, logging
from . import sql


class DBLayoutException(Exception):
    """Exception that occurs if the existing database layout doesn't meet the requirements."""

# Database connection object
db = None

# Table prefix
prefix = None

# Logger for database warnings
logger = logging.getLogger("omg.database")

def connect():
    """Connect to the database server with information from the config file. The drivers specified in ``config.options.database.drivers`` are tried in the given order."""
    global db, prefix
    if db is None:
        db = sql.newConnection(config.options.database.drivers)
        try:
            db.connect(*[config.options.database[key] for key in
                         ("mysql_user","mysql_password","mysql_db","mysql_host","mysql_port")])
        except sql.DBException as e:
            logger.error("I cannot connect to the database. Did you provide the correct information in the config file? MySQL error: {}".format(e.message))
            sys.exit(1)
            
        logger.info("Database connection is open.")
        prefix = config.options.database.prefix
    else: logger.warning("database.connect has been called although the database connection was already open")
    return db


def get():
    """Return the database connection object or None if the connection has not yet been opened."""
    return db


def resetDatabase():
    """Drop all tables and create them without data again. All table rows will be lost!"""
    from . import tables
    for table in tables.tables:
        table.reset()


def listTables():
    """Return a list of all tables in the database."""
    return list(db.query("SHOW TABLES").getSingleColumn())
