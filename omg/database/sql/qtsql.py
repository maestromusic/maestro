#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""Database driver using QtSql. Have a look at database.sql.AbstractSQL for docstrings."""

from PyQt4 import QtSql
import datetime, threading

from . import DBException, EmptyResultException, AbstractSql, AbstractSqlResult
from omg import utils,strutils


class Sql(AbstractSql):
    def __init__(self):
        self._db = QtSql.QSqlDatabase("QMYSQL")
                
    def connect(self,username,password,database,host="localhost",port=3306):
        self._db.setHostName(host)
        self._db.setPort(int(port))
        self._db.setDatabaseName(database)
        ok = self._db.open(username,password)
        if not ok:
            raise DBException("DB-connection failed: {}".format(self._db.lastError().databaseText()))
        self.lock = threading.Lock()

    def close(self):
        self._db.close()
        del self._db
        
    def query(self,queryString,*args):
        with self.lock:
            query = QtSql.QSqlQuery(self._db)
            query.setForwardOnly(True) # improves performance

            # Prepare
            if not query.prepare(queryString):
                if self._db.lastError() is not None:
                    raise DBException("Query failed: {}".format(self._db.lastError().text()),queryString,args)
                else: raise DBException("Query failed",queryString,args)

            # Bind
            for i,arg in enumerate(args):
                if isinstance(arg,utils.FlexiDate):
                    arg = arg.toSql()
                query.bindValue(i,arg)

            # Execute
            if query.exec_():
                return SqlResult(query)
            else:
                if self._db.lastError() is not None:
                    raise DBException("Query failed: {}".format(self._db.lastError().text()),queryString,args)
                else: raise DBException("Query failed",queryString,args)

    def multiQuery(self,queryString,argSets):
        with self.lock:
            if not isinstance(argSets,list):
                argSets = list(argSets)
            if len(argSets) == 0:
                raise ValueError("You must give at least one set of arguments.")
            
            # Prepare
            query = QtSql.QSqlQuery(self._db)
            query.setForwardOnly(True) # improves performance
            query.prepare(queryString)

            # Bind
            for i in range(len(argSets[0])):
                values = [argSet[i] if not isinstance(argSet[i],utils.FlexiDate)
                                       else argSet[i].toSql()
                          for argSet in argSets]
                query.addBindValue(values)

            # Execute
            if query.execBatch():
                return SqlResult(query)
            else:
                if self._db.lastError() is not None:
                    raise DBException("Query failed: {}".format(self._db.lastError().text()),queryString,argSets)
                else: raise DBException("Query failed",queryString,argSets)

    def transaction(self):
        with self.lock:
            if not self._db.transaction():
                raise DBException("Could not start a transaction.")

    def commit(self):
        with self.lock:
            if not self._db.commit():
                if self._db.lastError() is not None:
                    raise DBException("Commit failed: {}".format(self._db.lastError().text()))
                else: raise DBException("Commit failed.")
                    
    def rollback(self):
        with self.lock:
            if not self._db.rollback():
                if self._db.lastError() is not None:
                    raise DBException("Rollback failed: {}".format(self._db.lastError().text()))
                else: raise DBException("Rollback failed.")


class SqlResult(AbstractSqlResult):
    def __init__(self,query):
        self._result = query # No need to use QSqlResult objects
        # Store these values as the methods will return -1 after the query has become inactive
        self._affectedRows = self._result.numRowsAffected() 
        self._insertId = self._result.lastInsertId()
        
    def __iter__(self):
        return SqlResultIterator(self._result)
    
    def __len__(self):
        return self._result.size()

    def next(self):
        return self.__iter__().__next__()

    def size(self):
        return self._result.size()
        
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
            raise EmptyResultException()
        return self._result.value(0)

    def getSingleColumn(self):
        if self.size() == 0:
            raise EmptyResultException()
        else: return (row[0] for row in self)


class SqlResultIterator:
    """Iterator-object which is used to iterate over an SqlResult."""
    def __init__(self,qSqlResult):
        self._result = qSqlResult
        
    def __iter__(self):
        return self
        
    def __next__(self):
        if self._result.next():
            record = self._result.record()
            return tuple(record.value(i) for i in range(record.count()))
        else: raise StopIteration
