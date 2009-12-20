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
            self._db = mysql.MySQL(username,password,database,host,int(port))
        except mysql.error:
            raise DBException(self._db.error())
            
    def query(self,queryString,*args):
        if args:
            queryString = _replaceQueryArgs(queryString,*args)
        return SqlResult(self._db.query(queryString),self._db)
        
    def queryDict(self,queryString,*args):
        if args:
            queryString = _replaceQueryArgs(queryString,*args)
        self._db.use_dict = True
        result = SqlResult(self._db.query(queryString),self._db)
        self._db.use_dict = False
        return result

    def getDate(self,date):
        return date


class SqlResult(AbstractSqlResult):
    def __init__(self,mysqlResult,db):
        self._result = mysqlResult
        self._affectedRows = db.affected_rows
        self._insertId = db.insert_id
    
    def __iter__(self):
        return self._result.__iter__()
        
    def __len__(self):
        return self._result.__len__()
        
    def size(self):
        return self._result.__len__()
    
    def next(self):
        return next(self._result.__iter__())
        
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