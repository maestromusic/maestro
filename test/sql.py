# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""Unittests for the sql-package."""

import unittest

from omg import application, config, database as db, utils

data = (
    ("Tobias Ä",24,1.8,True,None),
    ("Julia Ö",22,1.7,False,None),
    ("Karin Ü",21,1.8,True,None),
    ("Frédéric François Chopin",39,1.6,False,utils.FlexiDate(1849,10,17))
)

testTable = "sqltest"


class SqlTestCase(unittest.TestCase):
    def __init__(self,type,driver=None):
        super().__init__()
        self.type, self.driver = type, driver
        
    def setUp(self):
        db.close()
        if self.type == 'sqlite':
            config.options.database.type = 'sqlite'
            config.options.database.sqlite_path = ':memory:'
            print("Checking SQLite...")
        else:
            config.options.database.type = 'mysql'
            config.options.database.mysql_drivers = [self.driver]
            print("Checking MySQL with driver '{}'...".format(self.driver))
        
        try:
            db.connect()
        except db.sql.DBException as e:
            self.skipTest("I cannot connect to the '{}' database using driver '{}'. Did you provide the"
                          " correct information in the testconfig file? SQL error: {}"
                          .format(self.type,self.driver,e.message))

    def tearDown(self):
        db.close()

    def runTest(self):
        # Create the table
        if self.type == 'mysql':
            db.query("""
                CREATE TEMPORARY TABLE {}{} (
                id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                name VARCHAR(30) NOT NULL,
                age INT NOT NULL,
                size DOUBLE NOT NULL,
                male BOOLEAN NOT NULL,
                death INT NULL DEFAULT NULL,
                PRIMARY KEY(id)
                ) ENGINE InnoDB, CHARACTER SET 'utf8';
                """.format(db.prefix,testTable)
            )
        else:
             db.query("""
                CREATE TABLE {}{} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(30) NOT NULL,
                age INT NOT NULL,
                size DOUBLE NOT NULL,
                male BOOLEAN NOT NULL,
                death INT NULL DEFAULT NULL
                )
                """.format(db.prefix,testTable)
            )
        
        # Fill it with data
        result = db.query("INSERT INTO {}{} (name,age,size,male,death) VALUES (?,?,?,?,?)"
                                .format(db.prefix,testTable),*data[0]) # without death column
        self.assertEqual(result.insertId(),1)

        result = db.multiQuery("INSERT INTO {}{} (name,age,size,male,death) VALUES (?,?,?,?,?)"
                                .format(db.prefix,testTable),data[1:])
        # Neither affectedRows nor insertId are equal for different drivers after a multiQuery
        self.assertEqual(db.query("SELECT COUNT(*) FROM {}{}".format(db.prefix,testTable)).getSingle(),4)

        # And retrieve it again
        result = db.query("SELECT id,name,age,size,male,death FROM {}{} ORDER BY id".format(db.prefix,testTable))
        self.assertEqual(len(result),4)
        for i,row in enumerate(result):
            self.assertEqual(i+1,row[0]) # id
            for j in range(5):
                self.assertEqual(data[i][j],row[j+1] if j+1<5 else utils.FlexiDate.fromSql(row[j+1]))

        # Check getSingle* methods
        result = db.query("SELECT id FROM {}{} WHERE age = ?".format(db.prefix,testTable),24)
        self.assertEqual(result.getSingle(),1)

        result = db.query("SELECT id FROM {}{} ORDER BY id".format(db.prefix,testTable))
        for i,v in enumerate(result.getSingleColumn()):
            self.assertEqual(i+1,v)

        result = db.query("SELECT id,age FROM {}{} WHERE id = ?".format(db.prefix,testTable),2)
        row = result.getSingleRow()
        self.assertEqual(row[0],2)
        self.assertEqual(row[1],data[1][1])

        # Start modifying the data
        result = db.query("DELETE FROM {}{} WHERE death IS NOT NULL".format(db.prefix,testTable))
        self.assertEqual(result.affectedRows(),1)

        # Test transactions
        db.transaction()
        for i in range(1,4):
            db.query("UPDATE {}{} SET age=age+1 WHERE id = ?".format(db.prefix,testTable),i)
        db.commit()

        result = db.query("SELECT age FROM {}{} ORDER BY id".format(db.prefix,testTable))
        self.assertListEqual(list(result.getSingleColumn()),[25,23,22])

        db.transaction()
        for i in range(1,4):
            db.query("UPDATE {}{} SET death = ?".format(db.prefix,testTable),utils.FlexiDate(2000))
        db.rollback()

        result = db.query("SELECT death FROM {}{}".format(db.prefix,testTable))
        self.assertListEqual(list(utils.FlexiDate.fromSql(value) for value in result.getSingleColumn()),
                             3*[None])

        # Check exceptions
        self.assertRaises(db.sql.DBException,lambda: db.query("STUPID QUERY"))
        
        result = db.query("SELECT * FROM {}{} WHERE death IS NOT NULL".format(db.prefix,testTable))
        self.assertRaises(db.sql.EmptyResultException,result.getSingle)
        self.assertRaises(db.sql.EmptyResultException,result.getSingleRow)
        

def load_tests(loader, standard_tests, pattern):
    # See http://docs.python.org/py3k/library/unittest.html#load-tests-protocol
    suite = unittest.TestSuite()

    for driver in ["qtsql","pymysql","myconnpy"]:
        suite.addTest(SqlTestCase("mysql",driver))
    suite.addTest(SqlTestCase("sqlite"))
    
    return suite


if __name__ == "__main__":
    print("To run this test use: python setup.py test --test-suite=test.sql")
