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
from . import DBException

class Sql:    
    def connect(self,username,password,database,host="localhost",port=3306):
        try:
            self._db = mysql.MySQL(username,password,database,host,int(port))
        except mysql.error:
            raise DBException(self._db.error())
            
    def query(self,querystring,*args):
        self._db.use_dict = False
        return SqlResult(self._db.query(querystring,*args))
        
    def queryDict(self,querystring,*args):
        self._db.use_dict = True
        return SqlResult(self._db.query(querystring,*args))
        
class SqlResult:
    def __init__(self,mysqlResult):
        self._result = mysqlResult
    
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
        return self._result.affected_rows()
    
    def insertId(self):
        return self._result.insert_id()
    
    def getSingle(self):
        return self._result.get_single()