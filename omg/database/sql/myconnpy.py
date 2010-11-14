#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
# This module contains a MySQL-driver using the myconnpy module
# (https://launchpad.net/myconnpy).

import mysql.connector
from . import DBException, _replaceQueryArgs, AbstractSql, AbstractSqlResult
import datetime, threading

class Sql(AbstractSql):
    def connect(self,username,password,database,host="localhost",port=3306):
        self._db = mysql.connector.Connect(database=database,user=username,password=password,host=host,port=port,buffered=True)
        self.lock = threading.Lock()

    def query(self,queryString,*args):
        with self.lock:
            if args:
                queryString = _replaceQueryArgs(queryString,*args)
            cursor = self._db.cursor()
            cursor.execute(queryString)
            return SqlResult(cursor)


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
        return self._cursor._executed.decode('utf-8')
        
    def affectedRows(self):
        return self._cursor.rowcount
    
    def insertId(self):
        return self._cursor.lastrowid
    
    def getSingle(self):
        try:
            return self.single
        except AttributeError:
            row = self._cursor.fetchone()
            self.single = row[0] if row is not None else None
            return self.single
        
    def getSingleColumn(self):
        return (row[0] for row in self._cursor.fetchall())
