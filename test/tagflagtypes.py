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

import unittest

from omg import application, database as db
from omg.core import tags


class TagTypeTestCase(unittest.TestCase):
    def setUp(self):
        application.stack.clear()
        self.checks = []
        
    def check(self,values,redo=True):
        result = db.query("SELECT tagtype,title,icon,private,sort FROM {}tagids WHERE tagname='testtag'"
                          .format(db.prefix))
        if values is not None:
            dbValues = [v if not db.isNull(v) else None for v in result.getSingleRow()]
            dbValues[3] = bool(dbValues[3]) # private
            dbValues = tuple(dbValues)
                            
            self.assertEqual(dbValues,values)
            tag = tags.get("testtag")
            self.assertEqual(tag.type.name,values[0])
            self.assertEqual(tag.rawTitle,values[1])
            self.assertEqual(tag.iconPath,values[2])
            self.assertEqual(tag.private,values[3])
            self.assertEqual(tags.tagList.index(tag),values[4])
        else:
            self.assertRaises(db.sql.EmptyResultException,result.getSingleRow)
        
        if redo:
            self.checks.append((values,application.stack.index()))
    
    def checkUndo(self):
        """Undo all changes and do the checks again at the right moments."""
        for values,index in reversed(self.checks):
            application.stack.setIndex(index)
            self.check(values,redo=False)
        
        application.stack.setIndex(0)
        self.check(None,redo=False) # all steps undone
        
    def runTest(self):
        index = len(tags.tagList)
        
        newTag = tags.addTagType("testtag",tags.TYPE_VARCHAR)
        self.check(("varchar",None,None,False,index))
        
        tags.changeTagType(newTag,type=tags.TYPE_DATE)
        self.check(("date",None,None,False,index))
        
        tags.changeTagType(newTag,title="TEST")
        self.check(("date","TEST",None,False,index))
        
        tags.changeTagType(newTag,iconPath="testiconpath")
        self.check(("date","TEST","testiconpath",False,index))
        
        tags.changeTagType(newTag,private=True)
        self.check(("date","TEST","testiconpath",True,index))
        
        tags.removeTagType(newTag)
        self.check(None)
        
        tags.addTagType("testtag",tags.TYPE_TEXT)
        self.check(("text",None,None,False,index))
        
        tags.moveTagType(newTag,0)
        self.check(("text",None,None,False,0))
        
        self.checkUndo()
        
        
if __name__ == "__main__":
    print("To run this test use: python setup.py test --test-suite=test.tagflagtypes")
    