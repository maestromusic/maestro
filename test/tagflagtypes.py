# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

from omg import application, database as db
from omg.core import flags, tags
from . import testcase


class TagTypeTestCase(testcase.UndoableTestCase):
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
        self.check(None,redo=False) # all steps undone
        
        
class FlagTypeTestCase(testcase.UndoableTestCase):
    def check(self,name,iconPath,redo=True):
        result = db.query("SELECT name,icon FROM {}flag_names WHERE name='testflag' OR name='testflag2'"
                .format(db.prefix))
        if name is None: # no flag should exist
            self.assertRaises(db.sql.EmptyResultException,result.getSingle)
        else:
            for dbName,dbIconPath in result:
                if db.isNull(dbIconPath):
                    dbIconPath = None
                flag = flags.get(name)
                self.assertEqual(flag.name,name)
                self.assertEqual(dbName,name)
                self.assertEqual(flag.iconPath,iconPath)
                self.assertEqual(dbIconPath,iconPath)
                break;
            else: self.fail() # two flags found by the db query
        
    def runTest(self):
        flagType = flags.addFlagType('testflag')
        self.check('testflag',None)
        
        flags.changeFlagType(flagType,iconPath='testpath')
        self.check('testflag','testpath')
        
        flags.changeFlagType(flagType,name='testflag2')
        self.check('testflag2','testpath')
        
        flags.changeFlagType(flagType,iconPath=None)
        self.check('testflag2',None)
        
        flags.deleteFlagType(flagType)
        self.check(None,None)
        
        flags.addFlagType('testflag',iconPath='testpath2')
        self.check('testflag','testpath2')
        
        self.checkUndo()
        self.check(None,None,redo=False) # all steps undone
        
        
if __name__ == "__main__":
    print("To run this test use: python setup.py test --test-suite=test.tagflagtypes")
    