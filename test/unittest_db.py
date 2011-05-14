#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation

import sys, unittest
from omg import application, database as db, tags


class ElementsContentsTestCase(unittest.TestCase):
    def setUp(self):
        #     1
        #    / \
        #   2   3-----
        #  / \ / \   |
        # 4   5   6  |
        #        / \ /
        #       7   8
        db.query("""
            INSERT INTO {}elements(id,file,toplevel,elements) VALUES
                (1,0,1,2),(2,0,0,2),(3,0,0,3),(4,1,0,0),(5,1,0,0),(6,0,0,2),(7,1,0,0),(8,1,0,0)
                """.format(db.prefix))
        db.query("""
            INSERT INTO {}contents(container_id,position,element_id) VALUES
                (1,1,2),(1,2,3),(2,1,4),(2,2,5),(3,1,5),(3,2,6),(3,3,8),(6,1,7),(6,2,8)
                """.format(db.prefix))

    def tearDown(self):
        db.query("TRUNCATE TABLE {}elements".format(db.prefix))
        db.query("TRUNCATE TABLE {}contents".format(db.prefix))

    def runTest(self):
        self.assertSetEqual(db.contents(1,False),{2,3})
        self.assertSetEqual(db.contents([2,3],False),{4,5,6,8})
        self.assertSetEqual(db.contents(1,True),set(range(2,9)))
        self.assertSetEqual(db.parents(5,False),{2,3})
        self.assertSetEqual(db.parents(5,True),{1,2,3})
        self.assertSetEqual(db.parents(8,True),{1,3,6})
        self.assertEqual(db.position(1,3),2)
        self.assertRaises(ValueError,db.position,1,8)






if __name__ == "__main__":
    application.init(initTags=False,testDB=True)
    db.resetDatabase()
    
    suite = unittest.TestSuite()
    suite.addTest(ElementsContentsTestCase())
        
    unittest.TextTestRunner(verbosity=2).run(suite)
