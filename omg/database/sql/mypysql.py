#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
# This module contains a MySQL-driver using the mysql-python module
# (http://sourceforge.net/projects/mypysql/).
#
import mysql
from . import DBException, _replaceQueryArgs, AbstractSql, AbstractSqlResult
import logging

class Sql(AbstractSql):    
    def connect(self,username,password,database,host="localhost",port=3306):
        try:
            self._db = mysql.connect(user=username,passwd=password,db=database,host=host,port=int(port))
        except mysql.DatabaseError as e:
            raise DBException(str(e))
            
    def query(self,queryString,*args):
        if args:
            queryString = _replaceQueryArgs(queryString,*args)
        cursor = self._db.cursor()
        cursor.execute(queryString)
        return SqlResult(cursor)
        
    def queryDict(self,queryString,*args):
        raise Exception("queryDict is not supported")
        if args:
            queryString = _replaceQueryArgs(queryString,*args)
        self._db.use_dict = True
        result = SqlResult(self._db.execute(queryString),self._db)
        self._db.use_dict = False
        return result


class SqlResult(AbstractSqlResult):
    def __init__(self,cursor):
        self._cursor = cursor
    
    def __iter__(self):
        return self._cursor.__iter__()
        
    def __len__(self):
        return self._cursor.__len__()
        
    def size(self):
        return self._result.__len__()
    
    def next(self):
        return self._cursor.next()
        
    def executedQuery(self):
        return self._result.__str__()
        
    def affectedRows(self):
        return self._affectedRows
    
    def insertId(self):
        return self._insertId
    
    def getSingle(self):
        return self._result.get_single()
        
    def getSingleColumn(self):
        return (row[0] for row in self)
