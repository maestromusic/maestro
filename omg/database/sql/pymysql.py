# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

import pymysql
from . import DBException, AbstractSql, AbstractSqlResult, EmptyResultException


class Sql(AbstractSql):
    def connect(self,username,password,database,host="localhost",port=3306,**kwargs):
        self._db = pymysql.connect(db=database,user=username,passwd=password,
                                   host=host,port=port,use_unicode=True,charset='utf8')

    def close(self):
        self._db.close()
            
    def query(self,queryString,*args):
        if args:
            queryString = queryString.replace('?','%s')
        cursor = self._db.cursor()
        cursor.execute(queryString,args)
        return SqlResult(cursor)
    
    def multiQuery(self,queryString,argSets):
        if argSets:
            queryString = queryString.replace('?','%s')
        cursor = self._db.cursor()
        cursor.executemany(queryString,argSets)
        return SqlResult(cursor)
        
    def transaction(self):
        self.query('START TRANSACTION')
        
    def commit(self):
        self._db.commit()
        
    def rollback(self):
        self._db.rollback()


class SqlResult(AbstractSqlResult):
    def __init__(self,cursor):
        self._cursor = cursor
    
    def __iter__(self):
        return self._cursor.__iter__()
        
    def __len__(self):
        return self._cursor.rowcount
        
    def size(self):
        return self._cursor.rowcount
    
    def next(self):
        return self._cursor.fetchone()
        
    def executedQuery(self):
        return self._cursor._executed
        
    def affectedRows(self):
        return self._cursor.rowcount
    
    def insertId(self):
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
