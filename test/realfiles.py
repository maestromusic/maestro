#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""Unittests for the realfiles2-package."""

import unittest, shutil, os

if __name__ == "__main__":
    # Import and initialize modules
    from omg import config # Initialize config and logging
    config.init([])
    from omg import database
    database.connect()
    from omg import tags
    tags.init()
    
    from omg import realfiles2, FlexiDate
    
    PATH_EMPTY = 'test/realfiles/empty'
    PATH_FULL = 'test/realfiles/full'
    PATH_TEST = 'test/realfiles/test'
    PATH_WITHOUT_EXT = 'test/realfiles/testwithoutext'

    ORIGINAL_TAGS = {
    tags.get("artist"): ["Martin","Michael"],
    tags.get("title"): ['The "äöü#~♀" Song'],
    tags.get("album"): ["Dullness"],
    tags.get("date"): [FlexiDate(2010),FlexiDate(2000,12,24)],
    tags.get("genre"): ["Dull","Gangsta"],
    tags.get("description"): ["äöü#~♀","..."]
    }

    TAGS_TO_WRITE = {
    tags.get("artist"): ["You","Know","Who"],
    tags.get("date"): [FlexiDate(1900,12,24)],
    tags.get("description"): ["Stupid ümläütß"],
    tags.get("conductor"): ["Absolutely","Nobody"]
    }
    ORIGINAL_POSITION = 1

# Abstract base class for our test cases
class BaseTest(unittest.TestCase):
    def __init__(self,ext):
        super(BaseTest,self).__init__()
        self.full = PATH_FULL + "." + ext
        self.empty = PATH_EMPTY + "." + ext
        self.test = PATH_TEST + "." + ext
    def __str__(self):
        return "{name} for file {f}".format(name = self.__class__.__name__, f = self.full)
   
class OpenTest(BaseTest):
    def setUp(self):
        shutil.copyfile(self.full,PATH_WITHOUT_EXT)
        
    def runTest(self):
        self.file = realfiles2.get(self.full,absolute=True)
        self.file = realfiles2.get(PATH_WITHOUT_EXT,absolute=True)

    def tearDown(self):
        os.remove(PATH_WITHOUT_EXT)

class ReadTest(BaseTest):
    def setUp(self):
        self.file = realfiles2.get(self.full,absolute=True)

    def runTest(self):
        self.file.read()
        self.assertEqual(self.file.position,ORIGINAL_POSITION)
        for key,values in self.file.tags.items():
            self.assertEqual(values,ORIGINAL_TAGS[key])
        self.assertEqual(self.file.tags,ORIGINAL_TAGS)
        self.assertIn(type(self.file.length),(float, int))
        self.assertGreaterEqual(self.file.length,0)

class RemoveTest(BaseTest):
    def setUp(self):
        shutil.copyfile(self.full,self.test)
        self.file = realfiles2.get(self.test,absolute=True)

    def runTest(self):
        tagsToRemove = [tags.get(name) for name in ('artist','title','conductor','notexistent2')]
        self.file.remove(tagsToRemove)
        del self.file
        self.file = realfiles2.get(self.test, absolute = True)
        self.file.read()
        self.assertEqual(self.file.tags,{k:v for k,v in ORIGINAL_TAGS.items() if k not in tagsToRemove})

    def tearDown(self):
        os.remove(self.test)

class EmptyFileTest(BaseTest):
    def setUp(self):
        shutil.copyfile(self.empty,self.test)
        self.file = realfiles2.get(self.test,absolute=True)

    def runTest(self):
        self.file.tags[tags.get('artist')] = ['Someone','Everyone']
        self.file.save()
        del self.file
        self.file = realfiles2.get(self.test, absolute = True)
        self.file.read()
        self.assertEqual(self.file.tags,{tags.get('artist'): ['Someone','Everyone']})

    def tearDown(self):
        os.remove(self.test)


class WriteTest(BaseTest):
    def setUp(self):
        shutil.copyfile(self.full,self.test)
        self.file = realfiles2.get(self.test,absolute=True)

    def runTest(self):
        self.file.tags = TAGS_TO_WRITE
        self.file.position = 2
        self.file.save()
        del self.file
        self.file = realfiles2.get(self.test, absolute = True)
        self.file.read()
        self.assertEqual(self.file.position,2)
        self.assertEqual(self.file.tags,TAGS_TO_WRITE)
        

    def tearDown(self):
        os.remove(self.test)
    

class Id3Test(unittest.TestCase):
    def setUp(self):
        self.test =  'test/realfiles/three_types_of_comments_test.mp3'
        shutil.copyfile('test/realfiles/three_types_of_comments.mp3', self.test)
        self.file = realfiles2.get(self.test, absolute=True)
    
    def test_read(self):
        self.file.read()
        self.file.tags
        self.assertEqual(self.file.tags[tags.get('genre')], ['Rock'])
        self.assertEqual(len(self.file.tags[tags.get('comment')]), 3)
    
    def test_write(self):
        self.file.read()
        self.file.tags[tags.get('comment')].append('another comment')
        self.file.save()
        del self.file
        self.file = realfiles2.get(self.test, absolute = True)
        self.file.read()
        self.assertEqual(len(self.file.tags[tags.get('comment')]), 4)
    
    def tearDown(self):
        os.remove(self.test)
        
        

if __name__ == "__main__":
    suite = unittest.TestSuite()
    
    for ext in ('ogg','mp3', 'mpc', 'flac', 'spx'):
        suite.addTest(OpenTest(ext))
        suite.addTest(ReadTest(ext))
        suite.addTest(RemoveTest(ext))
        suite.addTest(EmptyFileTest(ext))
        suite.addTest(WriteTest(ext))
        suite.addTest(Id3Test('test_read'))
        suite.addTest(Id3Test('test_write'))
    
    unittest.TextTestRunner(verbosity=2).run(suite)
