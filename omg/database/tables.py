# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""Module to manage the database tables used by OMG."""

import re

from .sql import DBException
from .. import constants, database as db
  
  
class SQLTable:
    """A table in the database.
    
    This class contains methods to create, check and drop a table in an SQL database. Note that instantiating
    SQLTable does not create an actual table or modify the database in any way. The class has three public
    attributes:

        * createQueries: maps db type to a list of queries necessary to create the table and associated 
        indexes and triggers. The first query must be a 'CREATE TABLE' query.
        * name: contains the name of the table including the optional prefix. This is extracted from the
          first createQuery.
        * columns: the names of the columns
    """
    def __init__(self, createQueries):
        # replace {p} by db.prefix
        self.createQueries = {key: [query.format(p=db.prefix) for query in queries]
                              for key, queries in createQueries.items()}
        result = re.match("\s*CREATE\s*TABLE\s*(\w+)\s*\((.*)\)", self.createQueries[db.type][0], re.I|re.S)
        if result is None:
            raise DBException("First create query must be a 'CREATE TABLE' query: {}"
                              .format(self.createQueries[db.type][0]))
        self.name = result.group(1)
        lines = result.group(2).split('\n')
        columns = [line.split()[0] for line in lines if len(line.split()) > 0]
        # Filter out definitions of keys, indexes etc.
        # See https://dev.mysql.com/doc/refman/5.5/en/create-table.html
        # or  https://www.sqlite.org/lang_createtable.html
        specialWords = ["CONSTRAINT","PRIMARY","KEY","INDEX","UNIQUE","FULLTEXT","SPATIAL","FOREIGN","CHECK"]
        self.columns = [c for c in columns if c not in specialWords]

    def exists(self):
        """Return whether this table exists in the database."""
        return self.name in db.listTables()
        
    def create(self):
        """Create this table by executing its createQuery."""
        if self.exists():
            raise DBException("Table '{}' does already exist.".format(self.name))
        print("Creating", self.name)
        for query in self.createQueries[db.type]:
            print(query)
            db.query(query)
    
    def reset(self):
        """Drop this table and create it without data again. All table rows will be lost!"""
        if self.exists():
            # Indexes and triggers are deleted automatically
            db.query("DROP TABLE {}".format(self.name))
                
        self.create()


tables = []

def _addMySQL(*queries):
    tables.append({'mysql': queries})
        
def _addSQLite(*queries):
    assert 'sqlite' not in tables[-1]
    tables[-1]['sqlite'] = queries

#----------#
# elements #
#----------#
_addMySQL("""
CREATE TABLE {p}elements (
    id          MEDIUMINT UNSIGNED  NOT NULL,
    domain      SMALLINT  UNSIGNED  NOT NULL,
    file        BOOLEAN             NOT NULL,
    type        TINYINT   UNSIGNED  NOT NULL DEFAULT 0,
    elements    SMALLINT  UNSIGNED  NOT NULL DEFAULT 0,
    PRIMARY KEY(id),
    FOREIGN KEY(domain) REFERENCES {p}domains(id)
) ENGINE InnoDB, CHARACTER SET 'utf8'
""")
_addSQLite("""
CREATE TABLE {p}elements (
    id          INTEGER PRIMARY KEY,
    domain      INTEGER             NOT NULL,
    file        BOOLEAN             NOT NULL DEFAULT 0,
    type        INTEGER             NOT NULL DEFAULT 0,
    elements    INTEGER             NOT NULL DEFAULT 0,
    FOREIGN KEY(domain) REFERENCES {p}domains(id)
)
""")

#----------#
# contents #
#----------#
_addMySQL("""
CREATE TABLE {p}contents (
    container_id MEDIUMINT UNSIGNED NOT NULL,
    position     SMALLINT  UNSIGNED NOT NULL,
    element_id   MEDIUMINT UNSIGNED NOT NULL,
    PRIMARY KEY(container_id,position),
    INDEX element_idx(element_id),
    FOREIGN KEY(container_id) REFERENCES {p}elements(id) ON DELETE CASCADE,
    FOREIGN KEY(element_id) REFERENCES {p}elements(id) ON DELETE CASCADE
) ENGINE InnoDB, CHARACTER SET 'utf8'
""")
_addSQLite("""
CREATE TABLE {p}contents (
    container_id MEDIUMINT UNSIGNED NOT NULL,
    position     SMALLINT  UNSIGNED NOT NULL,
    element_id   MEDIUMINT UNSIGNED NOT NULL,
    PRIMARY KEY(container_id,position),
    FOREIGN KEY(container_id) REFERENCES {p}elements(id) ON DELETE CASCADE,
    FOREIGN KEY(element_id) REFERENCES {p}elements(id) ON DELETE CASCADE
)
""",
"CREATE INDEX {p}contents_element_idx ON {p}contents (element_id)"
)

