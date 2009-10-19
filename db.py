#!/usr/bin/env python3.1
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
import re
import logging


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
        length MEDIUMINT UNSIGNED NOT NULL,
        PRIMARY KEY(container_id),
        UNIQUE INDEX path_idx(path),
        INDEX hash_idx(hash),
        INDEX length_idx(length)
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
        tagtype ENUM('varchar','date','text') DEFAULT 'varchar',
        PRIMARY KEY(id),
        UNIQUE INDEX(tagname)
    );""",
    
    "othertags":"""
    CREATE TABLE othertags (
        container_id MEDIUMINT UNSIGNED NOT NULL,
        tagname VARCHAR(63),
        value VARCHAR(255),
        INDEX container_id_idx(container_id)
    );"""
    }

# MySQL-command to create a table for a tag with a specific type.  Replace the placeholder before use...
CREATE_TAG_TABLE_CMDS = {
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


# The MySQL-object
_db = None

# After connecting with the database the following variables will contain the corresponding functions from the wrapped MySQL-object.
query = None
list_tables = None
tagtypes = None
logger = None
def connect():
    """Connects to the database server with the information from the config file."""
    global _db,query,list_tables,tagtypes, logger
    logger = logging.getLogger(name="db")
    _db = MySQL(config.get("database","mysql_user"),
                config.get("database","mysql_password"),
                config.get("database","mysql_db"),
                config.get("database","mysql_host"))
    query = _db.query
    list_tables = _db.list_tables
    tagtypes = _parse_indexed_tags(config.get("tags","indexed_tags"))


def query_dict(query,**args):
    """Queries the database like query but returns results as dictionary."""
    _db.use_dict = True
    omgwtf = _db.query(query,**args)
    _db.use_dict = False
    return omgwtf


def _parse_indexed_tags(string):
    """Parses the given string. This option should contain a comma-separated list of strings of the form tagname(tagtype) where the part in brackets is optional and defaults to 'varchar'. It checks whether the syntax is correct and all types have a corresponding CREATE_TAG_TABLE_CMDS-command and returns a dictionary {tagname : tagtype}. Otherwise an exception is raised."""

    # Matches strings like "   tagname (   tagtype   )   " (the part in brackets is optional) and stores the interesting parts in the first and third group.
    prog = re.compile('\s*(\w+)\s*(\(\s*(\w*)\s*\))?\s*$')
    tags = {}
    for tagstring in string.split(","):
        result = prog.match(tagstring)
        if result == None:
            raise Exception("Invalid syntax in the indexed_tags-option of the config-file ('{0}').".format(tagstring))
        tagname = result.groups()[0]
        tagtype = result.groups()[2]
        if not tagtype:
            tagtype = "varchar"
        if tagtype.lower() not in CREATE_TAG_TABLE_CMDS.keys():
            raise Exception("Unsupported tag type '{0}' in the indexed_tags-option of the config-file.".format(tagtype))
        tags[tagname] = tagtype
    return tags


def get_tagnames():
    """Returns a list with all tagnames which are in the tagids-table."""
    return [row[0] for row in query("SELECT tagname FROM tagids")]


def get_tagid(tagname):
    """Returns the id of tag <tagname>, or None if the tag doesn't exist in the tagids-table."""
    return query("SELECT id FROM tagids WHERE name='?';", tagname).get_single()


def check_tables(create_tables=False,insert_tagids=False):
    """Checks if all necessary tables exists and creates them if <create_tables> is true. Prints a warning if the database contains tables which are not necessary. If <insert_tagids> is true, this method inserts missing tags into the tagids-table ensuring that it contains at least the tags which are given in the indexed_tags-option. In any case it prints warnings if something is wrong with that table."""
    existent_tables = set(list_tables())
    # While existent_tables is just a set, necessary_tables is a dictionary with the corresponding SQL-commands as values.
    necessary_tables = CREATE_STATIC_TABLE_CMDS.copy()
    indexed_tags = _parse_indexed_tags(config.get("tags","indexed_tags"))
    for tag,tagtype in indexed_tags.items():
        table = "tag_{0}".format(tag)
        necessary_tables[table] = CREATE_TAG_TABLE_CMDS[tagtype].format(table) # replace placeholder in SQL-command
    superflous_tables = existent_tables - set(necessary_tables.keys())
    missing_tables = {table:command for table,command in necessary_tables.items() if table not in existent_tables}
    if len(superflous_tables) > 0:
        print("Warning: Superflous tables found: ",end="")
        print(superflous_tables)
    if len(missing_tables) > 0:
        if create_tables:
            for table,command in missing_tables.items():
                print("Table {0} is missing...".format(table),end="")
                query(command)
                print("created")
        else: raise Exception("Missing tables found: {0}".format(set(missing_tables.keys())))

    # In the second part of this method we check if the tags in tagids are consistent with those in the indexed_tags-option.
    if "tagids" in list_tables():
        tags_in_table = {tag:tagtype for tag,tagtype in query("SELECT tagname,tagtype FROM tagids")}
        for tag,tagtype in tags_in_table.items():
            if not tag in indexed_tags:
                print("Warning: tagids-table contains the tag '{0}' which is not listed in the indexed_tags-options.".format(tag))
            elif tagtype != indexed_tags[tag]:
                print("Warning: The type of tag '{0}' in tagids-table differs from the type in the config-file.".format(tag))
        if insert_tagids:
            for tag,tagtype in indexed_tags.items():
                if not tag in tags_in_table:
                    print("Tag '{0}' missing in tagids-table...".format(tag),end="")
                    query("INSERT INTO tagids(tagname,tagtype) VALUES ('?','?')",tag,tagtype)
                    print("inserted")
        else:
            missing_tagids = [tag for tag in indexed_tags if not tag in tags_in_table]
            if len(missing_tagids) > 0:
                raise Exception("Some tags are missing in tagids-table: {0}".format(missing_tagids))


def _check_foreign_key(table,key,ref_table,ref_key,tablename=None,autofix=False):
    """Checks whether each value in <table>.<key> is also contained in <ref_table>.<ref_key>. Prints a warning otherwise. If given, <tablename> will be used in this warning <tablename> instead of <table> so subqueries may be used in <table> """
    result = query("SELECT COUNT(*) FROM ? WHERE ? NOT IN (SELECT ? FROM ?)",table,key,ref_key,ref_table).get_single()
    if result > 0:
        if tablename == None:
            tablename = table
        logger.warning("Foreign key '{0}' in table '{1}' has {2} broken entries.".format(key,tablename,result))
        if autofix:
            logger.warning("Deleting {0} entries in table {1}".format(result,tablename))
            query("DELETE FROM ? WHERE ? NOT IN (SELECT ? FROM ?)",table,key,ref_key,ref_table)


def check_foreign_keys(autofix=False):
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
        tablename = "tag_{0}".format(tagname)
        if tablename in list_tables(): # If something's wrong with the tagids-table, tablename may not exist
            foreign_keys.append(("(SELECT value_id FROM tags WHERE tag_id={0}) AS subtable".format(tagid),
                                "value_id",tablename,"id","tags"))
            foreign_keys.append((tablename, "id", "tags", "value_id")) # aus db-theoretischer sicht kein foreign key :-p

    for args in foreign_keys:
        _check_foreign_key(*args,autofix=autofix)
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
