#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtSql
from . import DBException

class Sql:
    def __init__(self):
        self._db = QtSql.QSqlDatabase("QMYSQL")

    def connect(self,username,password,database,host="localhost",port=3306):
        self._db.setHostName(host)
        self._db.setPort(port)
        self._db.setDatabaseName(database)
        ok = self._db.open(username,password)
        if not ok:
            raise DBException("DB-connection failed: {0}".format(self._db.lastError().databaseText()))

    def query(self,queryString,*args):
        return self._query(queryString,False,*args)
    
    def queryDict(self,queryString,*args):
        return self._query(queryString,True,*args)
        
    def _query(self,queryString,useDict,*args):
        query = QtSql.QSqlQuery(self._db)
        query.prepare(queryString)
        for arg in args:
            query.addBindValue(arg)
        ok = query.exec_()
        if not ok:
            raise DBException("Query failed: {0}".format(self._db.lastError().databaseText()))
        return SqlResult(query,useDict)

    
class SqlResult:
    def __init__(self,qSqlResult,useDict):
        self._result = qSqlResult
        self._useDict = useDict
        
    def __iter__(self):
        return SqlResultIterator(self._result,self._useDict)
    
    def __len__(self):
        return self._result.size()

    def size(self):
        return self._result.size()
    
    def next(self):
        return next(self.__iter__())
        
    def executedQuery(self):
        return str(self._result.executedQuery()) # QSqlQuery.executedQuery returns a QString
    
    def affectedRows(self):
        return self._result.numRowsAffected()
        
    def insertId(self):
        return self._result.lastInsertId()
        
    def getSingle(self):
        if not self._result.isValid():
            self._result.next()
        return self._result.value(0)


class SqlResultIterator:
    def __init__(self,qSqlResult,useDict):
        self._result = qSqlResult
        if useDict:
            self._convertMethod = self._recordToDict
        else: self._convertMethod = self._recordToTuple
        
    def __iter__(self):
        return self
        
    def __next__(self):
        if not self._result.next():
            raise StopIteration
        else: return self._convertMethod(self._result.record())
        
    def _recordToTuple(self,record):
        return tuple([record.value(i) for i in range(record.count())])
    
    def _recordToDict(self,record):
        return {record.fieldName(i): record.value(i) for i in range(record.count())}