#-------#
# files #
#-------#
_addMySQL("""
CREATE TABLE {p}files (
    element_id MEDIUMINT UNSIGNED NOT NULL,
    url        VARCHAR(511)       NOT NULL,
    hash       VARCHAR(63),
    verified   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    length     MEDIUMINT UNSIGNED NOT NULL,
    PRIMARY KEY(element_id),
    INDEX url_idx(url(333)),
    INDEX hash_idx(hash),
    INDEX length_idx(length),
    FOREIGN KEY(element_id) REFERENCES {p}elements(id) ON DELETE CASCADE
) ENGINE InnoDB, CHARACTER SET 'utf8'
""")
_addSQLite("""
CREATE TABLE {p}files (
    element_id MEDIUMINT UNSIGNED NOT NULL,
    url        VARCHAR(511)       NOT NULL,
    hash       VARCHAR(63),
    verified   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    length     MEDIUMINT UNSIGNED NOT NULL,
    FOREIGN KEY(element_id) REFERENCES {p}elements(id) ON DELETE CASCADE
)
""",
"CREATE INDEX {p}files_url_idx ON {p}files (url)",
"CREATE INDEX {p}files_hash_idx ON {p}files (hash)",
"CREATE INDEX {p}files_length_idx ON {p}files (length)",
"""
CREATE TRIGGER {p}files_timestamp_trg AFTER UPDATE ON {p}files
BEGIN
UPDATE {p}files SET verified = CURRENT_TIMESTAMP WHERE element_id = new.element_id;
END
"""
)

#--------#
# tagids #
#--------#
_addMySQL("""
CREATE TABLE {p}tagids (
    id       SMALLINT UNSIGNED             NOT NULL AUTO_INCREMENT,
    tagname  VARCHAR(63)                   NOT NULL,
    tagtype  ENUM('varchar','date','text') NOT NULL DEFAULT 'varchar',
    title    VARCHAR(63)                   DEFAULT NULL,
    icon     VARCHAR(255)                  DEFAULT NULL,
    private  BOOLEAN                       NOT NULL,
    sort     SMALLINT UNSIGNED             NOT NULL,
    PRIMARY KEY(id),
    UNIQUE INDEX(tagname)
) ENGINE InnoDB, CHARACTER SET 'utf8'
""")
_addSQLite("""
CREATE TABLE {p}tagids (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    tagname  VARCHAR(63)                   NOT NULL UNIQUE,
    tagtype  VARCHAR(7)                    NOT NULL DEFAULT 'varchar',
    title    VARCHAR(63)                   DEFAULT NULL,
    icon     VARCHAR(255)                  DEFAULT NULL,
    private  BOOLEAN                       NOT NULL DEFAULT 0,
    sort     INTEGER                       NOT NULL DEFAULT -1
)
""")

#------#
# tags #
#------#
_addMySQL("""
CREATE TABLE {p}tags (
    element_id MEDIUMINT UNSIGNED NOT NULL,
    tag_id     SMALLINT  UNSIGNED NOT NULL,
    value_id   MEDIUMINT UNSIGNED NOT NULL,
    INDEX tag_value_idx(tag_id,value_id),
    INDEX element_idx(element_id),
    FOREIGN KEY(element_id) REFERENCES {p}elements(id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES {p}tagids(id) ON DELETE CASCADE
) ENGINE InnoDB, CHARACTER SET 'utf8'
""")
_addSQLite("""
CREATE TABLE {p}tags (
    element_id MEDIUMINT UNSIGNED NOT NULL,
    tag_id     SMALLINT  UNSIGNED NOT NULL,
    value_id   MEDIUMINT UNSIGNED NOT NULL,
    FOREIGN KEY(element_id) REFERENCES {p}elements(id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES {p}tagids(id) ON DELETE CASCADE
)
""",
"CREATE INDEX {p}tags_tag_value_idx ON {p}tags (tag_id,value_id)",
"CREATE INDEX {p}tags_element_idx ON {p}tags (element_id)")

