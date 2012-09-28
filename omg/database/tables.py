# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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
    SQLTable does not create an actual table or modify the database in any way. The class has two public
    attributes:

        * createQueries: contains the queries which can be used to create the table. The first query must be
          a 'CREATE TABLE' query. Further queries may add indexes and triggers.
        * name: contains the name of the table including the optional prefix. This is extracted from the
          first createQuery.
    """
    def __init__(self,createQueries):
        self.createQueries = createQueries
        result = re.match("\s*CREATE\s*TABLE\s*(\w+)",createQueries[0],re.I)
        if result is None:
            raise DBException("First create query must be a 'CREATE TABLE' query: {}"
                              .format(createQueries[0]))
        else: self.name = result.group(1)

    def exists(self):
        """Return whether this table exists in the database."""
        return self.name in db.listTables()
        
    def create(self):
        """Create this table by executing its createQuery."""
        if self.exists():
            raise DBException("Table '{}' does already exist.".format(self.name))
        for query in self.createQueries:
            db.query(query)
    
    def reset(self):
        """Drop this table and create it without data again. All table rows will be lost!"""
        if self.exists():
            # Indexes and triggers are deleted automatically
            db.query("DROP TABLE {}".format(self.name))
                
        self.create()


tables = []

def _addMySQL(*queries):
    if db.type == 'mysql':
        tables.append(queries)
        
def _addSQLite(*queries):
    if db.type == 'sqlite':
        tables.append(queries)

#----------#
# elements #
#----------#
_addMySQL("""
CREATE TABLE {}elements (
    id          MEDIUMINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    file        BOOLEAN             NOT NULL,
    toplevel    BOOLEAN             NOT NULL,
    elements    SMALLINT  UNSIGNED  NOT NULL DEFAULT 0,
    major       BOOLEAN             NOT NULL,
    PRIMARY KEY(id)
) ENGINE InnoDB, CHARACTER SET 'utf8'
""".format(db.prefix))
_addSQLite("""
CREATE TABLE {}elements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file        BOOLEAN             NOT NULL DEFAULT 0,
    toplevel    BOOLEAN             NOT NULL DEFAULT 0,
    elements    SMALLINT  UNSIGNED  NOT NULL DEFAULT 0,
    major       BOOLEAN             NOT NULL DEFAULT 0
)
""".format(db.prefix))

#----------#
# contents #
#----------#
_addMySQL("""
CREATE TABLE {0}contents (
    container_id MEDIUMINT UNSIGNED NOT NULL,
    position     SMALLINT  UNSIGNED NOT NULL,
    element_id   MEDIUMINT UNSIGNED NOT NULL,
    PRIMARY KEY(container_id,position),
    INDEX element_idx(element_id),
    FOREIGN KEY(container_id) REFERENCES {0}elements(id) ON DELETE CASCADE,
    FOREIGN KEY(element_id) REFERENCES {0}elements(id) ON DELETE CASCADE
) ENGINE InnoDB, CHARACTER SET 'utf8'
""".format(db.prefix))
_addSQLite("""
CREATE TABLE {0}contents (
    container_id MEDIUMINT UNSIGNED NOT NULL,
    position     SMALLINT  UNSIGNED NOT NULL,
    element_id   MEDIUMINT UNSIGNED NOT NULL,
    PRIMARY KEY(container_id,position),
    FOREIGN KEY(container_id) REFERENCES {0}elements(id) ON DELETE CASCADE,
    FOREIGN KEY(element_id) REFERENCES {0}elements(id) ON DELETE CASCADE
)
""".format(db.prefix),
"CREATE INDEX contents_element_idx ON {}contents (element_id)".format(db.prefix)
)

#-------#
# files #
#-------#
_addMySQL("""
CREATE TABLE {0}files (
    element_id MEDIUMINT UNSIGNED NOT NULL,
    url        VARCHAR(511)       NOT NULL,
    hash       VARCHAR(63),
    verified   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    length     MEDIUMINT UNSIGNED NOT NULL,
    PRIMARY KEY(element_id),
    INDEX url_idx(url(333)),
    INDEX hash_idx(hash),
    INDEX length_idx(length),
    FOREIGN KEY(element_id) REFERENCES {0}elements(id) ON DELETE CASCADE
) ENGINE InnoDB, CHARACTER SET 'utf8'
""".format(db.prefix))
_addSQLite("""
CREATE TABLE {0}files (
    element_id MEDIUMINT UNSIGNED NOT NULL,
    url        VARCHAR(511)       NOT NULL,
    hash       VARCHAR(63),
    verified   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    length     MEDIUMINT UNSIGNED NOT NULL,
    FOREIGN KEY(element_id) REFERENCES {0}elements(id) ON DELETE CASCADE
)
""".format(db.prefix),
"CREATE INDEX files_url_idx ON {}files (url)".format(db.prefix),
"CREATE INDEX files_hash_idx ON {}files (hash)".format(db.prefix),
"CREATE INDEX files_length_idx ON {}files (length)".format(db.prefix),
"""
CREATE TRIGGER files_timestamp_trg AFTER UPDATE ON {0}files
BEGIN
UPDATE {0}files SET verified = CURRENT_TIMESTAMP WHERE element_id = new.element_id;
END
""".format(db.prefix)
)

#--------#
# tagids #
#--------#
_addMySQL("""
CREATE TABLE {0}tagids (
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
""".format(db.prefix))
_addSQLite("""
CREATE TABLE {}tagids (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    tagname  VARCHAR(63)                   NOT NULL UNIQUE,
    tagtype  VARCHAR(7)                    NOT NULL DEFAULT 'varchar',
    title    VARCHAR(63)                   DEFAULT NULL,
    icon     VARCHAR(255)                  DEFAULT NULL,
    private  BOOLEAN                       NOT NULL DEFAULT 0,
    sort     INTEGER                       NOT NULL DEFAULT -1
)
""".format(db.prefix))

#------#
# tags #
#------#
_addMySQL("""
CREATE TABLE {0}tags (
    element_id MEDIUMINT UNSIGNED NOT NULL,
    tag_id     SMALLINT  UNSIGNED NOT NULL,
    value_id   MEDIUMINT UNSIGNED NOT NULL,
    INDEX tag_value_idx(tag_id,value_id),
    INDEX element_idx(element_id),
    FOREIGN KEY(element_id) REFERENCES {0}elements(id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES {0}tagids(id) ON DELETE CASCADE
) ENGINE InnoDB, CHARACTER SET 'utf8'
""".format(db.prefix))
_addSQLite("""
CREATE TABLE {0}tags (
    element_id MEDIUMINT UNSIGNED NOT NULL,
    tag_id     SMALLINT  UNSIGNED NOT NULL,
    value_id   MEDIUMINT UNSIGNED NOT NULL,
    FOREIGN KEY(element_id) REFERENCES {0}elements(id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES {0}tagids(id) ON DELETE CASCADE
)
""".format(db.prefix),
"CREATE INDEX tags_tag_value_idx ON {}tags (tag_id,value_id)".format(db.prefix),
"CREATE INDEX tags_element_idx ON {}tags (element_id)".format(db.prefix))

#----------------#
# values_varchar #
#----------------#
_addMySQL("""
CREATE TABLE {0}values_varchar (
    id              MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tag_id          SMALLINT  UNSIGNED NOT NULL,
    value           VARCHAR({1})       NOT NULL,
    sort_value      VARCHAR({1}),
    hide            BOOLEAN            NOT NULL,
    PRIMARY KEY(id),
    INDEX tag_value_idx(tag_id,value),
    FOREIGN KEY(tag_id) REFERENCES {0}tagids(id) ON DELETE CASCADE
) ENGINE InnoDB, CHARACTER SET 'utf8'
""".format(db.prefix,constants.TAG_VARCHAR_LENGTH))
_addSQLite("""
CREATE TABLE {0}values_varchar (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_id     SMALLINT  UNSIGNED NOT NULL,
    value      VARCHAR({1})       NOT NULL,
    sort_value VARCHAR({1}),
    hide       BOOLEAN            NOT NULL DEFAULT 0,
    FOREIGN KEY(tag_id) REFERENCES {0}tagids(id) ON DELETE CASCADE
)
""".format(db.prefix,constants.TAG_VARCHAR_LENGTH),
"CREATE INDEX values_varchar_idx ON {}values_varchar (value)".format(db.prefix))

#-------------#
# values_text #
#-------------#
_addMySQL("""
CREATE TABLE {0}values_text (
    id     MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tag_id SMALLINT  UNSIGNED NOT NULL,
    value  TEXT               NOT NULL,
    PRIMARY KEY(id),
    INDEX tag_value_idx(tag_id,value(10)),
    FOREIGN KEY(tag_id) REFERENCES {0}tagids(id) ON DELETE CASCADE
) ENGINE InnoDB, CHARACTER SET 'utf8'
""".format(db.prefix))
_addSQLite("""
CREATE TABLE {0}values_text (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_id SMALLINT  UNSIGNED NOT NULL,
    value  TEXT               NOT NULL,
    FOREIGN KEY(tag_id) REFERENCES {0}tagids(id) ON DELETE CASCADE
)
""".format(db.prefix),
"CREATE INDEX values_text_idx ON {}values_text (value)".format(db.prefix))

#-------------#
# values_date #
#-------------#
_addMySQL("""
CREATE TABLE {0}values_date (
    id     MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tag_id SMALLINT  UNSIGNED NOT NULL,
    value  INT       UNSIGNED NOT NULL,
    PRIMARY KEY(id),
    INDEX tag_value_idx(tag_id,value),
    FOREIGN KEY(tag_id) REFERENCES {0}tagids(id) ON DELETE CASCADE
) ENGINE InnoDB, CHARACTER SET 'utf8'
""".format(db.prefix))
_addSQLite("""
CREATE TABLE {0}values_date (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_id SMALLINT  UNSIGNED NOT NULL,
    value  INT       UNSIGNED NOT NULL,
    FOREIGN KEY(tag_id) REFERENCES {0}tagids(id) ON DELETE CASCADE
)
""".format(db.prefix),
"CREATE INDEX values_date_idx ON {}values_date (value)".format(db.prefix))

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
""".format(db.prefix,constants.FLAG_VARCHAR_LENGTH))
_addSQLite("""
CREATE TABLE {}flag_names (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    VARCHAR({})       NOT NULL,
    icon    VARCHAR(255)      DEFAULT NULL
)
""".format(db.prefix,constants.FLAG_VARCHAR_LENGTH))

#-------#
# flags #
#-------#
_addMySQL("""
CREATE TABLE {0}flags (
    element_id      MEDIUMINT UNSIGNED NOT NULL,
    flag_id         SMALLINT UNSIGNED NOT NULL,
    UNIQUE INDEX flag_idx(element_id,flag_id),
    FOREIGN KEY(element_id) REFERENCES {0}elements(id) ON DELETE CASCADE,
    FOREIGN KEY(flag_id) REFERENCES {0}flag_names(id) ON DELETE CASCADE
) ENGINE InnoDB
""".format(db.prefix))
_addSQLite("""
CREATE TABLE {0}flags (
    element_id      MEDIUMINT UNSIGNED NOT NULL,
    flag_id         SMALLINT UNSIGNED NOT NULL,
    FOREIGN KEY(element_id) REFERENCES {0}elements(id) ON DELETE CASCADE,
    FOREIGN KEY(flag_id) REFERENCES {0}flag_names(id) ON DELETE CASCADE
)
""".format(db.prefix),
"CREATE UNIQUE INDEX flags_idx ON {}flags (element_id,flag_id)".format(db.prefix))

#---------#
# folders #
#---------#
_addMySQL("""
CREATE TABLE {}folders (
    path         VARCHAR(511)    NOT NULL,
    state        TINYINT NOT NULL DEFAULT 0
) ENGINE InnoDB, CHARACTER SET 'utf8'
""".format(db.prefix))
_addSQLite("""
CREATE TABLE {}folders (
    path         VARCHAR(511)    NOT NULL,
    state        INTEGER NOT NULL DEFAULT 0
)
""".format(db.prefix))

#----------#
# newfiles #
#----------#
_addMySQL("""
CREATE TABLE {}newfiles (
    url        VARCHAR(511)       NOT NULL,
    hash       VARCHAR(63),
    verified   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX url_idx(url(333)),
    INDEX hash_idx(hash)
) ENGINE InnoDB, CHARACTER SET 'utf8'
""".format(db.prefix))
_addSQLite("""
CREATE TABLE {}newfiles (
    url        VARCHAR(511)       NOT NULL,
    hash       VARCHAR(63),
    verified   INTEGER DEFAULT CURRENT_TIMESTAMP
)
""".format(db.prefix),
"CREATE INDEX newfiles_url_idx ON {}newfiles (url)".format(db.prefix),
"CREATE INDEX newfiles_hash_idx ON {}newfiles (hash)".format(db.prefix),
"""
CREATE TRIGGER newfiles_timestamp_trg AFTER UPDATE ON {0}newfiles
BEGIN
UPDATE {0}newfiles SET verified = CURRENT_TIMESTAMP WHERE url = new.url;
END
""".format(db.prefix)
)

#------#
# data #
#------#
_addMySQL("""
CREATE TABLE {0}data (
    element_id  MEDIUMINT UNSIGNED  NOT NULL,
    type        VARCHAR(255)        NOT NULL,
    sort        SMALLINT UNSIGNED   NOT NULL,
    data        TEXT                NOT NULL,
    INDEX data_idx(element_id,type,sort),
    FOREIGN KEY(element_id) REFERENCES {0}elements(id) ON DELETE CASCADE
) ENGINE InnoDB, CHARACTER SET 'utf8'
""".format(db.prefix))
_addSQLite("""
CREATE TABLE {0}data (
    element_id  INTEGER         NOT NULL,
    type        VARCHAR(255)    NOT NULL,
    sort        INTEGER         NOT NULL,
    data        TEXT            NOT NULL,
    FOREIGN KEY(element_id) REFERENCES {0}elements(id) ON DELETE CASCADE
)
""".format(db.prefix),
"CREATE INDEX data_idx ON {}data (element_id,type,sort)".format(db.prefix)
)

tables = [SQLTable(queries) for queries in tables]
