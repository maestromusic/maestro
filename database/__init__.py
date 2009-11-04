#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
# Package usage:
# import database
# db = database.connect()
#
import config
import logging
from . import sql

class DBLayoutException(Exception):
    """Exception that occurs if the existing database layout doesn't meet the requirements."""

# Database connection object
db = None

# Logger for database warnings
logger = logging.getLogger("database")

def connect():
    """Connects to the database server with information from the config file."""
    global db
    db = sql.newDatabase(config.get("database","driver"))
    db.connect(*[config.get("database",key) for key in ("mysql_user","mysql_password","mysql_db","mysql_host","mysql_port")])
    logger.debug("Database connection is open.")
    return db