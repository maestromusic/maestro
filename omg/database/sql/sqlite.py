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

import sqlite3, datetime, threading

from . import DBException, AbstractSql, AbstractSqlResult, EmptyResultException
from .. import prefix
from ... import utils, logging, strutils

sqlite3.register_adapter(utils.FlexiDate, utils.FlexiDate.toSql)

logger = logging.getLogger(__name__)
transactionLock = threading.RLock()


class Sql(AbstractSql):
    def connect(self,path, isolation_level=None):
        # There doesn't seem to be a real documentation of the isolation_level parameter. 
        # But I like the conclusion of this discussion:
        # http://mail.python.org/pipermail/python-list/2010-March/1239395.html
        self._db = sqlite3.connect(path, isolation_level=isolation_level)
        # Foreign keys must be enabled in each connection
        self._db.execute("PRAGMA foreign_keys = ON")
        
        self._db.create_function('REMOVE_DIACRITICS', 1, strutils.removeDiacritics)

    def close(self):
        self._db.close()
            
    def query(self,queryString,*args):
        queryString = queryString.format(p=prefix)
        with transactionLock:
            while True:
                try:
                    return SqlResult(self._db.execute(queryString,args),False)
                except Exception as e:
                    if isinstance(e,sqlite3.OperationalError) and str(e) == 'database is locked':
                        logger.warning("Database is locked (I will retry). Query: {}".format(queryString))
                        import time
                        time.sleep(0.1)
                        continue
                    raise DBException(str(e),query=queryString,args=args)
    
    def multiQuery(self,queryString,argSets):
        queryString = queryString.format(p=prefix)
        with transactionLock:
            while True:
                try:
                    if self._transactionDepth == 0:
                        self.query('BEGIN TRANSACTION')
                    result = SqlResult(self._db.executemany(queryString,argSets),True)
                    if self._transactionDepth == 0:
                        self._db.commit()
                    return result
                except Exception as e:
                    if isinstance(e,sqlite3.OperationalError) and str(e) == 'database is locked':
                        logger.warning("Database is locked (I will retry). Multiquery: {}".format(queryString))
                        import time
                        time.sleep(0.1)
                        continue
                    raise DBException(str(e),query=queryString,args=argSets)
        
    def transaction(self):
        if super().transaction():
            transactionLock.acquire()
            self.query('BEGIN TRANSACTION')
            return True
        else: return False
        
    def commit(self):
        if super().commit():
            self._db.commit()
            transactionLock.release()
            return True
        else: return False
        
    def rollback(self):
        super().rollback()
        self._db.rollback()
        transactionLock.release()
        
    def getDate(self,value):
        if value.endswith('+00:00'):
            value = value[:-6]
        return datetime.datetime.strptime(value,"%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc)
            

class SqlResult(AbstractSqlResult):
    def __init__(self,cursor,multi):
        self._cursor = cursor
        self._multi = multi
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
        if self._multi:
            raise DBException("You must not use 'affectedRows' after a multiquery.")
        return self._cursor.rowcount
    
    def insertId(self):
        if self._multi:
            raise DBException("You must not use 'insertId' after a multiquery.")
        return self._cursor.lastrowid
    
    def getSingle(self):
        if len(self._rows) == 0:
            raise EmptyResultException()
        else: return self._rows[0][0]
        
    def getSingleColumn(self):
        return (row[0] for row in self._rows)
