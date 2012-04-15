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

import sqlite3, datetime
from . import DBException, AbstractSql, AbstractSqlResult, EmptyResultException


class Sql(AbstractSql):
    def connect(self,path,**kwargs):
        # There doesn't seem to be a real documentation of the isolation_level parameter. 
        # But I like the conclusion of this discussion:
        # http://mail.python.org/pipermail/python-list/2010-March/1239395.html
        isolevel = None if "mode" not in kwargs else kwargs["mode"]
        self._db = sqlite3.connect(path,isolation_level = isolevel)
        # Foreign keys must be enabled in each connection
        self._db.execute("PRAGMA foreign_keys = ON")

    def close(self):
        self._db.close()
            
    def query(self,queryString,*args):
        try:
            return SqlResult(self._db.execute(queryString,args))
        except Exception as e:
            raise DBException(str(e),query=queryString,args=args)
    
    def multiQuery(self,queryString,argSets):
        try:
            return SqlResult(self._db.executemany(queryString,argSets))
        except Exception as e:
            raise DBException(str(e),query=queryString,args=argSets)
        
    def transaction(self):
        self.query('BEGIN TRANSACTION')
        
    def commit(self):
        self._db.commit()
        
    def rollback(self):
        self._db.rollback()
        
    def getDate(self,value):
        return datetime.datetime.strptime(value,"%Y-%m-%d %H:%M:%S").replace(tzinfo = datetime.timezone.utc)


class SqlResult(AbstractSqlResult):
    def __init__(self,cursor):
        self._cursor = cursor
        if cursor.rowcount == -1: # chances are that this is a SELECT query
            self._rows = cursor.fetchall()
            self._index = -1
        else: self._rows = None 
    
    def __iter__(self):
        return self._rows.__iter__()
        
    def __len__(self):
        return len(self._rows)
        
    def size(self):
        return len(self._rows)
    
    def next(self):
        self._index += 1
        return self._rows[self._index]
        
    def executedQuery(self):
        return self._cursor._executed.decode('utf-8')
        
    def affectedRows(self):
        return self._cursor.rowcount
    
    def insertId(self):
        if self._cursor.lastrowid is None:
            # lastrowid is None after multiqueries
            return self._cursor.execute("SELECT last_insert_rowid()").fetchone()[0]
        else:
            return self._cursor.lastrowid
    
    def getSingle(self):
        if len(self._rows) == 0:
            raise EmptyResultException()
        else: return self._rows[0][0]
        
    def getSingleColumn(self):
        return (row[0] for row in self._rows)
