#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
# Unittests for the sql-module.
#
import sql
import sys
import unittest
import getpass

testTable = "testtable"

username = input("Please enter the SQL username I should use: ")
password = getpass.getpass("Please enter the SQL password I should use: ")
database = input("Please enter the SQL database I should use: ")


class SqlTest(unittest.TestCase):
    
    def setUpTestTable(self,driver):
        self.db = sql.newDatabase(driver)
        self.db.connect(username,password,database)
        self.db.query("""
            CREATE TEMPORARY TABLE {0} (
            id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
            text VARCHAR(10) NOT NULL,
            PRIMARY KEY(id)
            )""".format(testTable)
        )
        for i in range(10):
            self.db.query("INSERT INTO {0}(text) VALUES ('ebbes{1}')".format(testTable,i))
    
    def performTests(self):
        result = self.db.query("SELECT * FROM "+testTable)
        self.assertEqual(result.size(),10)
        self.assertEqual(result.lastQuery(),"SELECT * FROM "+testTable)
        row = result.next()
        self.assertEqual(len(row),2)
        self.assertEqual(row[1],"ebbes0")

        result = self.db.queryDict("SELECT * FROM "+testTable)
        self.assertEqual(result.size(),10)
        data = result.next()
        self.assertDictEqual({'text':'ebbes0','id':1},data)
        
        result = self.db.query("SELECT COUNT(*) FROM "+testTable)
        self.assertEqual(result.getSingle(),10)
        self.assertEqual(result.getSingle(),10) # check twice to ensure that getSingle doesn't move the cursor

        result = self.db.queryDict("SELECT text AS ebbes FROM "+testTable)
        data = result.next()
        self.assertTrue('ebbes' in data)
        
    def testQtSqlDriver(self):
        self.setUpTestTable("qtsql")
        self.performTests()
        
    def testMyPySqlDriver(self):
        self.setUpTestTable("mypysql")
        self.performTests()
        
unittest.main()