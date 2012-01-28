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

"""Module to manage the database tables used by omg."""

import re
from omg import constants,database as db
from omg.database.sql import DBException


class SQLTable:
    """A table in the database.
    
    This class contains methods to create, check and drop a table in an SQL database. Note that instantiating SQLTable does not create an actual table or modify the database in any way. The class has two public attributes:

        * ``createQuery`` contains the query which can be used to create the table and is given in the constructor.
        * ``name`` contains the name of the table including the optional prefix and is extracted from ``createQuery``.
    """
    def __init__(self,createQuery):
        self.createQuery = createQuery
        result = re.match("\s*CREATE\s*TABLE\s*(\w+)",createQuery,re.I)
        if result is None:
            raise DBException("Bad SQL-Query: {}".format(createQuery))
        else: self.name = result.group(1)

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


# Dictionary mapping table names to table objects which are created with the following queries.
tables = [SQLTable(createQuery) for createQuery in (
"""CREATE TABLE {}elements (
        id          MEDIUMINT UNSIGNED  NOT NULL AUTO_INCREMENT,
        file        BOOLEAN             NOT NULL,
        toplevel    BOOLEAN             NOT NULL,
        elements    SMALLINT  UNSIGNED  NOT NULL DEFAULT 0,
        major       BOOLEAN             NOT NULL,
        PRIMARY KEY(id)
    ) ENGINE InnoDB, CHARACTER SET 'utf8';
""".format(db.prefix),
"""CREATE TABLE {0}contents (
        container_id MEDIUMINT UNSIGNED NOT NULL,
        position     SMALLINT  UNSIGNED NOT NULL,
        element_id   MEDIUMINT UNSIGNED NOT NULL,
        PRIMARY KEY(container_id,position),
        INDEX element_idx(element_id),
        FOREIGN KEY(container_id) REFERENCES {0}elements(id) ON DELETE CASCADE,
        FOREIGN KEY(element_id) REFERENCES {0}elements(id) ON DELETE CASCADE
    ) ENGINE InnoDB, CHARACTER SET 'utf8';
""".format(db.prefix),
"""CREATE TABLE {0}files (
        element_id MEDIUMINT UNSIGNED NOT NULL,
        path       VARCHAR(511)       NOT NULL,
        hash       VARCHAR(63),
        verified   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        length     MEDIUMINT UNSIGNED NOT NULL,
        PRIMARY KEY(element_id),
        INDEX path_idx(path(333)),
        INDEX hash_idx(hash),
        INDEX length_idx(length),
        FOREIGN KEY(element_id) REFERENCES {0}elements(id) ON DELETE CASCADE
    ) ENGINE InnoDB, CHARACTER SET 'utf8';
""".format(db.prefix),
"""CREATE TABLE {0}tagids (
        id       SMALLINT UNSIGNED             NOT NULL AUTO_INCREMENT,
        tagname  VARCHAR(63)                   NOT NULL,
        tagtype  ENUM('varchar','date','text') NOT NULL DEFAULT 'varchar',
        title    VARCHAR(63)                   DEFAULT NULL,
        icon     VARCHAR(255)                  DEFAULT NULL,
        sorttags VARCHAR(20)                   NOT NULL,
        private  BOOLEAN                       NOT NULL,
        PRIMARY KEY(id),
        UNIQUE INDEX(tagname)
    ) ENGINE InnoDB, CHARACTER SET 'utf8';
""".format(db.prefix),
"""CREATE TABLE {0}tags (
        element_id MEDIUMINT UNSIGNED NOT NULL,
        tag_id     SMALLINT  UNSIGNED NOT NULL,
        value_id   MEDIUMINT UNSIGNED NOT NULL,
        INDEX tag_value_idx(tag_id,value_id),
        INDEX element_idx(element_id),
        FOREIGN KEY(element_id) REFERENCES {0}elements(id) ON DELETE CASCADE,
        FOREIGN KEY(tag_id) REFERENCES {0}tagids(id) ON DELETE CASCADE
    ) ENGINE InnoDB, CHARACTER SET 'utf8';
""".format(db.prefix),
"""CREATE TABLE {0}values_varchar (
        id              MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
        tag_id          SMALLINT  UNSIGNED NOT NULL,
        value           VARCHAR({1})       NOT NULL,
        sort_value      VARCHAR({1}),
        hide            BOOLEAN            NOT NULL,
        PRIMARY KEY(id),
        INDEX tag_value_idx(tag_id,value),
        FOREIGN KEY(tag_id) REFERENCES {0}tagids(id) ON DELETE CASCADE
    ) ENGINE InnoDB, CHARACTER SET 'utf8';
""".format(db.prefix,constants.TAG_VARCHAR_LENGTH),
"""CREATE TABLE {0}values_text (
        id     MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
        tag_id SMALLINT  UNSIGNED NOT NULL,
        value  TEXT               NOT NULL,
        PRIMARY KEY(id),
        INDEX tag_value_idx(tag_id,value(10)),
        FOREIGN KEY(tag_id) REFERENCES {0}tagids(id) ON DELETE CASCADE
    ) ENGINE InnoDB, CHARACTER SET 'utf8';
""".format(db.prefix),
"""CREATE TABLE {0}values_date (
        id     MEDIUMINT UNSIGNED NOT NULL AUTO_INCREMENT,
        tag_id SMALLINT  UNSIGNED NOT NULL,
        value  INT       UNSIGNED NOT NULL,
        PRIMARY KEY(id),
        INDEX tag_value_idx(tag_id,value),
        FOREIGN KEY(tag_id) REFERENCES {0}tagids(id) ON DELETE CASCADE
    ) ENGINE InnoDB, CHARACTER SET 'utf8';
""".format(db.prefix),
"""CREATE TABLE {}flag_names (
        id      SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
        name    VARCHAR({})       NOT NULL,
        icon    VARCHAR(255)      DEFAULT NULL,
        PRIMARY KEY(id)
) ENGINE InnoDB, CHARACTER SET 'utf8';
""".format(db.prefix,constants.FLAG_VARCHAR_LENGTH),
"""CREATE TABLE {0}flags (
        element_id      MEDIUMINT UNSIGNED NOT NULL,
        flag_id         SMALLINT UNSIGNED NOT NULL,
        UNIQUE INDEX flag_idx(element_id,flag_id),
        FOREIGN KEY(element_id) REFERENCES {0}elements(id) ON DELETE CASCADE,
        FOREIGN KEY(flag_id) REFERENCES {0}flag_names(id) ON DELETE CASCADE
) ENGINE InnoDB;
""".format(db.prefix),
"""CREATE TABLE {}folders (
        path         VARCHAR(511)    NOT NULL,
        state        ENUM('unknown','nomusic','ok','unsynced')    NOT NULL DEFAULT 'unknown'
) ENGINE InnoDB, CHARACTER SET 'utf8';
""".format(db.prefix),
"""CREATE TABLE {}newfiles (
        path       VARCHAR(511)       NOT NULL,
        hash       VARCHAR(63),
        verified   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX path_idx(path(333)),
        INDEX hash_idx(hash)) ENGINE InnoDB, CHARACTER SET 'utf8' ;
""".format(db.prefix),
)]
