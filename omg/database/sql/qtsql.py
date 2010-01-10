#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtSql
from . import DBException, _replaceQueryArgs, AbstractSql, AbstractSqlResult
import datetime

class Sql(AbstractSql):
    def __init__(self):
        self._db = QtSql.QSqlDatabase("QMYSQL")

    def connect(self,username,password,database,host="localhost",port=3306):
        self._db.setHostName(host)
        self._db.setPort(int(port))
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
        
        if args:
            queryString = _replaceQueryArgs(queryString,*args)
            
        if not query.exec_(queryString):
            if self._db.lastError() is not None:
                message = "Query failed: {0} | Query: {1}".format(self._db.lastError().text(),queryString)
            else: message = "Query failed {0}".format(queryString)
            raise DBException(message)
        return SqlResult(query,useDict)
    
    def getDate(self,qdate):
        try:
            return datetime.date(qdate.year(),qdate.month(),qdate.day())
        except ValueError:
            return datetime.date(1988,12,2) #TODO: of course this is stupid...but at least on my computer QtSql delivers always the same wrong and invalid date and I cannot create a datetime.date from it.
        
        
class SqlResult(AbstractSqlResult):
    def __init__(self,qSqlResult,useDict):
        self._result = qSqlResult
        self._useDict = useDict
        self._affectedRows = self._result.numRowsAffected()
        self._insertId = self._result.lastInsertId()
        
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
        return self._affectedRows
        
    def insertId(self):
        return self._insertId
        
    def getSingle(self):
        if not self._result.isValid(): # usually the cursor is positioned before the first entry
            self._result.next()
        if not self._result.isValid():
            return None;
        return self._result.value(0)
    
    def getSingleColumn(self):
        return (row[0] for row in self)


class SqlResultIterator:
    """Iterator-object which is used to iterate over an SqlResult."""
    def __init__(self,qSqlResult,useDict):
        self._result = qSqlResult
        self._convertMethod = self._recordToDict if useDict else self._recordToTuple
        
    def __iter__(self):
        return self
        
    def __next__(self):
        if self._result.next():
            return self._convertMethod(self._result.record())
        else: raise StopIteration
        
    def _recordToTuple(self,record):
        """Convert a QSqlRecord to a tuple."""
        return tuple([record.value(i) for i in range(record.count())])
    
    def _recordToDict(self,record):
        """Convert a QSqlRecord to a dictionary which maps columnnames (or aliases) to the corresponding values."""
        return {record.fieldName(i): record.value(i) for i in range(record.count())}