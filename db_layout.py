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

CREATE_CONTAINERS_TABLE_CMD = """
    CREATE TABLE containers (
        id MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
        name VARCHAR(256) NOT NULL,
        INDEX name_idx(name(10)),
        elements SMALLINT UNSIGNED NOT NULL DEFAULT 0,
        PRIMARY KEY(id)
    );
    """
CREATE_CONTENTS_TABLE_CMD = """
    CREATE TABLE contents (
        container_id MEDIUMINT UNSIGNED NOT NULL,
        position SMALLINT UNSIGNED NOT NULL,
        element_id MEDIUMINT UNSIGNED NOT NULL,
        PRIMARY KEY(container_id,position),
        INDEX element_idx(element_id)
    );
    """
    
CREATE_FILES_TABLE_CMD = """
    CREATE TABLE files (
        id MEDIUMINT UNSIGNED NOT NULL,
        path VARCHAR(512) UNIQUE,
        hash VARCHAR(64) UNIQUE,
        verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY(id),
        INDEX path_idx(path),
        INDEX hash_idx(hash)
    );
    """
CREATE_TAG_TABLE_GENERIC_CMD = """
    CREATE TABLE tag_{0} (
        id MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
        value VARCHAR(128) UNIQUE NOT NULL,
        PRIMARY KEY(id),
        INDEX value_idx(value(15))
    );
    """
CREATE_TAGS_TABLE_CMD = """
    CREATE TABLE tags (
        song_id MEDIUMINT UNSIGNED NOT NULL,
        tag_id SMALLINT UNSIGNED NOT NULL,
        value_id MEDIUMINT UNSIGNED NOT NULL,
        INDEX tag_value_idx(tag_id,value_id),
        INDEX song_idx(song_id)
    );
    """
def create_table(name, tagname=None):
    if name=="containers":
        command=CREATE_CONTAINERS_TABLE_CMD
    elif name=="contents":
        command=CREATE_CONTENTS_TABLE_CMD
    elif name=="files":
        command=CREATE_FILES_TABLE_CMD
    elif name=="tags":
        command=CREATE_TAGS_TABLE_CMD
    elif name=="tag":
        command=CREATE_TAG_TABLE_GENERIC_CMD.format(tagname)
    omg.sql_query(command)

def check_tables():
    indexed_tags=config.get("tags","indexed_tags").split(",")
    existent_tables = set(omg._db.list_tables())
    should_exist_tables = set(["containers", "contents", "files", "tags"])
    for tag in indexed_tags:
        should_exist_tables.add("tag_{0}".format(tag))
    superflous_tables = existent_tables - should_exist_tables
    missing_tables = should_exist_tables - existent_tables
    print("Superflous: ")
    print(superflous_tables)
    print("Missing: ")
    print(missing_tables)

if __name__=="__main__":
    config.init(constants.CONFIG)
    omg.init()
    check_tables()
    