#----------------#
# values_varchar #
#----------------#
_addMySQL("""
CREATE TABLE {0}values_varchar (
    id              MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tag_id          SMALLINT  UNSIGNED NOT NULL,
    value           VARCHAR({1})       NOT NULL,
    sort_value      VARCHAR({1}),
    search_value    VARCHAR({1}),
    hide            BOOLEAN            NOT NULL,
    PRIMARY KEY(id),
    INDEX tag_value_idx(tag_id,value),
    FOREIGN KEY(tag_id) REFERENCES {0}tagids(id) ON DELETE CASCADE
) ENGINE InnoDB, CHARACTER SET 'utf8'
""".format(db.prefix, constants.TAG_VARCHAR_LENGTH))
_addSQLite("""
CREATE TABLE {0}values_varchar (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_id          SMALLINT  UNSIGNED NOT NULL,
    value           VARCHAR({1})       NOT NULL,
    sort_value      VARCHAR({1}),
    search_value    VARCHAR({1}),
    hide            BOOLEAN            NOT NULL DEFAULT 0,
    FOREIGN KEY(tag_id) REFERENCES {0}tagids(id) ON DELETE CASCADE
)
""".format(db.prefix, constants.TAG_VARCHAR_LENGTH),
"CREATE INDEX {p}values_varchar_idx ON {p}values_varchar (value)")

#-------------#
# values_text #
#-------------#
_addMySQL("""
CREATE TABLE {p}values_text (
    id     MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tag_id SMALLINT  UNSIGNED NOT NULL,
    value  TEXT               NOT NULL,
    PRIMARY KEY(id),
    INDEX tag_value_idx(tag_id,value(10)),
    FOREIGN KEY(tag_id) REFERENCES {p}tagids(id) ON DELETE CASCADE
) ENGINE InnoDB, CHARACTER SET 'utf8'
""")
_addSQLite("""
CREATE TABLE {p}values_text (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_id SMALLINT  UNSIGNED NOT NULL,
    value  TEXT               NOT NULL,
    FOREIGN KEY(tag_id) REFERENCES {p}tagids(id) ON DELETE CASCADE
)
""",
"CREATE INDEX {p}values_text_idx ON {p}values_text (value)")

#-------------#
# values_date #
#-------------#
_addMySQL("""
CREATE TABLE {p}values_date (
    id     MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tag_id SMALLINT  UNSIGNED NOT NULL,
    value  INT       UNSIGNED NOT NULL,
    PRIMARY KEY(id),
    INDEX tag_value_idx(tag_id,value),
    FOREIGN KEY(tag_id) REFERENCES {p}tagids(id) ON DELETE CASCADE
) ENGINE InnoDB, CHARACTER SET 'utf8'
""")
_addSQLite("""
CREATE TABLE {p}values_date (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_id SMALLINT  UNSIGNED NOT NULL,
    value  INT       UNSIGNED NOT NULL,
    FOREIGN KEY(tag_id) REFERENCES {p}tagids(id) ON DELETE CASCADE
)
""",
"CREATE INDEX {p}values_date_idx ON {p}values_date (value)")

#------------#
# flag_names #
#------------#
_addMySQL("""
CREATE TABLE {}flag_names (
    id      SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name    VARCHAR({})       NOT NULL,
    icon    VARCHAR(255)      DEFAULT NULL,
    PRIMARY KEY(id)
) ENGINE InnoDB, CHARACTER SET 'utf8'
""".format(db.prefix, constants.FLAG_VARCHAR_LENGTH))
_addSQLite("""
CREATE TABLE {}flag_names (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    VARCHAR({})       NOT NULL,
    icon    VARCHAR(255)      DEFAULT NULL
)
""".format(db.prefix, constants.FLAG_VARCHAR_LENGTH))

