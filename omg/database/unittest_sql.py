#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""Unittests for the sql-package."""

import sql
import sys
import unittest
import getpass

class SqlTest(unittest.TestCase):
    def setUpTestTable(self,driver):
        self._driver = driver
        self.db = sql.newConnection(driver)
        self.db.connect(username,password,database)
        self.db.query("""
            CREATE TEMPORARY TABLE {0} (
            id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
            text VARCHAR(10) NOT NULL,
            PRIMARY KEY(id)
            )""".format(testTable)
        )
        for i in range(1,11): # Start with 1 or MySQL will complain
            self.db.query("INSERT INTO {0}(id,text) VALUES ({1},'ebbes{1}')".format(testTable,i))
        
    def performTests(self):
        result = self.db.query("SELECT * FROM "+testTable)
        self.assertEqual(result.size(),10)
        self.assertEqual(result.executedQuery(),"SELECT * FROM "+testTable)
        row = result.next()
        self.assertEqual(len(row),2)
        self.assertEqual(row[1],"ebbes1")

        result = self.db.query("SELECT COUNT(*) FROM "+testTable)
        self.assertEqual(result.getSingle(),10)
        self.assertEqual(result.getSingle(),10) # check twice to ensure that getSingle doesn't move the cursor
        
        result = self.db.query("SELECT id FROM "+testTable+" ORDER BY id")
        self.assertListEqual(list(result.getSingleColumn()),list(range(1,11))) # AUTO_INCREMENT-column starts at 1

        result = self.db.query("SELECT id FROM "+testTable+" WHERE text = ?",'ebbes4').getSingle()
        self.assertEqual(result,4)
        
        result = self.db.query("SELECT ?",'abc\'\\def').getSingle()
        self.assertEqual(result,'abc\'\\def')
        
        result = self.db.query("INSERT INTO "+testTable+" VALUES (11,'ebbes11')")
        self.assertEqual(result.insertId(),11)
        self.assertEqual(result.affectedRows(),1)
        
        result = self.db.queryDict("SELECT * FROM "+testTable+" ORDER BY id")
        self.assertEqual(result.size(),11)
        data = result.next()
        self.assertDictEqual({'text':'ebbes1','id':1},data)
        
        result = self.db.queryDict("SELECT * FROM "+testTable)
        data = result.next()
        self.assertTrue('text' in data.keys())
            
        result = self.db.queryDict("SELECT text AS ebbes FROM "+testTable)
        data = result.next()
        self.assertTrue('ebbes' in data.keys())
            
            
    def testQtSqlDriver(self):
        print("Checking QtSQL driver...")
        self.setUpTestTable("qtsql")
        self.performTests()
        
    def testMyPySqlDriver(self):
        print("Checking MyPySql driver...")
        self.setUpTestTable("mypysql")
        self.performTests()

if __name__ == "__main__":
    testTable = "testtable"

    username = input("Please enter the SQL username I should use: ")
    password = getpass.getpass("Please enter the SQL password I should use: ")
    database = input("Please enter the SQL database I should use: ")
    unittest.main()