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

"""Unittests for the LevelTreeModel."""

import sys, unittest, os.path
sys.path.insert(0,os.path.normpath(os.path.join(os.getcwd(),os.path.dirname(__file__),'../')))

from omg import application, config, database as db, utils
from testlevel import *


class LevelTestCase(unittest.TestCase):
    """Base test case."""
    def __init__(self,level,model):
        super().__init__()
        self.level = level
        self.model = model
        self.checks = []
        
    def check(self,*args):
        """Check whether the current tree structure as well as the flat playlist is in agreement with
        *wrapperString* (a string in the format for TestLevel.getWrappers).
        
        If *redo* is True, record the test so that it can be performed again when checkUndo is called.
        """
        check = Check(self,*args)
        check.check()
        self.checks.append((check,application.stack.index()))
        
    def checkUndo(self):
        """Undo all changes to the playlist and do the checks again at the right moments."""
        for check,index in reversed(self.checks):
            application.stack.setIndex(index)
            check.check()
        
        application.stack.setIndex(0)
        # Check empty
        Check(self,'').check()


class Check:
    def __init__(self,testCase,wrapperString):
        self.testCase = testCase
        self.wrapperString = wrapperString

    def check(self):
        # Check tree structure
        self.testCase.assertEqual(self.wrapperString,getWrapperString(self.testCase.model.root))
        
        #TODO: Check container structure in level
    

class InsertTestCase(LevelTestCase):
    def runTest(self):
        level = self.level
        model = self.model
        
        model.insertElements(model.root,0,level.ids('A'))
        self.check('A')
        
        model.insertElements(model.root.contents[0],0,level.ids('A1,A2,A3'))
        self.check('A[A1,A2,A3]')
        
        model.insertElements(model.root,1,level.ids('A'))
        self.check('A[A1,A2,A3],A[A1,A2,A3]')
        
        self.checkUndo()
        

        
    
if __name__ == "__main__":
    application.init(exitPoint='noplugins')
    from omg.models import leveltreemodel

    level = TestLevel()
    level.addContainer('A')
    level.addFile('A1')
    level.addFile('A2')
    level.addFile('A3')
    model = leveltreemodel.LevelTreeModel(level)
    
    suite = unittest.TestSuite()
    suite.addTest(InsertTestCase(level,model))
    unittest.TextTestRunner(verbosity=2).run(suite)
    