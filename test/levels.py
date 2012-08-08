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

"""Unittests for core.levels"""

import unittest

from omg import application, config, database as db, utils

from .testlevel import *


class TestCase(unittest.TestCase):
    """Base test case for playlist test cases."""
    def __init__(self,level,playlist=None):
        super().__init__()
        
        self.level = level
        self.real = level == levels.real
        self.checks = []
        
        self.F1 = level.get(1)
        self.F2 = level.get(2)
        self.F3 = level.get(3)
        self.C1 = level.get(4)
        
    def setUp(self):
        application.stack.clear()
        
    def check(self,checkType,values,redo=True):
        if checkType == 'contents':
            parent, contents = values
            self.assertListEqual([c.id for c in contents],parent.contents.ids)
            if self.real:
                self.assertListEqual([c.id for c in contents],list(db.query(
                            "SELECT element_id FROM {}contents WHERE container_id = ? ORDER BY position"
                            .format(db.prefix),parent.id).getSingleColumn()))
        
        if checkType == 'parents':
            element, parents = values
            self.assertCountEqual([p.id for p in parents],element.parents)
            if self.real:
                self.assertCountEqual([p.id for p in parents],db.query(
                            "SELECT container_id FROM {}contents WHERE element_id=?"
                            .format(db.prefix),element.id).getSingleColumn())
                
        if redo:
            self.checks.append((checkType,values,self.level.stack.index()))
        
    def checkUndo(self):
        """Undo all changes to the playlist and do the checks again at the right moments."""
        for checkType,values,index in reversed(self.checks):
            self.level.stack.setIndex(index)
            self.check(checkType,values,redo=False)
        
        self.level.stack.setIndex(0)
        for element in [self.F1,self.F2,self.F3,self.C1]:
            if element.isContainer():
                self.assertEqual(element.contents.ids,[])
            self.assertEqual(element.parents,[])
            
        if self.real:
            self.assertEqual(0,db.query("SELECT COUNT(*) FROM {}contents".format(db.prefix)).getSingle())
           
    def runTest(self):
        self.level.insertContents(self.C1,0,[self.F1,self.F3])
        self.check('contents',(self.C1,[self.F1,self.F3]))
        self.check('parents',(self.F1,[self.C1]))

        self.level.insertContents(self.C1,1,[self.F2])
        self.check('contents',(self.C1,[self.F1,self.F2,self.F3]))
        
        self.level.removeContents(self.C1,[1,2])
        self.check('contents',(self.C1,[self.F1]))
        self.check('parents',(self.F2,[]))
        
        #container = self.level.merge([self.C1,self.F2,self.F3])
        
        if not self.real:
            self.checkUndo()
        else:
            # Store the current state in a new level
            level = levels.Level('TEST',parent=levels.real)
            level.getFromIds([1,2,3,4])
            
            self.checkUndo()
            
            self.checks = []
            
            # Restore the state to check whether commit works
            level.commit()
            self.check('contents',(self.C1,[self.F1]))
            self.check('parents',(self.F1,[self.C1]))
            self.check('parents',(self.F2,[]))
            self.check('parents',(self.F3,[]))
            
            self.checkUndo()

        
def load_tests(loader, standard_tests, pattern):
    # See http://docs.python.org/py3k/library/unittest.html#load-tests-protocol
    suite = unittest.TestSuite()
    
    db.transaction()
    elementCount = 4
    db.multiQuery('INSERT INTO {}elements (id,file,toplevel,elements,major) VALUES (?,?,?,?,0)'
                  .format(db.prefix),
                  [(1,1,0,0,),(2,1,0,0,),(3,1,0,0,),
                   (4,0,1,3,)
                  ])
    # Create fake files which have their id as path and hash
    db.query("""INSERT INTO {0}files (element_id,path,hash,length)
                            SELECT id,id,id,0 FROM {0}elements WHERE file=1"""
             .format(db.prefix))
                  
    #db.multiQuery('INSERT INTO {}contents (container_id,position,element_id) VALUES(?,?,?)'
    #              .format(db.prefix),
    #              [(4,1,1),(4,2,2),(4,3,3)])
    db.multiQuery('INSERT INTO {}values_varchar (id,tag_id,value,sort_value,hide) VALUES (?,?,?,NULL,0)'
                  .format(db.prefix),
                  [(1,tags.TITLE.id,'F1'),(2,tags.TITLE.id,'F2'),(3,tags.TITLE.id,'F3'),
                   (4,tags.TITLE.id,'C1'),])
    db.multiQuery('INSERT INTO {}tags (element_id,tag_id,value_id) VALUES (?,?,?)'
                  .format(db.prefix),
                  # each title in values_varchar has the same id as the corresponding element
                  [(i,tags.TITLE.id,i) for i in range(1,elementCount+1)])
    db.commit()

    levels.editor.getFromIds(list(range(1,elementCount+1))) # load all elements into editor level
    
    suite.addTest(TestCase(levels.editor))
    suite.addTest(TestCase(levels.real))
    return suite
    
if __name__ == "__main__":
    print("To run this test use: python setup.py test --test-suite=test.levels")
    