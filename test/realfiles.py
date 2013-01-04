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

from omg import application, utils, filebackends, database as db
from omg.core import tags
    
PATH_BASE = os.path.join(os.getcwd(),os.path.dirname(__file__))
PATH_EMPTY = os.path.join(PATH_BASE,'realfiles/empty')
PATH_FULL = os.path.join(PATH_BASE,'realfiles/full')
PATH_INVALID = os.path.join(PATH_BASE,'realfiles/invalid')
PATH_TEST = os.path.join(PATH_BASE,'realfiles/test')

ORIGINAL_TAGS = {
tags.get("artist"): ["Martin","Michael"],
tags.get("title"): ['The "äöü#~♀" Song'],
tags.get("album"): ["Dullness"],
tags.get("date"): [utils.FlexiDate(2010),utils.FlexiDate(2000,12,24)],
tags.get("genre"): ["Dull","Gangsta"],
tags.get("comment"): ["äöü#~♀","..."]
}

TAGS_TO_WRITE = {
tags.get("artist"): ["You","Know","Who"],
tags.get("date"): [utils.FlexiDate(1900,12,24)],
tags.get("comment"): ["Stupid ümläütß"],
tags.get("conductor"): ["Absolutely","Nobody"]
}
ORIGINAL_POSITION = 1


def getFile(path):
    file = filebackends.getFile('file://'+path)
    file.readTags()
    return file
    
    
# Abstract base class for our test cases
class BaseTest(unittest.TestCase):
    def __init__(self,ext):
        super().__init__()
        self.full = PATH_FULL + "." + ext
        self.empty = PATH_EMPTY + "." + ext
        self.invalid = PATH_INVALID + "." + ext
        self.test = PATH_TEST + "." + ext

   
class OpenTest(BaseTest):
    def runTest(self):
        self.file = getFile(self.full)


class ReadTest(BaseTest):
    def setUp(self):
        self.file = getFile(self.full)

    def runTest(self):
        self.assertEqual(self.file.position,ORIGINAL_POSITION)
        for key,values in self.file.tags.items():
            self.assertEqual(values,ORIGINAL_TAGS[key])
        self.assertEqual(self.file.tags,ORIGINAL_TAGS)
        self.assertEqual(type(self.file.length),int)
        self.assertGreaterEqual(self.file.length,0)


class RemoveTest(BaseTest):
    def setUp(self):
        shutil.copyfile(self.full,self.test)
        self.file = getFile(self.test)

    def runTest(self):
        tagsToRemove = [tags.get(name) for name in ('artist','title','comment')]
        for tag in tagsToRemove:
            del self.file.tags[tag]
        self.file.saveTags()
        self.file.readTags()
        self.assertEqual(self.file.tags,{k:v for k,v in ORIGINAL_TAGS.items() if k not in tagsToRemove})

    def tearDown(self):
        os.remove(self.test)


class EmptyFileTest(BaseTest):
    def setUp(self):
        shutil.copyfile(self.empty,self.test)
        self.file = getFile(self.test)

    def runTest(self):
        self.file.tags[tags.get('artist')] = ['Someone','Everyone']
        self.file.saveTags()
        self.file.readTags()
        self.assertEqual(self.file.tags,{tags.get('artist'): ['Someone','Everyone']})

    def tearDown(self):
        os.remove(self.test)


class InvalidTagsTest(BaseTest):
    def setUp(self):
        shutil.copyfile(self.invalid,self.test)
        
    def runTest(self):
        self.file = getFile(self.test)
        tag = tags.get('artist')
        self.assertEqual(list(self.file.tags.keys()),[tag])
        self.assertTrue(len(self.file.tags[tag]) == 1)
        self.assertTrue(tag.isValid(self.file.tags[tag][0]))


@unittest.skip("Broken because pytaglib does not write comments in mp3.")
class WriteTest(BaseTest):
    def setUp(self):
        shutil.copyfile(self.full,self.test)
        self.file = getFile(self.test)

    def runTest(self):
        self.file.tags = TAGS_TO_WRITE
        self.file.saveTags()
        self.file.readTags()
        print(self.test)
        self.assertEqual(self.file.tags,TAGS_TO_WRITE)
        
    def tearDown(self):
        os.remove(self.test)


def load_tests(loader=None, standard_tests=None, pattern=None):
    # See http://docs.python.org/py3k/library/unittest.html#load-tests-protocol
    suite = unittest.TestSuite()
    for ext in ('ogg','mp3'):
        suite.addTest(OpenTest(ext))
        suite.addTest(ReadTest(ext))
        suite.addTest(RemoveTest(ext))
        suite.addTest(EmptyFileTest(ext))
        suite.addTest(WriteTest(ext))
    suite.addTest(InvalidTagsTest('ogg')) # invalid tag handling is independent of file format
    return suite


if __name__ == "__main__":
    print("To run this test use: python setup.py test --test-suite=test.realfiles")
    