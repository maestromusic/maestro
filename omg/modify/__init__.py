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

from .. import tags, logging, database as db
from ..constants import REAL, EDITOR, CONTENTS
from . import events
# At the end of the file we will import the submodules real and events.

translate = QtCore.QCoreApplication.translate

logger = logging.getLogger(__name__)



# Type of a change
ADDED,CHANGED,DELETED = 1,2,3
    
            
         
def _debugAll(event):
    logger.debug("EVENT: " + str(event))

    
class ChangeEventDispatcher(QtCore.QObject):
    
    changes = QtCore.pyqtSignal(events.ChangeEvent)
    
    def __init__(self):
        QtCore.QObject.__init__(self)


dispatcher = ChangeEventDispatcher()
dispatcher.changes.connect(_debugAll)

stack = QtGui.QUndoStack()



_currentEditorId = 0
_fileEditorIds = {}
# TODO: Liste wieder leeren?

def editorIdForPath(path):
    global _fileEditorIds
    if path not in _fileEditorIds:
        _fileEditorIds[path] = newEditorId()
    return _fileEditorIds[path]

def newEditorId():
    global _currentEditorId
    _currentEditorId -= 1
    return _currentEditorId


def beginMacro(level, name):
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
