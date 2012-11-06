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
from omg.core import tags, levels, elements
from omg.filebackends import BackendFile, BackendURL, urlTypes
from . import testcase
from .testlevel import *

class TestFile(BackendFile):
    @staticmethod
    def tryLoad(url):
        assert url.scheme == 'test'
        return TestFile(url)
    
    def readTags(self):
        self.tags = tags.Storage()
        artist,title = self.url.parsedUrl.path[1:].split(' - ') # skip leading /
        self.tags.add(tags.TITLE, title)
        self.tags.add(tags.get('artist'), artist)
    
    def saveTags(self):
        # writing tags to filesystem is not checked by this unittest
        return []
    
    length = 180

class TestUrl(BackendURL):
    CAN_RENAME = False
    CAN_DELETE = False
    IMPLEMENTATIONS = [ TestFile ]
    
    def __init__(self, urlString):
        if "://" not in urlString:
            urlString = "test:///" + utils.relPath(urlString)
        super().__init__(urlString)

urlTypes["test"] = TestUrl
 

class LevelTestCase(testcase.UndoableTestCase):
    """Base test case for level related test cases."""
    def __init__(self,level):
        super().__init__()
        
        self.level = level
        self.real = level == levels.real
    
    def setUp(self):
        super().setUp()
        self.level.elements = {}
        if self.real:
            db.query("DELETE FROM {}elements".format(db.prefix))
            from omg.core import reallevel
            reallevel._dbIds = set()


class CreationTestCase(LevelTestCase):
    def runTest(self):
        if not self.real:
            self.assertEqual(self.level.elements, {}) # this is important on undo
        self.f1 = self.level.collect(TestUrl('test://band 1 - song'))
        # due to the fixed url->id mapping, these id is the same on real and editor
        self.assertEqual(self.f1.id, 1)
        self.assertIn(self.f1.id, self.level)
        self.f2 = self.level.collect(TestUrl('test://band 2 - a song'))
        self.f3 = self.level.collect(TestUrl('test://band 3 - another song'))
        self.f4 = self.level.collect(TestUrl('test://band 4 - no song'))
        containerTags = tags.Storage({tags.TITLE: ['Weird album']})
        if self.real: # On real level createContainer does not work until we added the contents to the db
            self.assertEqual(0, db.query("SELECT COUNT(*) FROM {}elements".format(db.prefix)).getSingle())
            from omg.core import reallevel
            self.assertEqual(reallevel._dbIds,set())
            self.level.addToDb([self.f1, self.f2, self.f3, self.f4])
            self.assertEqual(4, db.query("SELECT COUNT(*) FROM {}elements".format(db.prefix)).getSingle())
            self.assertEqual(reallevel._dbIds,set([1,2,3,4]))
        
        # note that this id will be different when this test is run for editor and real level
        predictedId = db._nextId
        self.assertNotIn(predictedId, self.level) 
        self.assertEqual(self.f1.parents, [])
        self.c = self.level.createContainer(tags=containerTags, contents=[self.f1, self.f2, self.f3])
        self.assertEqual(self.c.id, predictedId)
        self.assertIn(predictedId, self.level)
        self.assertEqual(self.c.contents,
                         elements.ContentList.fromList([self.f1.id, self.f2.id, self.f3.id]))
        self.assertEqual(self.f1.parents, [self.c.id])
        
        self.checkUndo()
        self.checkRedo()
        
        
