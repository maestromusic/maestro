# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ..application import ChangeEvent
from .. import logging
from . import events
# At the end of the file we will import the submodules real

# DEPRECATED! Use constants.ADDED etc. instead
ADDED,CHANGED,DELETED = 1,2,3

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)


class ElementChangeCommand(QtGui.QUndoCommand):
    """An undo command changing the elements on some level. Has the following attributes:
     - level: an instance of omg.models.levels.Level
     - ids: a list of IDs which are affected by the command
     - contents: a boolean indicating if content relations have changed
    """
    def __init__(self, level, ids = None, contents = None, text = None):
        super().__init__()
        self.level = level
        self.ids = ids
        self.contents = contents
        if text is not None:
            self.setText(text)
    
    def redoChanges(self):
        raise NotImplementedError()
    
    def undoChanges(self):
        raise NotImplementedError()
    
    def redo(self):
        self.redoChanges()
        self.level.changed.emit(self.ids, self.contents)
        
    def undo(self):
        self.undoChanges()
        self.level.changed.emit(self.ids, self.contents)

class ChangeEventDispatcher(QtCore.QObject):
    
    changes = QtCore.pyqtSignal(ChangeEvent)
    
    def __init__(self):
        QtCore.QObject.__init__(self)

dispatcher = ChangeEventDispatcher()
 
            
def _debugAll(event):
    logger.debug("EVENT: " + str(event))
    
dispatcher.changes.connect(_debugAll)

stack = QtGui.QUndoStack()

def beginMacro(name):
    stack.beginMacro(name)

def endMacro():
    stack.endMacro()

def push(command):
    stack.push(command)
        

def createUndoAction(parent, prefix = ""):
    return stack.createUndoAction(parent, prefix)

def createRedoAction(parent,prefix = ""):
    return stack.createRedoAction(parent, prefix)


# This is simply so that other modules can use modify.real.<stuff>
from . import real
