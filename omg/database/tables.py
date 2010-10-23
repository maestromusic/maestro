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
from omg import config, database, constants, tags
from . import db, DBLayoutException

class SQLTable:
    """A table in the database.
    
    This class contains methods to create, check and drop a table in an SQL database. Note that instantiating SQLTable does not create an actual table or modify the database in any way. The class has two public attributes:
    - createQuery contains the query which can be used to create the table
    - name contains the name of the table
    """
    def __init__(self,createQuery):
        """Initialise this table-object with the given create_query. The name of the table is extracted from the query. This method does not execute the query (in most cases a table created by this query will already exist in the database)."""
        self.createQuery = createQuery
        result = re.match("\s*CREATE\s*TABLE\s*(\w+)",createQuery,re.I)
        self.name = result.group(1)
        if self.name is None:
            raise Exception("Bad SQL-Query: {0}".format(createQuery))

    def exists(self):
        """Return whether this table exists in the database."""
        result = db.query("SHOW TABLES LIKE ?",self.name)
        return result.size() > 0
        
    def create(self):
        """Create this table by executing its createQuery."""
        if self.exists():
            raise DBLayoutException("Table '{0}' does already exist.".format(self.name))
        db.query(self.createQuery)
    
    def reset(self):
        """Drop this table and create it without data again. All table rows will be lost!"""
        if self.exists():
            db.query("DROP table {0}".format(self.name))
        self.create()


# Static tables
#========================
# Later this dictionary will be enlarged by the tag-tables (which depend on the config-file).
# Take the following commands, save them in an SQLTable object and save it with its name as key in a dictionary.
tables = {table.name:table for table in (SQLTable(createQuery) for createQuery in (
"""CREATE TABLE elements (
        id MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
        name VARCHAR(255) NOT NULL,
        file TINYINT(1) NOT NULL,
        toplevel TINYINT(1) NOT NULL,
        elements SMALLINT UNSIGNED NOT NULL DEFAULT 0,
        INDEX name_idx(name(10)),
        PRIMARY KEY(id)
    ) CHARACTER SET 'utf8';
""",
"""CREATE TABLE contents (
        container_id MEDIUMINT UNSIGNED NOT NULL,
        position SMALLINT UNSIGNED NOT NULL,
        element_id MEDIUMINT UNSIGNED NOT NULL,
        PRIMARY KEY(container_id,position),
        INDEX element_idx(element_id)
    );
""",
"""CREATE TABLE files (
        element_id MEDIUMINT UNSIGNED NOT NULL,
        path VARCHAR(511),
        hash VARCHAR(63),
        verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        length MEDIUMINT UNSIGNED NOT NULL,
        PRIMARY KEY(element_id),
        INDEX path_idx(path(333)),
        INDEX hash_idx(hash),
        INDEX length_idx(length)
    ) CHARACTER SET 'utf8';
""",
"""CREATE TABLE tags (
        element_id MEDIUMINT UNSIGNED NOT NULL,
        tag_id SMALLINT UNSIGNED NOT NULL,
        value_id MEDIUMINT UNSIGNED NOT NULL,
        INDEX tag_value_idx(tag_id,value_id),
        INDEX element_idx(element_id)
    );
""",
"""CREATE TABLE tagids (
        id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
        tagname VARCHAR(63) NOT NULL,
        tagtype ENUM('varchar','date','text') DEFAULT 'varchar',
        PRIMARY KEY(id),
        UNIQUE INDEX(tagname)
    );
"""
))}


# Tag tables
#========================
class TagTable(SQLTable):
    """Class for tables which hold all values of a certain tag. Because these tables are created by common queries only depending on tagname and tagtype there is a special class for them."""
    def __init__(self,tagname,tagtype):
        """Initialise this table-object with the given tagname and tagtype."""
        SQLTable.__init__(self,self._tagQueries[tagtype].format("tag_"+tagname))

    #queries to create the tag tables. Replace the placeholder with the tagname before use...
    _tagQueries = {
        tags.TYPE_VARCHAR: """
        CREATE TABLE {0} (
            id MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
            value VARCHAR({1}) NOT NULL,
            PRIMARY KEY(id)
        ) CHARACTER SET 'utf8';""".format("{0}",constants.TAG_VARCHAR_LENGTH),

        tags.TYPE_DATE: """
        CREATE TABLE {0} (
            id MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
            value DATE NOT NULL,
            PRIMARY KEY(id),
            UNIQUE INDEX value_idx(value)
        );""",

        tags.TYPE_TEXT: """
        CREATE TABLE {0} (
            id MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
            value TEXT NOT NULL,
            PRIMARY KEY(id)
        ) CHARACTER SET 'utf8';"""
    }

def allTables():
    """Return a dictionary mapping the table-names to SQLTable-instances and containing all tables which should be in the database (according to the information in tagids)."""
    result = dict(tables)
    if 'tagids' in tables:
        tagTables = {"tag_"+tagname:TagTable(tagname,tags.Type.byName(tagtype))
                        for tagname,tagtype in database.get().query("SELECT tagname,tagtype FROM tagids")}
        result.update(tagTables)
    return result
