#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from omg import config
import re
from . import db, DBLayoutException, _parseIndexedTags

class SQLTable:
    """This class contains methods to create, check and drop a table in an SQL database."""
    name = None # The name of this table.
    createQuery = None # The SQL-query which creates this table.
    
    def __init__(self,createQuery):
        """Initialises this table with the given create_query."""
        self.createQuery = createQuery
        result = re.match("\s*CREATE\s*TABLE\s*(\w+)",createQuery,re.I)
        self.name = result.group(1)
        if self.name == None:
            raise Exception("Bad SQL-Query: {0}".format(createQuery))

    def exists(self):
        """Returns whether this table exists in the database."""
        # In the QtSql-database driver placeholders in some SHOW-queries don't work...therefore we use format
        result = db.query("SHOW TABLES LIKE '{0}'".format(self.name))
        return result.size() > 0
        
    def create(self):
        """Creates this table by executing its createQuery."""
        if self.exists():
            raise DBLayoutException("Table '{0}' does already exist.".format(self.name))
        db.query(self.createQuery)
    
    def reset(self):
        """Drops this table and creates it without data again. All table rows will be lost!"""
        if not self.exists():
            raise DBLayoutException("Table '{0}' does not exist.".format(self.name))
        db.query("DROP table {0}".format(self.name))
        self.create()


# Static tables
#========================
# Later this dictionary will be enlarged by the tag-tables (which depend on the config-file).
# Take the following commands, save them in an SQLTable object and save it with its name as key in a dictionary.
tables = {table.name:table for table in (SQLTable(createQuery) for createQuery in (
"""CREATE TABLE containers (
        id MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
        name VARCHAR(255) NOT NULL,
        INDEX name_idx(name(10)),
        elements SMALLINT UNSIGNED NOT NULL DEFAULT 0,
        PRIMARY KEY(id)
    );
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
        container_id MEDIUMINT UNSIGNED NOT NULL,
        path VARCHAR(511),
        hash VARCHAR(63),
        verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        length MEDIUMINT UNSIGNED NOT NULL,
        PRIMARY KEY(container_id),
        UNIQUE INDEX path_idx(path),
        INDEX hash_idx(hash),
        INDEX length_idx(length)
    );
""",
"""CREATE TABLE tags (
        container_id MEDIUMINT UNSIGNED NOT NULL,
        tag_id SMALLINT UNSIGNED NOT NULL,
        value_id MEDIUMINT UNSIGNED NOT NULL,
        INDEX tag_value_idx(tag_id,value_id),
        INDEX container_idx(container_id)
    );
""",
"""CREATE TABLE tagids (
        id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
        tagname VARCHAR(63) NOT NULL,
        tagtype ENUM('varchar','date','text') DEFAULT 'varchar',
        PRIMARY KEY(id),
        UNIQUE INDEX(tagname)
    );
""",
"""CREATE TABLE othertags (
        container_id MEDIUMINT UNSIGNED NOT NULL,
        tagname VARCHAR(63),
        value VARCHAR(255),
        INDEX container_id_idx(container_id)
    );
""")
)}

# Tag tables
#========================
class TagTable(SQLTable):
    def __init__(self,tagname,tagtype):
        if not tagtype in self._tag_queries:
            raise Exception("Unknown tag type '{0}'".format(tagtype))
        SQLTable.__init__(self,self._tag_queries[tagtype].format("tag_"+tagname))

    #queries to create the tag tables. Replace the placeholder before use...
    _tag_queries = {
        "varchar" : """
        CREATE TABLE {0} (
            id MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
            value VARCHAR(255) NOT NULL,
            PRIMARY KEY(id),
            INDEX value_idx(value(15)),
            FULLTEXT INDEX fulltext_idx(value)
        );""",

        "date" : """
        CREATE TABLE {0} (
            id MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
            value DATE NOT NULL,
            PRIMARY KEY(id),
            UNIQUE INDEX value_idx(value)
        );""",

        "text" : """
        CREATE TABLE {0} (
            id MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
            value TEXT NOT NULL,
            PRIMARY KEY(id),
            INDEX value_idx(value(15)),
            FULLTEXT INDEX fulltext_idx(value)
        );"""
    }

for tagname,tagtype in _parseIndexedTags().items():
    newTable = TagTable(tagname,tagtype)
    tables[newTable.name] = newTable