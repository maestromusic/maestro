# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

from . import tageditor
from .. import application
from ..core import tags, flags


class Record:
    """Record that stores a flag and two lists of elements: All elements that are currently edited and the
    elements among those that have the flag."""
    def __init__(self,flag,allElements,elementsWithFlag):
        self.flag = flag
        self.allElements = allElements
        self.elementsWithFlag = elementsWithFlag
        
    def isCommon(self):
        """Return whether all edited elements have this record's flag."""
        return len(self.allElements) == len(self.elementsWithFlag)
    
    def merge(self,other):
        """Return a copy of this record which contains the union of the elementsWithFlag of this records and
        the record *other*."""
        elements = list(self.elementsWithFlag)
        elements.extend(el for el in other.elementsWithFlag if el not in elements)
        return Record(self.flag,self.allElements,elements)


class RecordModel(QtCore.QObject):
    """A RecordModel is basically the data-structure used by the flageditor. It simply stores a list of
    records and provides methods to change this list which emit signals when doing so.
    
    The list of Records can be accessed via item access.
    
    Intentionally the commands of RecordModel are very basic, so that each command can be undone easily.
    In contrast to the FlagEditorModel, the RecordModel does not do any Undo/Redo-stuff. Instead,
    FlagEditorModel splits its complicated actions into several calls of the methods of RecordModel which are
    assembled into an FlagEditorUndoCommand.
    
    Another advantage of having only basic commands is that the GUI has only to react to basic signals.
    """
    recordInserted = QtCore.pyqtSignal(int,Record)
    recordRemoved = QtCore.pyqtSignal(Record)
    recordChanged = QtCore.pyqtSignal(Record,Record)
    
    def __len__(self):
        return len(self._records)
    
    def __iter__(self):
        return self._records.__iter__()
    
    def index(self,record):
        """Return the position of *record* in the model."""
        return self._records.index(record)
    
    def setRecords(self,records):
        """Set the list of records."""
        self._records = list(records)
        
    def insertRecord(self,pos,record):
        """Insert *record* at the given position."""
        self._records.insert(pos,record)
        self.recordInserted.emit(pos,record)
        
    def removeRecord(self,record):
        """Remove *record* from the model."""
        self._records.remove(record)
        self.recordRemoved.emit(record)
        
    def changeRecord(self,oldRecord,newRecord):
        """Replace *oldRecord* by *newRecord* keeping the position. Do not edit any record! (this would break
        redo/undo."""
        pos = self._records.index(oldRecord)
        self._records[pos] = newRecord
        self.recordChanged.emit(oldRecord,newRecord)
    
        
class FlagEditorModel(QtCore.QObject):
    """The model of the FlagEditor. Internally it stores
    
        - a list of elements that are currently edited.
        - a list of records storing the flags as used by the model: Each record contains a flag and the
        sublist of elements that have this flag.
    
    Internally FlagEditorModel works very similar to TagEditorModel, so see the latter's docstring.
    
    Model parameters are:
    
        - level: the level that contains the elements
        - elements: a list of elements whose flags will be displayed and edited by this model.
        - stack: An undo stack or None, in which case the global stack will be used (only use your own stacks
          in modal dialogs)
    """
    resetted = QtCore.pyqtSignal()
    
    def __init__(self,level=None,elements=None,stack=None):
        super().__init__()
        
        self.records = RecordModel()
        self.recordInserted = self.records.recordInserted
        self.recordRemoved = self.records.recordRemoved
        self.recordChanged = self.records.recordChanged
        
        self.level = None # will be set in self.setElements
        if elements is None:
            elements = []
        self.setElements(level,elements)

        if stack is None:
            self.stack = application.stack
        else: self.stack = stack
        
    def setElements(self,level,elements):
        """Reset the model to display and edit the tags of *elements*."""
        if self.level != level:
            if self.level is not None:
                self.level.disconnect(self._handleLevelChanged)
            if level is not None:
                level.connect(self._handleLevelChanged)
        self.level = level
        self.elements = elements
        self.records.setRecords(self._createRecords().values())
        self.resetted.emit()
                
    def _createRecords(self):
        """Create records from the flags of self.elements and return them as dict mapping flagtype to record.
        """
        records = {}
        for element in self.elements:
            for flag in element.flags:
                if flag in records:
                    records[flag].elementsWithFlag.append(element)
                else: records[flag] = Record(flag,self.elements,[element])
        return records
        
    def getRecord(self,flag):
        """Get the record for the given flag or None if there is no record for this flag."""
        for record in self.records:
            if record.flag == flag:
                return record
        return None 
        
    def isEmpty(self):
        """Return whether there is at least one record/flag in one of the elements governed by this model."""
        return len(self.records) == 0
    
    def addFlag(self,flag,elementsWithFlag = None):
        """Add a flag to the elements contained in *elementsWithFlag* or all elements if this parameter is
        None.
        """
        if elementsWithFlag is None:
            elementsWithFlag = self.elements
        diff = flags.FlagDifference(additions=[flag])
        differences = {element: diff for element in elementsWithFlag if flag not in element.flags}
        self.level.changeFlags(differences)
        
    def removeFlag(self,flag):
        """Remove a flag from all elements."""
        diff = flags.FlagDifference(removals=[flag])
        differences = {element: diff for element in self.elements if flag in element.flags}
        self.level.changeFlags(differences)
        
    def changeRecord(self,oldRecord,newRecord):
        """Change *oldRecord* into *newRecord*. Make sure, that both records have self.elements as list of
        elements and a nonempty sublist thereof as list of elements with flag."""
        if len(newRecord.elementsWithFlag) == 0:
            raise ValueError("newRecord must contain at least one element; otherwise use removeFlag.")
        assert oldRecord.flag == newRecord.flag # only this is supported by the GUI
    
        removeElements = [el for el in oldRecord.elementsWithFlag if el not in newRecord.elementsWithFlag]
        addElements = [el for el in newRecord.elementsWithFlag if el not in oldRecord.elementsWithFlag]
        
        removeDiff = flags.FlagDifference(removals=[oldRecord.flag])
        addDiff = flags.FlagDifference(additions=[newRecord.flag])
        differences = {el: removeDiff for el in removeElements}
        differences.update({el: addDiff for el in addElements})
        if len(differences) > 0:
            self.level.changeFlags(differences)

    def getFlagsOfElement(self,element):
        """Return all flags of a specific element."""
        return [record.flag for record in self.records if element in record.elementsWithFlag]
    
    def _handleLevelChanged(self,event):
        """React to change events fo the underlying level."""
        currentIds = [el.id for el in self.elements]
        if all(id not in currentIds for id in event.dataIds):
            return # not our problem
        
        actualRecords = self._createRecords()
        
        for myRecord in list(self.records):
            if myRecord.flag not in actualRecords:
                self.records.removeRecord(myRecord)
            else:
                actualRecord = actualRecords[myRecord.flag]
                del actualRecords[myRecord.flag]
                if actualRecord.elementsWithFlag != myRecord.elementsWithFlag:
                    self.records.changeRecord(myRecord,actualRecord)
                #else: unchanged => nothing to do
                
        # Add the remaining records
        for actualRecord in actualRecords.values():
            self.records.insertRecord(len(self.records),actualRecord)
          