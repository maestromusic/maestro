#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
# Methods to create the database, connect to it, check its integrity and
# perform some minor corrections. If this file is invoked directly it will
# check the database without correcting or changing anything (just printing
# warnings to stdout).
#
import config
from mysql import MySQL

# MySQL-commands to create these static tables
CREATE_STATIC_TABLE_CMDS = {
    "containers" : """
    CREATE TABLE containers (
        id MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
        name VARCHAR(255) NOT NULL,
        INDEX name_idx(name(10)),
        elements SMALLINT UNSIGNED NOT NULL DEFAULT 0,
        PRIMARY KEY(id)
    );
    """,
    
    "contents": """
    CREATE TABLE contents (
        container_id MEDIUMINT UNSIGNED NOT NULL,
        position SMALLINT UNSIGNED NOT NULL,
        element_id MEDIUMINT UNSIGNED NOT NULL,
        PRIMARY KEY(container_id,position),
        INDEX element_idx(element_id)
    );
    """,
    
    "files": """
    CREATE TABLE files (
        container_id MEDIUMINT UNSIGNED NOT NULL,
        path VARCHAR(511),
        hash VARCHAR(63),
        verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY(container_id),
        UNIQUE INDEX path_idx(path),
        UNIQUE INDEX hash_idx(hash)
    );
    """,
    
    "tags": """
    CREATE TABLE tags (
        container_id MEDIUMINT UNSIGNED NOT NULL,
        tag_id SMALLINT UNSIGNED NOT NULL,
        value_id MEDIUMINT UNSIGNED NOT NULL,
        INDEX tag_value_idx(tag_id,value_id),
        INDEX container_idx(container_id)
    );
    """,
    
    "tagids":"""
    CREATE TABLE tagids (
        id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
        tagname VARCHAR(63) NOT NULL,
        PRIMARY KEY(id)
    );""",
    
    "othertags":"""
    CREATE TABLE othertags (
        container_id MEDIUMINT UNSIGNED NOT NULL,
        tagname VARCHAR(63),
        value VARCHAR(255)
    );"""
    }

# MySQL-command to create a table for a specific tag. Replace the placeholder before use...
CREATE_TAG_TABLE_CMD = """
    CREATE TABLE ? (
        id MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
        value VARCHAR(255) NOT NULL,
        PRIMARY KEY(id),
        UNIQUE INDEX value_idx(value(15))
    );
    """

# List of static tables
STATIC_TABLES = CREATE_STATIC_TABLE_CMDS.keys()

# The MySQL-object
_db = None

# After connecting with the database the following variables will contain the corresponding functions from the wrapped MySQL-object.
query = None
list_tables = None

def connect():
    """Connects to the database server with the information from the config file."""
    global _db,query,list_tables
    _db = MySQL(config.get("database","mysql_user"),
                config.get("database","mysql_password"),
                config.get("database","mysql_db"),
                config.get("database","mysql_host"))
    query = _db.query
    list_tables = _db.list_tables


def query_dict(query,**args):
    """Queries the database like query but returns results as dictionary."""
    _db.useDict = True
    _db.query(query,**args)
    _db.useDict = False


def create_table(name):
    """Creates the given table (either a static table or a tag-table, which must begin with "tag_")."""
    if name in CREATE_STATIC_TABLE_CMDS:
        query(CREATE_STATIC_TABLE_CMDS[name])
    elif name.startswith("tag_"):
        query(CREATE_TAG_TABLE_CMD,name)
    else: raise Exception("Unknown table name: {0}".format(name))


def get_tagnames():
    """Returns a list with all tagnames which are in the tagids-table."""
    return [row[0] for row in query("SELECT tagname FROM tagids")]


def get_tagid(tagname):
    """Returns the id of tag <tagname>, or None if the tag doesn't exist in the tagids-table."""
    return query("SELECT id FROM tagids WHERE name='?';", tagname).get_single()


