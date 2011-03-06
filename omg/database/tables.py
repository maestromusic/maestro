#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""Module to manage the database tables used by omg."""

import re
from omg import constants,database
from omg.database.sql import DBException

db = database.get()

class SQLTable:
    """A table in the database.
    
    This class contains methods to create, check and drop a table in an SQL database. Note that instantiating SQLTable does not create an actual table or modify the database in any way. The class has two public attributes:

        * ``createQuery`` contains the query which can be used to create the table and is given in the constructor.
        * ``name`` contains the name of the table. And is extracted from ``createQuery``.
    """
    def __init__(self,createQuery):
        self.createQuery = createQuery
        result = re.match("\s*CREATE\s*TABLE\s*(\w+)",createQuery,re.I)
        self.name = result.group(1)
        if self.name is None:
            raise DBException("Bad SQL-Query: {}".format(createQuery))

    def exists(self):
        """Return whether this table exists in the database."""
        result = db.query("SHOW TABLES LIKE '{}'".format(self.name))
        return result.size() > 0
        
    def create(self):
        """Create this table by executing its createQuery."""
        if self.exists():
            raise DBException("Table '{}' does already exist.".format(self.name))
        db.query(self.createQuery)
    
    def reset(self):
        """Drop this table and create it without data again. All table rows will be lost!"""
        if self.exists():
            db.query("DROP table {}".format(self.name))
        self.create()


# Dictionary mapping table names to table objects which are created with the following queries
tables = [SQLTable(createQuery) for createQuery in (
"""CREATE TABLE elements (
        id          MEDIUMINT UNSIGNED  NOT NULL AUTO_INCREMENT,
        file        TINYINT(1)          NOT NULL,
        toplevel    TINYINT(1)          NOT NULL,
        elements    SMALLINT  UNSIGNED  NOT NULL DEFAULT 0,
        PRIMARY KEY(id)
    ) ENGINE InnoDB, CHARACTER SET 'utf8';
""",
"""CREATE TABLE contents (
        container_id MEDIUMINT UNSIGNED NOT NULL,
        position     SMALLINT  UNSIGNED NOT NULL,
        element_id   MEDIUMINT UNSIGNED NOT NULL,
        PRIMARY KEY(container_id,position),
        INDEX element_idx(element_id),
        FOREIGN KEY(container_id) REFERENCES elements(id) ON DELETE CASCADE,
        FOREIGN KEY(element_id) REFERENCES elements(id) ON DELETE CASCADE
    ) ENGINE InnoDB, CHARACTER SET 'utf8';
""",
"""CREATE TABLE files (
        element_id MEDIUMINT UNSIGNED NOT NULL,
        path       VARCHAR(511)       NOT NULL,
        hash       VARCHAR(63),
        verified   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        length     MEDIUMINT UNSIGNED NOT NULL,
        PRIMARY KEY(element_id),
        INDEX path_idx(path(333)),
        INDEX hash_idx(hash),
        INDEX length_idx(length),
        FOREIGN KEY(element_id) REFERENCES elements(id) ON DELETE CASCADE
    ) ENGINE InnoDB, CHARACTER SET 'utf8';
""",
"""CREATE TABLE tagids (
        id      SMALLINT UNSIGNED             NOT NULL AUTO_INCREMENT,
        tagname VARCHAR(63)                   NOT NULL,
        tagtype ENUM('varchar','date','text') NOT NULL DEFAULT 'varchar',
        PRIMARY KEY(id),
        UNIQUE INDEX(tagname)
    ) ENGINE InnoDB, CHARACTER SET 'utf8';
""",
"""CREATE TABLE tags (
        element_id MEDIUMINT UNSIGNED NOT NULL,
        tag_id     SMALLINT  UNSIGNED NOT NULL,
        value_id   MEDIUMINT UNSIGNED NOT NULL,
        INDEX tag_value_idx(tag_id,value_id),
        INDEX element_idx(element_id),
        FOREIGN KEY(element_id) REFERENCES elements(id) ON DELETE CASCADE,
        FOREIGN KEY(tag_id) REFERENCES tagids(id) ON DELETE CASCADE
    ) ENGINE InnoDB, CHARACTER SET 'utf8';
""",
"""CREATE TABLE values_varchar (
        id     MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
        tag_id SMALLINT  UNSIGNED NOT NULL,
        value  VARCHAR({})        NOT NULL,
        PRIMARY KEY(id),
        INDEX tag_value_idx(tag_id,value),
        FOREIGN KEY(tag_id) REFERENCES tagids(id)
    ) ENGINE InnoDB, CHARACTER SET 'utf8';
""".format(constants.TAG_VARCHAR_LENGTH),
"""CREATE TABLE values_text (
        id     MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
        tag_id SMALLINT  UNSIGNED NOT NULL,
        value  TEXT               NOT NULL,
        PRIMARY KEY(id),
        INDEX tag_value_idx(tag_id,value(10)),
        FOREIGN KEY(tag_id) REFERENCES tagids(id)
    ) ENGINE InnoDB, CHARACTER SET 'utf8';
""",
"""CREATE TABLE values_date (
        id     MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
        tag_id SMALLINT  UNSIGNED NOT NULL,
        value  INT       UNSIGNED NOT NULL,
        PRIMARY KEY(id),
        INDEX tag_value_idx(tag_id,value),
        FOREIGN KEY(tag_id) REFERENCES tagids(id)
    ) ENGINE InnoDB, CHARACTER SET 'utf8';
"""
)]
