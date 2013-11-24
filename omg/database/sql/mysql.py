# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

"""Database connector using the official MySQL/Python Connector
http://dev.mysql.com/doc/relnotes/connector-python/en/
"""

import mysql.connector
from . import AbstractSql, AbstractSqlResult, DBException, EmptyResultException
from .. import prefix
from ... import utils


class Sql(AbstractSql):
    def connect(self, username, password, database, host="localhost", port=3306, **kwargs):
        try:
            self._db = mysql.connector.connect(database=database, user=username, password=password,
                                               host=host, port=port,
                                               buffered=True, autocommit=True)
        except mysql.connector.errors.Error as e:
            raise DBException("DB-connection failed: {}".format(str(e)))

    def close(self):
        self._db.close()
                    
    def query(self, queryString, *args):
        queryString = queryString.format(p=prefix)
        if len(args) > 0:
            queryString = queryString.replace('?','%s')
            args = [a.toSql() if isinstance(a, utils.FlexiDate) else a for a in args]
        try:
            cursor = self._db.cursor()
            cursor.execute(queryString, args)
        except mysql.connector.errors.Error as e:
            raise DBException(str(e), queryString, args)
        return SqlResult(cursor, False)
    
    def multiQuery(self, queryString, argSets):
        if not isinstance(argSets, (list,tuple)):
            # Usually this means that argSets is some other iterable object,
            # but mysql connector will complain.
            argSets = list(argSets)
        queryString = queryString.format(p=prefix).replace('?','%s')
        argSets = [[a.toSql() if isinstance(a, utils.FlexiDate) else a for a in argSet]
                   for argSet in argSets]
        try:
            cursor = self._db.cursor()
            cursor.executemany(queryString, argSets)
        except mysql.connector.errors.Error as e:
            raise DBException(str(e), queryString, argSets)
        return SqlResult(cursor,True)
        
    def transaction(self):
        if super().transaction():
            self.query('START TRANSACTION')
            return True
        else: return False
        
    def commit(self):
        if super().commit():
            self._db.commit()
            return True
        else: return False
        
    def rollback(self):
        super().rollback()
        self._db.rollback()


class SqlResult(AbstractSqlResult):
    def __init__(self,cursor,multi):
        self._cursor = cursor
        self._multi = multi
    
    def __iter__(self):
        return self._cursor.__iter__()
        
    def __len__(self):
        return self._cursor.rowcount
        
    def size(self):
        return self._cursor.rowcount
    
    def next(self):
        return self._cursor.fetchone()
        
    def executedQuery(self):
        return self._cursor._executed.decode('utf-8')
        
    def affectedRows(self):
        if self._multi:
            raise DBException("You must not use 'affectedRows' after a multiquery.")
        return self._cursor.rowcount
    
    def insertId(self):
        if self._multi:
            raise DBException("You must not use 'insertId' after a multiquery.")
        return self._cursor.lastrowid
    
    def getSingle(self):
        try:
            return self.single
        except AttributeError:
            row = self._cursor.fetchone()
            if row is None:
                raise EmptyResultException()
            self.single = row[0]
            return self.single
        
    def getSingleColumn(self):
        return (row[0] for row in self._cursor.fetchall())
