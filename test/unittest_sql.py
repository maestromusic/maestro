#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""Unittests for the sql-package."""

import sys, unittest, getpass
from omg.database import sql
from omg.utils import FlexiDate

testTable = "tmp_omg_test_table"

data = (
    ("Tobias Ä",24,1.8,True,None),
    ("Julia Ö",22,1.7,False,None),
    ("Karin Ü",21,1.8,True,None),
    ("Frédéric François Chopin",39,1.6,False,FlexiDate(1849,10,17))
)

class SqlTestCase(unittest.TestCase):
    def __init__(self,driver):
        unittest.TestCase.__init__(self)
        self.driver = driver
        
    def setUp(self):
        print("Checking driver '{}'...".format(self.driver))
        self.db = sql.newConnection([self.driver])
        self.db.connect(username,password,database)

    def tearDown(self):
        self.db.close()

    def runTest(self):
        # Create the table
        self.db.query("""
            CREATE TEMPORARY TABLE {} (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT,
            name VARCHAR(30) NOT NULL,
            age INT NOT NULL,
            size DOUBLE NOT NULL,
            male BOOLEAN NOT NULL,
            death INT NULL DEFAULT NULL,
            PRIMARY KEY(id)
            ) ENGINE InnoDB, CHARACTER SET 'utf8';
            """.format(testTable)
        )
        
        # Fill it with data
        result = self.db.query("INSERT INTO {} (name,age,size,male) VALUES (?,?,?,?)"
                                    .format(testTable),*data[0][:-1]) # without death
        self.assertEqual(result.insertId(),1)

        result = self.db.multiQuery("INSERT INTO {} (name,age,size,male,death) VALUES (?,?,?,?,?)".format(testTable),
                                    data[1:])
        self.assertEqual(result.affectedRows(),1) # The result contains only information about the last query
        self.assertEqual(result.insertId(),4)

        # And retrieve it again
        result = self.db.query("SELECT id,name,age,size,male,death FROM {} ORDER BY id".format(testTable))
        self.assertEqual(len(result),4)
        for i,row in enumerate(result):
            self.assertEqual(i+1,row[0]) # id
            for j in range(5):
                self.assertEqual(data[i][j],row[j+1]if j+1<5 else FlexiDate.fromSql(row[j+1]))

        result = self.db.query("SELECT id FROM {} WHERE age = ?".format(testTable),24)
        self.assertEqual(result.getSingle(),1)

        result = self.db.query("SELECT id FROM {} ORDER BY id".format(testTable))
        for i,v in enumerate(result.getSingleColumn()):
            self.assertEqual(i+1,v)

        result = self.db.query("SELECT id,age FROM {} WHERE id = ?".format(testTable),2)
        row = result.getSingleRow()
        self.assertEqual(row[0],2)
        self.assertEqual(row[1],data[1][1])

        # Start modifying the data
        result = self.db.query("DELETE FROM {} WHERE death IS NOT NULL".format(testTable))
        self.assertEqual(result.affectedRows(),1)

        # Test transactions
        self.db.transaction()
        for i in range(1,4):
            self.db.query("UPDATE {} SET age=age+1 WHERE id = ?".format(testTable),i)
        self.db.commit()

        result = self.db.query("SELECT age FROM {} ORDER BY id".format(testTable))
        self.assertListEqual(list(result.getSingleColumn()),[25,23,22])

        self.db.transaction()
        for i in range(1,4):
            self.db.query("UPDATE {} SET death = ?".format(testTable),FlexiDate(2000))
        self.db.rollback()

        result = self.db.query("SELECT death FROM {}".format(testTable))
        self.assertListEqual(list(FlexiDate.fromSql(value) for value in result.getSingleColumn()),3*[None])

        # Check exceptions
        self.assertRaises(sql.DBException,lambda: self.db.query("STUPID QUERY"))
        
        result = self.db.query("SELECT * FROM {} WHERE death IS NOT NULL".format(testTable))
        self.assertRaises(sql.EmptyResultException,result.getSingle)
        self.assertRaises(sql.EmptyResultException,result.getSingleRow)
        self.assertRaises(sql.EmptyResultException,result.getSingleColumn)
        

if __name__ == "__main__":
    username = input("Please enter the SQL username I should use: ")
    password = getpass.getpass("Please enter the SQL password I should use: ")
    database = input("Please enter the SQL database I should use: ")

    suite = unittest.TestSuite()
    for driver in ("qtsql",):
        suite.addTest(SqlTestCase(driver))
        
    unittest.TextTestRunner(verbosity=2).run(suite)
