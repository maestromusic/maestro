# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

import config
import constants
import mysql
import omg

STATIC_TABLES = ["containers", "contents", "files", "tags", "tagids", "othertags"]
# Tabellen die unabhängig von der Config existieren

CREATE_TABLE_COMMANDS = {
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
        id MEDIUMINT UNSIGNED NOT NULL,
        path VARCHAR(511) UNIQUE,
        hash VARCHAR(63) UNIQUE,
        verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY(id),
        INDEX path_idx(path),
        INDEX hash_idx(hash)
    );
    """,
    
    "tags": """
    CREATE TABLE tags (
        song_id MEDIUMINT UNSIGNED NOT NULL,
        tag_id SMALLINT UNSIGNED NOT NULL,
        value_id MEDIUMINT UNSIGNED NOT NULL,
        INDEX tag_value_idx(tag_id,value_id),
        INDEX song_idx(song_id)
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
        id MEDIUMINT UNSIGNED NOT NULL,
        tagname VARCHAR(63),
        value VARCHAR(255)
    );"""
    }
    
CREATE_TAG_TABLE_CMD = """
    CREATE TABLE tag_{0} (
        id MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
        value VARCHAR(255) UNIQUE NOT NULL,
        PRIMARY KEY(id),
        INDEX value_idx(value(15))
    );
    """

def create_table(name, **kwargs):
    """Creates a table in the SQL database.
    
    If name denotes a static table, there should be no keyword args. Otherwise, provide
    keyword args as follows:
        *) for name=tag, provide tagname=<string>
    """
    if name in STATIC_TABLES:
        command=CREATE_TABLE_COMMANDS[name]
    elif name=="tag":
        command=CREATE_TAG_TABLE_CMD.format(kwargs["tagname"])
    else:
        raise Exception("Unknown Table name: {0}".format(name))
    print("executing SQL command: {0}".format(command))
    omg._db.query(command)

def get_tagid(tagname):
    """Returns the id of tag <tagname>, or None if the tag doesn't exist in the tagids table."""
    return omg._db.query("SELECT id FROM tagids WHERE 'name'='?';", tagname).get_single()
    
    
def check_tables():
    """Checks the existing database layout.
    
    If there is anything inside the symmetric difference of the existent and the
    necessary tables, this function will do something (print warnings ATM)."""
    #TODO: check each field, create necessary tables
    indexed_tags=config.get("tags","indexed_tags").split(",")
    existent_tables = set(omg._db.list_tables())
    should_exist_tables = set(STATIC_TABLES)
    for tag in indexed_tags:
        should_exist_tables.add("tag_{0}".format(tag))
    superflous_tables = existent_tables - should_exist_tables
    missing_tables = should_exist_tables - existent_tables
    print("Superflous: ")
    print(superflous_tables)
    print("Missing: ")
    print(missing_tables)
    for missing in missing_tables: # first: check static tables
        if missing in STATIC_TABLES: # these ones are easayyy
            create_table(missing)
    for missing in missing_tables:
        if missing.startswith("tag_"):
            # we are missing a tag table!
            tagname = missing.split("_",1)[1]
            create_table("tag",tagname=tagname)
            if not get_tagid(tagname): #make sure the tag exists in the tagtable afterwards
                omg._db.query("INSERT INTO tagids(tagname) VALUES('?')", tagname)
            
            

if __name__=="__main__":
    config.init(constants.CONFIG)
    omg.init()
    check_tables()
    