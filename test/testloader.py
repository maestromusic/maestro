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

import unittest

class TestLoader(unittest.TestLoader):
    """Custom test loader that initializes OMG's framework before starting tests and works better with
    parametrized tests.
    
    When loading tests from a module, the default test loader will first create an instance of each class 
    found in the module that is derived from unittest.TestCase. This does not work if the test constructor
    expects arguments, if more than one instance should be created and if several tests share an abstract
    base class. To allow some customization, the default test loader will call module.load_tests (if present)
    and use its return value instead. But this is done *after* creating an instance of each class because
    those instances are passed as parameter to load_tests. 
    
    There are several ways around this, but they are ugly and break OOP, see e.g. 
        http://bugs.python.org/issue7897
        http://bugs.python.org/issue12600
        
    This test loader fixes this by calling load_tests directly if present (without useful arguments) and
    using the default behaviour else.
    
    See http://packages.python.org/distribute/setuptools.html#test-loader 
    """
    def __init__(self):
        from omg import application
        from omg.core import tags
        # Save the app from the garbage collector
        self.app = application.init(cmdConfig=['main.collection=/'],type="test",exitPoint='noplugins')
        for name,type in  [("artist","varchar"),("title","varchar"),("album","varchar"),("date","date"),
                           ("genre","varchar"),("comment","text")]:
            tags.addTagType(name,tags.ValueType.byName(type))
            
    def loadTestsFromModule(self,module):
        if hasattr(module,'load_tests'):
            return getattr(module,'load_tests')(self,[],None)
        else:
            return super().loadTestsFromModule(module)
        