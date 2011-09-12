#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""Unittests for the realfiles-package."""

import unittest, shutil, os

if __name__ == "__main__":
    # Import and initialize modules
    from omg import config # Initialize config and logging
    config.init([])
    from omg import database
    database.connect()
    from omg import tags
    tags.init()
    
    from omg import realfiles, FlexiDate
    
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

   
class OpenTest(BaseTest):
    def setUp(self):
        shutil.copyfile(self.full,PATH_WITHOUT_EXT)
        
    def runTest(self):
        self.file = realfiles.get(self.full,absolute=True)
        self.file = realfiles.get(PATH_WITHOUT_EXT,absolute=True)

    def tearDown(self):
        os.remove(PATH_WITHOUT_EXT)


class ReadTest(BaseTest):
    def setUp(self):
        self.file = realfiles.get(self.full,absolute=True)

    def runTest(self):
        self.file.read()
        self.assertEqual(self.file.position,ORIGINAL_POSITION)
        for key,values in self.file.tags.items():
            self.assertEqual(values,ORIGINAL_TAGS[key])
        self.assertEqual(self.file.tags,ORIGINAL_TAGS)
        self.assertEqual(type(self.file.length),float)
        self.assertGreater(self.file.length,0)


class RemoveTest(BaseTest):
    def setUp(self):
        shutil.copyfile(self.full,self.test)
        self.file = realfiles.get(self.test,absolute=True)

    def runTest(self):
        tagsToRemove = [tags.get(name) for name in ('artist','title','conductor','notexistent2')]
        self.file.remove(tagsToRemove)
        self.file.read()
        self.assertEqual(self.file.tags,{k:v for k,v in ORIGINAL_TAGS.items() if k not in tagsToRemove})

    def tearDown(self):
        os.remove(self.test)


class EmptyFileTest(BaseTest):
    def setUp(self):
        shutil.copyfile(self.empty,self.test)
        self.file = realfiles.get(self.test,absolute=True)

    def runTest(self):
        self.file.tags[tags.get('artist')] = ['Someone','Everyone']
        self.file.save()
        self.file.read()
        self.assertEqual(self.file.tags,{tags.get('artist'): ['Someone','Everyone']})

    def tearDown(self):
        os.remove(self.test)


class WriteTest(BaseTest):
    def setUp(self):
        shutil.copyfile(self.full,self.test)
        self.file = realfiles.get(self.test,absolute=True)

    def runTest(self):
        self.file.tags = TAGS_TO_WRITE
        self.file.position = 2
        self.file.save()
        self.file.read()
        self.assertEqual(self.file.position,2)
        self.assertEqual(self.file.tags,TAGS_TO_WRITE)
        

    def tearDown(self):
        os.remove(self.test)


if __name__ == "__main__":
    suite = unittest.TestSuite()
    
    for ext in ('ogg','mp3'):
        suite.addTest(OpenTest(ext))
        suite.addTest(ReadTest(ext))
        suite.addTest(RemoveTest(ext))
        suite.addTest(EmptyFileTest(ext))
        suite.addTest(WriteTest(ext))
    
    unittest.TextTestRunner(verbosity=2).run(suite)
