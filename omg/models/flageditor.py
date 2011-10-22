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

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from .. import modify, tags


class Record:
    """Record that stores a flag and two lists of elements: All elements that are currently edited and the
    elements among those that do have the flag."""
    def __init__(self,flag,allElements,elementsWithFlag):
        self.flag = flag
        self.allElements = allElements
        self.elementsWithFlag = elementsWithFlag
        
    def isCommon(self):
        """Return whether all edited elements have this record's flag."""
        return len(self.allElements) == len(self.elementsWithFlag)


class FlagEditorModel(QtCore.QObject):
    """The model of the FlagEditor. Internally it stores
    
        - a list of elements that are currently edited. If *saveDirectly* is True, these elements will only
        contain the tags-attribute (actually we only need the title). If *saveDirectly* is False they will
        also store the original flags for the UndoCommand generated by save. These flags won't be updated
        on ChangeEvents, so you must use either use the flageditor as dialog or set *saveDirectly* to True.
        - a list of records storing the flags as used by the model: Each record contains a flag and the
        sublist of elements that have this flag.
    
    Model parameters are:
    
        - level: whether changes in this model affect the database or the editor
        - elements: a list of elements whose flags will be displayed and edited by this model. This list
        should contain tags and flags, otherwise they are loaded from the database. Of course the model will
        use a copy of the elements internally.
        - saveDirectly: whether changes in the model are applied directly.
        - tagEditorModel: The model of the tageditor in which this flageditor is contained. This is used to
          react on titlesChanged signals and to choose the correct undostack if saveDirectly is False.
        
    \ """
    resetted = QtCore.pyqtSignal()
    recordInserted = QtCore.pyqtSignal(int,Record)
    recordRemoved = QtCore.pyqtSignal(Record)
    recordChanged = QtCore.pyqtSignal(Record,Record)
    titlesChanged = QtCore.pyqtSignal(list)
    
    def __init__(self,level,elements,saveDirectly,tagEditorModel=None):
        super().__init__()
        
        self.level = level
        self.saveDirectly = saveDirectly
        self.undoStack = tagEditorModel.undoStack if not saveDirectly else None
        tagEditorModel.titlesChanged.connect(self._handleTitlesChanged)
        self.setElements(elements)
            
        # This may be deactivated if the FlagEditor is run as a dialog...but it should not cause any harm.
        modify.dispatcher.changes.connect(self._handleDispatcher)
        
    def setElements(self,elements):
        """Reset the model to display and edit the tags of (a copy of) *elements*."""
        self.elements = [el.export(attributes=['tags','flags'],copyList=['tags']) for el in elements]
        for new,old in zip(self.elements,elements):
            # Generate a title using the tags from the old element
            if tags.TITLE in old.tags:
                new.title = new.getTitle(old.tags[tags.TITLE])
                #TODO: maddin, geht das so?
        self.createRecords()
        
    def createRecords(self):
        """Create records reading the flags from self.elements. Afterwards set the elements' flags
        attributes to None and emit a resetted-signal."""
        self.records = []
        for element in self.elements:
            for flag in element.flags:
                existingRecord = self.getRecord(flag)
                if existingRecord is None:
                    self.records.append(Record(flag,self.elements,[element]))
                else: existingRecord.elementsWithFlag.append(element)
            if self.saveDirectly:
                element.flags = None
        self.resetted.emit()
        
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
        None. If there is already a record for this flag, *elementsWithFlag* will be added to that record."""
        if elementsWithFlag is None:
            elementsWithFlag = self.elements
        record = self.getRecord(flag)
        if record is not None:
            newElements = [el for el in elementsWithFlag if el not in record.elementsWithFlag]
            if len(newElements) > 0:
                newRecord = Record(flag,self.elements,record.elementsWithFlag + newElements)
                command = FlagEditorUndoCommand(self,self._changeRecord(record,newRecord),
                                                text=self.tr("Add flag"))
                self._push(command)
        else:
            record = Record(flag,self.elements,elementsWithFlag)
            command = FlagEditorUndoCommand(self,self._insertRecord,len(self.records),record,
                                            text=self.tr("Add flag"))
            self._push(command)
        
    def removeFlag(self,flag):
        """Remove a flag from all elements."""
        record = self.getRecord(flag)
        command = FlagEditorUndoCommand(self,self._removeRecord,record,text=self.tr("Remove flag"))
        self._push(command)
        
    def changeRecord(self,oldRecord,newRecord):
        """Change *oldRecord* into *newRecord*. Make sure, that both records have self.elements as list of
        elements and a nonempty sublist thereof as list of elements with flag."""
        if len(newRecord.elementsWithFlag) > 0:
            raise ValueError("newRecord must contain at least one element; otherwise use removeFlag.")
        command = FlagEditorUndoCommand(self,self._changeRecord,oldRecord,newRecord,
                                        text=self.tr("Change flag record"))
        self._push(command)
    
    # The next three methods are called by FlagEditorUndoCommand
    def _insertRecord(self,pos,record):
        """Really insert a record at the given position. This method may only be called by an UndoCommand."""
        self.records.insert(pos,record)
        self.recordInserted.emit(pos,record)
    
    def _removeRecord(self,record):
        """Really remove a record. This method may only be called by an UndoCommand."""
        self.records.remove(record)
        self.recordRemoved.emit(record)

    def _changeRecord(self,oldRecord,newRecord):
        """Really change *oldRecord* into *newRecord*. This method may only be called by an UndoCommand."""
        self.records[self.records.index(oldRecord)] = newRecord
        self.recordChanged.emit(oldRecord,newRecord)
        
    def _push(self,command):
        """Push the UndoCommand *command* to the correct UndoStack."""
        if self.saveDirectly:
            modify.push(command)
        else: self.undoStack.push(command)
        
    def createRedoAction(self,parent=None,prefix=""):
        """Create an action redoing the last change in this model."""
        if self.saveDirectly:
            return modify.createRedoAction(self.level,parent,prefix)
        else: return self.undoStack.createRedoAction(parent,prefix)
    
    def createUndoAction(self,parent=None,prefix=""):
        """Create an action undoing the last change in this model."""
        if self.saveDirectly:
            return modify.createUndoAction(self.level,parent,prefix)
        else: return self.undoStack.createUndoAction(parent,prefix)
    
    def getFlagsOfElement(self,element):
        """Return all flags of a specific element."""
        return [record.flag for record in self.records if element in record.elementsWithFlag]
    
    def getChanges(self):
        """Return the changes between the flags as stored in the records and the flags in the database
        or in the editor. This method may only be used if saveDirectly is False."""
        if self.saveDirectly:
            raise RuntimeError("You must not call save in a FlagEditorModel that saves directly.")
            
        return {element.id: (element.flags,self.getFlagsOfElement(element))
                for element in self.elements}

    def _handleDispatcher(self,event):
        """React to change events."""
        if isinstance(event,modify.events.ElementsDeletedEvent):
            affectedElements = [element for element in self.elements if element.id in event.ids()]
            if len(affectedElements) > 0:
                # All records store a reference to this list, so this will update them, too.
                self.elements = [element for element in self.elements if element not in affectedElements]
                if len(self.elements) == 0:
                    self.createRecords()
                    return
                for record in self.records[:]: # list may change
                    remaining = [element for element in record.elementsWithFlag
                                    if element not in affectedElements]
                    if len(remaining) == 0:
                        self._removeRecord(record)
                    elif len(remaining) < len(record.elementsWithFlag):
                        self._changeRecord(record,Record(record.flag,self.elements,remaining))
            return
        
        elif isinstance(event,modify.events.FlagTypeChangedEvent):
            if event.action == modify.CHANGED: # ADDED and REMOVED don't affect us
                # This finds the record using the flagtype's id and thus also works with the changed flag.
                record = self.getRecord(event.flagType)
                if record is not None:
                    # Replace by the same record with the new flag
                    newRecord = Record(event.flagType,self.elements,record.elementsWithFlag)
                    self._changeRecord(record,newRecord)
            return
        
        elif isinstance(event,modify.events.ElementChangeEvent) and event.level == self.level:
            if isinstance(event,modify.events.FlagAddedEvent):
                record = self.getRecord(event.flag)
                if record is None:
                    # Traverse self.elements so that we don't have to copy
                    affected = [element for element in self.elements if element in event.getElements()]
                    if len(affected) > 0:
                        self._insertRecord(len(self.records),Record(event.flag,self.elements,affected))
                elif not record.isCommon(): # Nothing to do otherwise
                     newElementsWithFlag = [element for element in self.elements
                                    if element in event.getElements() or element in record.elementsWithFlag]
                     if len(newElementsWithFlag) > len(record.elementsWithFlag):
                         self._changeRecord(record,Record(record.flag,self.elements,newElementsWithFlag))
                return
            
            elif isinstance(event,modify.events.FlagRemovedEvent):
                record = self.getRecord(event.flag)
                if record is None:
                    return # Nothing to do
                remaining = [element for element in record.elementsWithFlag
                                if element not in event.elements]
                if len(remaining) == 0:
                    self._removeRecord(record)
                elif len(remaining) < len(record.elementsWithFlag):
                    self._changeRecord(record,Record(record.flag,self.elements,remaining))
                return
            
            elif event.flagsChanged:
                # General ElementChangeEvent
                if not any(element.id in event.ids() for element in self.elements):
                    return
                # Contrary to the detailed event handling above, we do a very simple thing here: We store the
                # flags in the elements and load them anew using createRecords.
                # If saveDirectly is False this destroys the original flags stored for the UndoCommand.
                # So make sure to use a flageditor either with saveDirectly or as a dialog.
                for element in self.elements:
                    if element.id in event.ids():
                        # No need to copy because the flags will be deleted in createRecords in a moment.
                        element.flags = event.getFlags(element.id)
                    else: element.flags = self.getFlagsOfElement(element)
                self.createRecords()

    def _handleTitlesChanged(self,affected):
        ownAffected = [] # Our copies of the affected elements
        for affectedElement in affected:
            for i,element in enumerate(self.elements):
                if element.id == affectedElement.id:
                    element.title = affectedElement.title
                    ownAffected.append(element)
                    break
        self.titlesChanged.emit(ownAffected)

                
class FlagEditorUndoCommand(QtGui.QUndoCommand):
    """UndoCommand used by the FlagEditorModel. It stores one of the methods of the model and some arguments.
    On redo this method will be called with the arguments. When creating the command it will calculate the
    inverse method and the necessary arguments and on undo that method is called.
    
    If the model saves its changes directly to the database or the editor (i.e. the tageditor is not running
    as a dialog) redo and undo will not only change the model but also call the correct modify-methods
    (on REAL-level) or emit the correct events (on EDITOR-level).
    
    Constructor parameters:
    
        - *model*: the FlagEditorModel
        - *method*: one of the methods of the model
        - *params*: arguments to be passed to *method*
        - text: a text for the UndoCommand (confer QtGui.QUndoCommand).
        
    \ """
    def __init__(self,model,method,*params,text=None):
        super().__init__(text)
        self.model = model
        self.method = method
        self.params = params
        self.level = model.level
        if method.__name__ == '_insertRecord':
            pos,record = params
            self.undoMethod = model._removeRecord
            self.undoParams = [record]
        elif method.__name__ == '_removeRecord':
            record = params[0]
            pos = model.records.index(record)
            self.undoMethod = model._insertRecord
            self.undoParams = [pos,record]
        elif method.__name__ == '_changeRecord':
            oldRecord,newRecord = params
            self.undoMethod = model._changeRecord
            self.undoParams = [newRecord,oldRecord]
            
    def redo(self):
        # First modify the model
        self.method(*self.params)
        # Then modify the editor or the database
        if self.model.saveDirectly:
            self._modify(True)
            
    def undo(self):
        self.undoMethod(*self.undoParams)
        if self.model.saveDirectly:
            self._modify(False)
         
    def _modify(self,redo):
        """Redo this command or undo it, depending on the parameter *redo*."""
        if self.method.__name__ == '_insertRecord':
            pos,record = self.params
            self._execute('add' if redo else 'remove',record.flag,record.elementsWithFlag)
        elif self.method.__name__ == '_removeRecord':
            record = self.params[0] # 'record, = self.params' would work, too.
            self._execute('remove' if redo else 'add',record.flag,record.elementsWithFlag)
        elif self.method.__name__ == '_changeRecord':
            if redo:
                oldRecord,newRecord = self.params
            else: newRecord,oldRecord = self.params
        
            if oldRecord.flag != newRecord.flag:
                self._execute('remove',oldRecord.flag,oldRecord.elementsWithFlag)
                self._execute('add',newRecord.flag,newRecord.elementsWithFlag)
            else:
                oldElements = set(oldRecord.elementsWithFlag)
                newElements = set(newRecord.elementsWithFlag)
                removeList = list(oldElements - newElements)
                addList = list(newElements - oldElements)
                actions = []
                if len(removeList):
                    self._execute('remove',oldRecord.flag,removeList)
                if len(addList):
                    self._execute('add',newRecord.flag,addList)
                return actions
    
    def _execute(self,type,*params):
        """Depending on the level either emit a SingleFlagChangeEvent (EDITOR) or call a function from
        modify.real (REAL), which will emit an event after really changing things. *type* is one of 'add' or
        'remove' and determines which event or function should be used. *params* are the arguments of the
        event/function (corresponding event/function pairs share the same signature).
        """
        if self.model.level == modify.EDITOR:
            print([el.id for el in params[1]])
            theClass = {
                'add': modify.events.FlagAddedEvent,
                'remove': modify.events.FlagRemovedEvent
            }[type]
            modify.dispatcher.changes.emit(theClass(modify.EDITOR,*params))
        else:
            theFunction = {
                'add': modify.real.addFlag,
                'remove': modify.real.removeFlag
            }[type]
            theFunction(*params)
                    