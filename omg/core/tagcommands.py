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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ..database import write as dbWrite
from .. import application, database as db

translate = QtGui.QApplication.translate

class SortValueChangeEvent(application.ChangeEvent):
    """This event is emitted when a sortvalue changes."""
    def __init__(self,tag,valueId,oldValue,newValue):
        self.tag,self.valueId,self.oldValue,self.newValue = tag,valueId,oldValue,newValue       

class ChangeSortValueCommand(QtGui.QUndoCommand):
    """An UndoCommand that changes the sort value of a tag value."""
    def __init__(self, tag, valueId, oldSort, newSort, text = translate(__name__, "change sort value")):
        super().__init__(text)
        self.tag = tag
        self.valueId = valueId
        self.oldSort = oldSort
        self.newSort = newSort

    def redo(self):
        self.setSortValue(self.newSort,self.oldSort)
       
    def undo(self):
        self.setSortValue(self.tag,self.valueId,self.oldSort,self.newSort)
    
    def setSortValue(self, new, old):
        dbWrite.setSortValue(self.tag, self.valueId, new)
        application.dispatcher.changes.emit(SortValueChangeEvent(self.tag, self.valueId, old, new))

class HiddenAttributeChangeEvent(application.ChangeEvent):
    """This event is emitted when the "hidden" attribute of a tag value changes."""
    def __init__(self, tag, valueId, newState):
        self.tag, self.valueId, self.newState = tag, valueId, newState

class HiddenAttributeCommand(QtGui.QUndoCommand):
    """A command to change the "hidden" attribute of a tag value."""
    def __init__(self, tag, valueId, newState = None, text = translate(__name__, 'change hidden flag')):
        """Create the command. If newState is None, then the old one will be fetched from the database
        and the new one set to its negative.
        Otherwise, this class assumes that the current state is (not newState), so don't call this
        whith newState = oldState."""
        super().__init__(text)
        self.tag = tag
        self.valueId = valueId
        self.newState = db.hidden(tag, valueId) if newState is None else newState
       
    def redo(self):
        self.setHidden(self.newState)

    def undo(self):
        self.setHidden(not self.newState)
        
    def setHidden(self, newState):
        dbWrite.setHidden(self.tag, self.valueId, newState)
        application.dispatcher.changes.emit(HiddenAttributeChangeEvent(self.tag, self.valueId, newState))