#-------#
# flags #
#-------#
_addMySQL("""
CREATE TABLE {p}flags (
    element_id      MEDIUMINT UNSIGNED NOT NULL,
    flag_id         SMALLINT UNSIGNED NOT NULL,
    UNIQUE INDEX flag_idx(element_id,flag_id),
    FOREIGN KEY(element_id) REFERENCES {p}elements(id) ON DELETE CASCADE,
    FOREIGN KEY(flag_id) REFERENCES {p}flag_names(id) ON DELETE CASCADE
) ENGINE InnoDB
""")
_addSQLite("""
CREATE TABLE {p}flags (
    element_id      MEDIUMINT UNSIGNED NOT NULL,
    flag_id         SMALLINT UNSIGNED NOT NULL,
    FOREIGN KEY(element_id) REFERENCES {p}elements(id) ON DELETE CASCADE,
    FOREIGN KEY(flag_id) REFERENCES {p}flag_names(id) ON DELETE CASCADE
)
""",
"CREATE UNIQUE INDEX {p}flags_idx ON {p}flags (element_id,flag_id)")

#---------#
# folders #
#---------#
_addMySQL("""
CREATE TABLE {p}folders (
    path         VARCHAR(511)    NOT NULL,
    state        TINYINT NOT NULL DEFAULT 0
) ENGINE InnoDB, CHARACTER SET 'utf8'
""")
_addSQLite("""
CREATE TABLE {p}folders (
    path         VARCHAR(511)    NOT NULL,
    state        INTEGER NOT NULL DEFAULT 0
)
""")

#----------#
# newfiles #
#----------#
_addMySQL("""
CREATE TABLE {p}newfiles (
    url        VARCHAR(511)       NOT NULL,
    hash       VARCHAR(63),
    verified   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX url_idx(url(333)),
    INDEX hash_idx(hash)
) ENGINE InnoDB, CHARACTER SET 'utf8'
""")
_addSQLite("""
CREATE TABLE {p}newfiles (
    url        VARCHAR(511)       NOT NULL,
    hash       VARCHAR(63),
    verified   INTEGER DEFAULT CURRENT_TIMESTAMP
)
""",
"CREATE INDEX {p}newfiles_url_idx ON {p}newfiles (url)",
"CREATE INDEX {p}newfiles_hash_idx ON {p}newfiles (hash)",
"""
CREATE TRIGGER {p}newfiles_timestamp_trg AFTER UPDATE ON {p}newfiles
BEGIN
UPDATE {p}newfiles SET verified = CURRENT_TIMESTAMP WHERE url = new.url;
END
"""
)

#----------#
# stickers #
#----------#
_addMySQL("""
CREATE TABLE {p}stickers (
    element_id  MEDIUMINT UNSIGNED  NOT NULL,
    type        VARCHAR(255)        NOT NULL,
    sort        SMALLINT UNSIGNED   NOT NULL,
    data        TEXT                NOT NULL,
    INDEX stickers_idx(element_id,type,sort),
    FOREIGN KEY(element_id) REFERENCES {p}elements(id) ON DELETE CASCADE
) ENGINE InnoDB, CHARACTER SET 'utf8'
""")
_addSQLite("""
CREATE TABLE {p}stickers (
    element_id  INTEGER         NOT NULL,
    type        VARCHAR(255)    NOT NULL,
    sort        INTEGER         NOT NULL,
    data        TEXT            NOT NULL,
    FOREIGN KEY(element_id) REFERENCES {p}elements(id) ON DELETE CASCADE
)
""",
"CREATE INDEX {p}stickers_idx ON {p}stickers (element_id,type,sort)"
)

#---------#
# domains #
#---------#
_addMySQL("""
CREATE TABLE {p}domains (
    id    SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name  VARCHAR(64),   
    PRIMARY KEY(id),
    UNIQUE INDEX(name)
) ENGINE InnoDB, CHARACTER SET 'utf8'
""")
_addSQLite("""
CREATE TABLE {p}domains (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  VARCHAR(64) NOT NULL UNIQUE
)
""")


tables = [SQLTable(queryDict) for queryDict in tables]

def byName(name):
    """Return the table with the given name, which must include the database prefix."""
    for table in tables:
        if name == table.name:
            return table
    else: return None
    
    
def sortedList():
    """Get all tables in an order such that each table only references tables that appeared earlier
    in the list."""
    # Some tables are referenced by other tables and must therefore be dropped last and created first.
    # The order is important!
    referencedTables = [byName(db.prefix+name) for name in ["domains", "elements", "tagids", "flag_names"]]
    otherTables = [table for table in tables if table not in referencedTables]
    return referencedTables + otherTables