class ContentsTestCase(LevelTestCase):
    def setUp(self):
        super().setUp()
        self.f1 = self.level.collect(TestUrl('test://band 1 - song'))
        self.f2 = self.level.collect(TestUrl('test://band 2 - a song'))
        self.f3 = self.level.collect(TestUrl('test://band 3 - another song'))
        self.f4 = self.level.collect(TestUrl('test://band 4 - no song'))
        self.fs = [self.f1, self.f2, self.f3, self.f4]
        containerTags = tags.Storage({tags.TITLE: ['Weird album']})
        if self.real:
            # On real level createContainer does not work until we added the contents to the db
            self.level.addToDb(self.fs)
        self.c = self.level.createContainer(tags=containerTags, contents=[])
        
    def runTest(self):
        self.assertEqual(self.c.contents, elements.ContentList())
        self.assertEqual(self.f1.parents, [])
        
        # setContents
        self.level.setContents(self.c, elements.ContentList.fromList(self.fs))
        self.assertEqual(self.c.contents, elements.ContentList.fromList(self.fs))
        self.assertEqual(self.f1.parents, [self.c.id])
        
        # setContents empty
        self.level.setContents(self.c, [])
        self.assertEqual(self.c.contents, elements.ContentList())
        self.assertEqual(self.f1.parents, [])
        
        # insertContents
        pairs = ((1, self.f1), (4, self.f2), (9, self.f3))
        self.level.insertContents(self.c, pairs)
        self.assertEqual(self.c.contents, elements.ContentList.fromPairs(pairs))
        self.assertEqual(self.f1.parents, [self.c.id])
        
        #TODO: Bug: This breaks monotonicity of ContentList
        #self.level.shiftPositions(self.c, [1,4], 9)
        #self.assertEqual(self.c.contents,
        #                 elements.ContentList.fromPairs([(9, self.f3), (10,self.f1), (13, self.f2)]))
        # If this is fixed, the next two changes have to be adapted
        self.level.removeContents(self.c, [4,9])
        self.assertEqual(self.c.contents,
                         elements.ContentList.fromPairs([(1,self.f1)]))
        self.assertEqual(self.f2.parents, [])
        
        # shiftPositions
        self.level.shiftPositions(self.c, [1], 9)
        self.assertEqual(self.c.contents, elements.ContentList.fromPairs([(10, self.f1)]))
        
        # insertContentsAuto
        contents = [self.f2, self.f4]
        self.level.insertContentsAuto(self.c, 1, contents)
        self.assertEqual(self.c.contents,
                         elements.ContentList.fromPairs([(10,self.f1), (11, self.f2), (12, self.f4)]))
        self.assertEqual(self.f4.parents, [self.c.id])
        
        self.level.insertContentsAuto(self.c, 2, [self.f3])
        self.assertEqual(self.c.contents,
                elements.ContentList.fromPairs([(10,self.f1), (11, self.f2), (12, self.f3), (13, self.f4)]))
        
        # removeContentsAuto
        self.level.removeContentsAuto(self.c, positions=[11])
        self.assertEqual(self.c.contents,
                         elements.ContentList.fromPairs([(10,self.f1), (11, self.f3), (12, self.f4)]))
        self.assertEqual(self.f2.parents, [])
        
        self.level.removeContentsAuto(self.c, indexes=[1])
        self.assertEqual(self.c.contents,
                         elements.ContentList.fromPairs([(10,self.f1), (11, self.f4)]))
        self.assertEqual(self.f3.parents, [])
        
        self.checkUndo()
        self.checkRedo()
        
        
class CommitTestCase(LevelTestCase):
    def setUp(self):
        super().setUp()
        self.subLevel = levels.Level('TEST', self.level)
        self.f1 = self.subLevel.collect(TestUrl('test://band 1 - song'))
        self.f2 = self.subLevel.collect(TestUrl('test://band 2 - a song'))
        self.f3 = self.subLevel.collect(TestUrl('test://band 3 - another song'))
        self.f4 = self.subLevel.collect(TestUrl('test://band 4 - no song'))
        self.fs = [self.f1, self.f2, self.f3, self.f4]
        self.containerTags = tags.Storage({tags.TITLE: ['Weird album']})
        self.contentList = elements.ContentList.fromPairs([(10,self.f1), (12,self.f2)])
        self.c = self.subLevel.createContainer(tags=self.containerTags, contents=self.contentList)
        
    def runTest(self):
        if self.real:
            self.assertEqual(0, db.query("SELECT COUNT(*) FROM {}elements".format(db.prefix)).getSingle())
            self.assertEqual(set(self.level.elements.keys()), set([el.id for el in self.fs]))
        else:
            self.assertEqual(self.level.elements, {})
        print("Start commit")
        self.subLevel.commit()
        if self.real:
            self.assertEqual(5, db.query("SELECT COUNT(*) FROM {}elements".format(db.prefix)).getSingle())
        self.assertEqual(set(self.level.elements.keys()),
                         set([element.id for element in [self.f1, self.f2, self.f3, self.f4, self.c]]))
        self.assertEqual(self.level[self.c.id].contents, self.contentList)
        self.assertIsNot(self.level[self.c.id].contents, self.contentList)
        self.assertEqual(self.level[self.f3.id].parents, [])
        self.assertEqual(self.level[self.c.id].tags, self.containerTags)
        self.assertIsNot(self.level[self.c.id].tags, self.containerTags)
        
        # Now change stuff on the sub level and commit again
        #===================================================
        self.f5 = self.subLevel.collect(TestUrl('test://band 5 - new song'))
        contentList = elements.ContentList.fromPairs([(10,self.f5), (12,self.f2)])
        self.subLevel.changeContents({self.c: contentList})
        self.subLevel.removeElements([self.f1])
        self.assertEqual(self.subLevel.elements.keys(),
                         set([element.id for element in [self.f2, self.f3, self.f4, self.f5, self.c]]))
        self.subLevel.commit()
        self.assertEqual(set(self.level.elements.keys()),
                     set([element.id for element in [self.f1, self.f2, self.f3, self.f4, self.f5, self.c]]))
        self.assertEqual(self.level[self.c.id].contents, contentList)
        
        self.checkUndo()
        self.checkRedo()

        
def load_tests(loader, standard_tests, pattern):
    # See http://docs.python.org/py3k/library/unittest.html#load-tests-protocol
    suite = unittest.TestSuite()
    for level in [levels.editor,levels.real]:
    #for level in [levels.editor]:
        suite.addTest(CreationTestCase(level))
        suite.addTest(ContentsTestCase(level))
        suite.addTest(CommitTestCase(level))
    return suite
    
if __name__ == "__main__":
    print("To run this test use: python setup.py test --test-suite=test.levels")
    