# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2012 Martin Altmayer, Michael Helmling
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

"""This module contains common QUndoCommands for modifying Elements in Levels."""

from PyQt4 import QtCore, QtGui

from . import levels
from .. import database as db, logging
from ..database import write

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

class CreateDBElementsCommand(QtGui.QUndoCommand):
    """Creates several elements in the database.
    
    This command is created with a number of temporary elements. On redo(), it creates
    permanent IDs and changes them in all levels. Additionally, the elements are stored
    in the database with all attributes (tags, flags, data, ...). The command however
    does not touch the filesystem.
    """
    
    def __init__(self, elements, newInLevel=False):
        """Create the command for *elements*, all of which must be temporary.
        
        If the parameter *newInLevel* is True, the elements will be loaded into the real
        level after creation, and are also deleted from real on undo(). Be careful not to use
        this when some element from *elements* is already contained in real before the command
        is executed (e.g. external file in a playlist).
        """
        super().__init__()
        self.elements = elements
        self.idMap = None
        self.newInLevel = newInLevel
    
    def redo(self):
        db.transaction()
        def dataRow(el):
            row = (el.isFile(),
                   len(el.parents)==0,
                   0 if el.isFile() else len(el.contents),
                   False if el.isFile() else el.major)
            if self.idMap is None:
                return row
            else:
                return (self.idMap[el.id], ) + row
        specs = [ dataRow(el) for el in self.elements ] 
        if self.idMap is None: #  first redo
            newIds = db.write.createElements(specs)
            self.idMap = dict( (el.id, newId) for el,newId in zip(self.elements, newIds))
        else:
            db.write.createElementsWithIds(specs)
        for oldId, newId in self.idMap.items():
            levels.Level._changeId(oldId, newId)
        db.write.addFiles([ (file.id, str(file.url), 0, file.length) # TODO: replace "0" by hash
                           for file in self.elements if file.isFile()])
        for element in self.elements:
            db.write.setTags(element.id, element.tags)
            db.write.setFlags(element.id, element.flags)
            db.write.setData(element.id, element.data)
            if element.isContainer():
                db.write.setContents(element.id, element.contents)
                db.write.setMajor([(element.id, element.major)])
        if self.newInLevel:
            levels.real.loadFromDB(self.idMap.values(), levels.real)
        db.commit()
        for level in levels.allLevels:
            level.emitEvent(set(self.idMap.values()) & set(level.elements.keys()))
        
    def undo(self):
        db.write.deleteElements(list(self.idMap.values()))
        for oldId, newId in self.idMap.items():
            levels.Level._changeId(newId, oldId)
        if self.newInLevel:
            for id in self.idMap:
                del levels.real.elements[id]
        for level in levels.allLevels:
            level.emitEvent(set(self.idMap.keys()) & set(level.elements.keys()))

class CopyElementsCommand(QtGui.QUndoCommand):
    """Copy elements from one level into another, and remove them again on undo()."""
    
    def __init__(self, level, elements):
        super().__init__()
        self.elements = elements
        
    def redo(self):
        for elem in self.elements:
            assert elem.id not in self.level.elements
            elemCopy = self.level.elements[elem.id] = elem.copy()
            elemCopy.level = self.level
            
    def undo(self):
        for elem in self.elements:
            del self.level.elements[elem.id]