def check_tables(create_tables=False,insert_tagids=False):
    """Checks if all necessary tables exists and creates them if <create_tables> is true. Prints a warning if the database contains tables which are not necessary. If <insert_tagids> is true, this method inserts missing tags into the tagids-table ensuring that it contains at least the tags which are given in the indexed_tags-option. In any case it prints warnings if something is wrong with that table."""
    existent_tables = set(list_tables())
    necessary_tables = set(STATIC_TABLES)
    indexed_tags = config.get("tags","indexed_tags").split(",")
    for tag in indexed_tags:
        necessary_tables.add("tag_{0}".format(tag))
    superflous_tables = existent_tables - necessary_tables
    missing_tables = necessary_tables - existent_tables
    if len(superflous_tables) > 0:
        print("Warning: Superflous tables found: ",end="")
        print(superflous_tables)
    if len(missing_tables) > 0:
        if create_tables:
            for table in missing_tables:
                print("Table {0} is missing...".format(table),end="")
                create_table(table)
                print("created")
        else: raise Exception("Missing tables found: {0}".format(missing_tables))

    # In the second part of this method we check if the tags in tagids are consistent with those in the indexed_tags-option.
    existent_tables = set(list_tables())
    if "tagids" in existent_tables:
        tags_in_table = get_tagnames()
        for tag in tags_in_table:
            if not tag in indexed_tags:
                print("Warning: tagids-table contains the tag '{0}' which is not listed in the indexed_tags-options.".format(tag))
        if insert_tagids:
            for tag in indexed_tags:
                if not tag in tags_in_table:
                    print("Tag '{0}' missing in tagids-table...".format(tag),end="")
                    query("INSERT INTO tagids(tagname) VALUES ('?')",tag)
                    print("inserted")
        else:
            missing_tagids = set(indexed_tags) - set(tags_in_table)
            if len(missing_tagids) > 0:
                raise Exception("Some tags are missing in tagids-table: {0}".format(missing_tagids))


def _check_foreign_key(table,key,ref_table,ref_key,tablename=None):
    """Checks whether each value in <table>.<key> is also contained in <ref_table>.<ref_key>. Prints a warning otherwise. If given, <tablename> will be used in this warning <tablename> instead of <table> so subqueries may be used in <table>."""
    result = query("SELECT COUNT(*) FROM ? WHERE ? NOT IN (SELECT ? FROM ?)",table,key,ref_key,ref_table).get_single()
    if result > 0:
        if tablename == None:
            tablename = table
        print("Warning: Foreign key '{0}' in table '{1}' has {2} broken entries.".format(key,tablename,result))


def check_foreign_keys():
    """Checks foreign key constraints in the database as the current MySQL doesn't support such constraints by itself (at least not in MyISAM). A foreign key is a column which values must be contained in another column in another table (the referenced table). For example: Every container_id-value in the contents-table must have a corresponding entry in the container-table."""
    print("Checking foreign keys in database...")
    # Argument sets to use with _check_foreign_key
    foreign_keys = [("contents","container_id","containers","id"),
                    ("contents","element_id","containers","id"),
                    ("files","container_id","containers","id"),
                    ("othertags","container_id","containers","id"),
                    ("tags","container_id","containers","id"),
                    ("tags","tag_id","tagids","id")
                  ]
    # Ok now things get messier...as the value ids in tags must be found in the corresponding tag-table we use a subquery to select only a part of tags with identical tag_id.
    for tagid,tagname in query("SELECT id,tagname FROM tagids"):
        foreign_keys.append(("(SELECT value_id FROM tags WHERE tag_id={0}) AS subtable".format(tagid),
                             "value_id","tag_{0}".format(tagname),"id","tags"))

    for args in foreign_keys:
        _check_foreign_key(*args)
    print("...done")


def update_element_counters():
    """Updates the elements-column of the containers-table."""
    print("Updating element counters...",end="")
    query("UPDATE containers SET elements = (SELECT COUNT(*) FROM contents WHERE container_id = id)")
    print("done")


# If this script is run directly it just performes the database check - without changing the DB.
if __name__=="__main__":
    connect()
    check_tables(create_tables=False,insert_tagids=False)
    check_foreign_keys()