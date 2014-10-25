# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
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

import unittest, functools

from maestro import application


class UndoableTestCase(unittest.TestCase):
    """A testcase that records calls to the assert*-methods together with the position of the undostack.
    Later it can undo and redo all commands on the stack and repeat all assert*-methods at the appropriate
    times.
    """
    def __init__(self, methodName='runTest'):
        super().__init__(methodName)
        self.stack = application.stack
        self.checks = []
        self._recordingStopped = False
        self._record = True
        
    def setUp(self):
        application.stack.clear()
        
    def stopRecording(self):
        """Do not record assert*-methods anymore."""
        self._recordingStopped = True
                                          
    def checkUndo(self):
        """Undo all commands on the stack and repeat the recorded assert*-methods at the appropriate times.
        """
        print("Start checkUndo for {} at {}".format(type(self).__name__, self.stack.index()))
        for method, index, args in reversed(self.checks):
            #print("Undoing {} at {}".format(method.__name__,index))
            self.stack.setIndex(index)
            self._record = False
            method(*args)
            self._record = True
        
        application.stack.setIndex(0)
        
    def checkRedo(self):
        """Redo all commands on the stack and repeat the recorded assert*-methods at the appropriate times.
        """
        print("Start checkRedo for {}".format(type(self).__name__))
        assert application.stack.index() == 0
        for method, index, args in self.checks:
            #print("Redoing {} at {}".format(method.__name__,index))
            self.stack.setIndex(index)
            self._record = False
            method(*args)
            self._record = True
        
    def _assert(self, methodName, *args):
        """Record the assert*-method of the given name, then call it with the given arguments."""
        if self._record and not self._recordingStopped:
            args = (self,)+args
            method = getattr(unittest.TestCase, methodName)
            #print("Appending {} at {}".format(method.__name__,self.stack.index()))
            self.checks.append((method, self.stack.index(), args))
            self._record = False
            method(*args)
            self._record = True
            
    # below all assert* methods are overwritten by _assert(methodName,...)
    # Of course, this is done using functools.partial
    # Unfortunately Python's binding of methods to class instances on attribute access does not work
    # with partial-objects. Thus we have to implement it here using a simple descriptor.
    
class AssertDescriptor:
    def __init__(self,name):
        self.name = name
        
    def __get__(self,instance,owner):
        if instance is not None:
            return functools.partial(owner._assert,instance,self.name)
        else: return super().__get__(instance,owner)
        
for name in ['assertEqual', 'assertTrue', 'assertFalse', 'assertIs', 'assertIsNot',
             'assertIsNone', 'assertIsNotNone', 'assertIn', 'assertNotIn', 'assertIsInstance',
             'assertNotIsInstance']:
    setattr(UndoableTestCase, name, AssertDescriptor(name)) 
            