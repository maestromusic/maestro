# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2012-2013 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtGui
from PyQt4.QtCore import Qt

from ..database import write as dbWrite
from ..core.levels import real
from ..core import tags
from .. import application, database as db

translate = QtGui.QApplication.translate

class SortValueChangeEvent(application.ChangeEvent):
    """This event is emitted when a sortvalue changes."""
    def __init__(self,tag,valueId,oldValue,newValue):
        self.tag,self.valueId,self.oldValue,self.newValue = tag,valueId,oldValue,newValue       


class ChangeSortValueCommand:
    """An UndoCommand that changes the sort value of a tag value."""
    def __init__(self, tag, valueId, oldSort, newSort):
        self.text = translate("ChangeSortValueCommand", "change sort value")
        self.tag = tag
        self.valueId = valueId
        self.oldSort = oldSort
        self.newSort = newSort

    def redo(self):
        self.setSortValue(self.newSort,self.oldSort)
       
    def undo(self):
        self.setSortValue(self.tag,self.valueId,self.oldSort,self.newSort)
    
    def setSortValue(self, new, old):
        db.query("UPDATE {}values_{} SET sort_value = ? WHERE tag_id = ? AND id = ?"
                 .format(db.prefix, self.tag.type), new, self.tag.id, self.valueId)
        application.dispatcher.emit(SortValueChangeEvent(self.tag, self.valueId, old, new))


class HiddenAttributeChangeEvent(application.ChangeEvent):
    """This event is emitted when the "hidden" attribute of a tag value changes."""
    def __init__(self, tag, valueId, newState):
        (self.tag, self.valueId, self.newState) = (tag, valueId, newState)


class HiddenAttributeCommand:
    """A command to change the "hidden" attribute of a tag value."""
    
    def __init__(self, tag, valueId, newState=None):
        """Create the command. If newState is None, then the old one will be fetched from the database
        and the new one set to its negative.
        Otherwise, this class assumes that the current state is (not newState), so don't call this
        whith newState = oldState."""
        self.text = translate("HiddenAttributeCommand", "change hidden flag")
        self.tag = tag
        self.valueId = valueId
        self.newState = db.hidden(tag, valueId) if newState is None else newState
       
    def redo(self):
        self.setHidden(self.newState)

    def undo(self):
        self.setHidden(not self.newState)
        
    def setHidden(self, newState):
        db.query("UPDATE {}values_{} SET hide = ? WHERE tag_id = ? AND id = ?"
                 .format(db.prefix, self.tag.type), newState, self.tag.id, self.valueId)
        application.dispatcher.emit(HiddenAttributeChangeEvent(self.tag, self.valueId, newState))


def renameTagValue(tag, oldValue, newValue):
    """A method to rename *all* instances of a certain tag value. For the real level only.
    
    The most prominent use is to correct the spelling of (foreign language) artists, composers etc.
    """
    oldId = db.idFromValue(tag, oldValue)
    newId = db.idFromValue(tag, newValue, insert=True)
    
    result = db.query("SELECT element_id, value_id FROM {}tags WHERE tag_id=? AND "
                        "(value_id=? OR value_id=?)".format(db.prefix),
                        tag.id, oldId, newId)
    elemToList = {}
    for elementId, valueId in result:
        if elementId not in elemToList:
            elemToList[elementId] = [valueId]
        else:
            elemToList[elementId].append(valueId) 
    onlyOld = [ id for id, vals in elemToList.items() if len(vals) == 1 and vals[0] == oldId ]
    both = [ id for id, vals in elemToList.items() if len(vals) == 2 ]
    bar = QtGui.QProgressDialog(translate("renameTagValue", "Renaming {} to {} ...")
                                .format(oldValue, newValue),
                                None,
                                0,
                                len(onlyOld) + len(both),
                                application.mainWindow)
    bar.setMinimumDuration(1000)
    bar.setWindowModality(Qt.WindowModal)
    application.stack.beginMacro(translate("renameTagValue", "rename {} value").format(tag),
                                 transaction=True)
    onlyOldDiff = tags.SingleTagDifference(tag, replacements=[(oldValue, newValue)])
    bothDiff = tags.SingleTagDifference(tag, removals=[newValue])
    for i, elid in enumerate(onlyOld):
        bar.setValue(i)
        real.changeTags({real.fetch(elid) : onlyOldDiff})
    for i, elid in enumerate(both, start=len(onlyOld)):
        bar.setValue(i)
        real.changeTags({real.fetch(elid) : bothDiff})
    bar.setValue(bar.value()+1)
    application.stack.endMacro()
