#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt


from .. import modify


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
    """The model of the FlagEditor. It stores a list of records containing a flag and a list of elements that
    have this flag and allows to edit this list.
    
        - level: whether changes in this model affect the database or the editor
        - elements: a list of elements whose flags will be displayed and editey by this model
        - saveDirectly: whether changes in the model are applied directly.
        - undoStack: the UndoStack that should be used if saveDirectly is False.
        
    \ """
    resetted = QtCore.pyqtSignal()
    recordInserted = QtCore.pyqtSignal(int,Record)
    recordRemoved = QtCore.pyqtSignal(Record)
    recordChanged = QtCore.pyqtSignal(Record,Record)
    
    def __init__(self,level,elements,saveDirectly,undoStack=None):
        super().__init__()
        
        self.level = level
        self.saveDirectly = saveDirectly
        self.elements = [element.copy(contents=[],copyTags=False) for element in elements]
        self.undoStack = undoStack
        
        self.createRecords()
        
    def setElements(self,elements):
        """Set the list of edited elements and reset the model."""
        self.elements = [element.copy(contents=[],copyTags=False) for element in elements]
        self.reset()
        
    def createRecords(self):
        """Create records reading the flags from self.elements."""
        self.records = []
        for element in self.elements:
            for flag in element.flags:
                existingRecord = self.getRecord(flag)
                if existingRecord is None:
                    self.records.append(Record(flag,self.elements,[element]))
                else: existingRecord.elementsWithFlag.append(element)
        
    def getRecord(self,flag):
        """Get the record for the given flag or None if there is no record for this flag."""
        for record in self.records:
            if record.flag == flag:
                return record
        return None 
        
    def reset(self):
        """Reset the model creating new records from the elements."""
        self.createRecords()
        self.resetted.emit()
        
    def isEmpty(self):
        """Return whether there is at least one record/flag in one of the elements governed by this model."""
        return len(self.records) == 0
    
    def addFlag(self,flag,elementsWithFlag = None):
        """Add a flag to the elements contained in *elementsWithFlag* or all elements if that parameter is
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
        """Change *oldRecord* into *newRecord*."""
        assert len(newRecord.elementsWithFlag) > 0
        command = FlagEditorUndoCommand(self,self._changeRecord,oldRecord,newRecord,
                                        text=self.tr("Change flag record"))
        self._push(command)
    
    # The next three methods are called by FlagEditorUndoCommand
    def _insertRecord(self,pos,record):
        """Really insert a record at the given position. This model may only be called by an UndoCommand."""
        self.records.insert(pos,record)
        self.recordInserted.emit(pos,record)
    
    def _removeRecord(self,record):
        """Really remove a record. This model may only be called by an UndoCommand."""
        self.records.remove(record)
        self.recordRemoved.emit(record)

    def _changeRecord(self,oldRecord,newRecord):
        """Really change *oldRecord* into *newRecord*. This model may only be called by an UndoCommand."""
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
    
    def save(self):
        """Save flags as stored in the internal records to the database and emit a change event."""
        if self.saveDirectly:
            raise RuntimeError("You must not call save in a FlagEditorModel that saves directly.")
            
        changes = {element: (element.flags,self.getFlagsOfElement(element))
                        for element in self.elements}
        
        self._push(modify.commands.FlagUndoCommand(self.level,changes,text=self.tr("Change flags")))


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
    def __init__(self,model,method,*params,text=None,level=modify.REAL):
        super().__init__(text)
        self.model = model
        self.method = method
        self.params = params
        self.level = level
        if method.__name__ == '_insertRecord':
            pos,record = params
            self.undoMethod = model._removeRecord
            self.undoParams = [record]
        elif method.__name__ == '_removeRecord':
            record = params[0] # 'record, = params' would work, too.
            pos = model.records.index(record)
            self.undoMethod = model._insertRecord
            self.undoParams = [pos,record]
        elif method.__name__ == '_changeRecord':
            oldRecord,newRecord = params
            self.undoMethod = model._changeRecord
            self.undoParams = [newRecord,oldRecord]
            
    def redo(self):
        # First modify the inner model
        self.method(*self.params)
        # Then modify the editor or the database
        if self.model.saveDirectly:
            self._modify(True)
            
    def undo(self):
        # First modify the inner model
        self.undoMethod(*self.undoParams)
        # Then modify the editor or the database
        if self.model.saveDirectly:
            self._modify(False)
         
    def _getActions(self,redo):
        """Return a list of actions that are necessary to perform the change of this UndoCommand outside of
        the flageditor (i.e. database or editor). Each action is a tuple consisting of a type ('add' or
        'remove') and one or more arguments (confer _modify).
        
        If *redo* is true the actions will redo this command otherwise they will undo it.
        """
        if self.method.__name__ == '_insertRecord':
            pos,record = self.params
            action = ('add' if redo else 'remove',record.flag,record.elementsWithFlag)
            return [action]
        elif self.method.__name__ == '_removeRecord':
            record = self.params[0] # 'record, = self.params' would work, too.
            action = ('remove' if redo else 'add',record.flag,record.elementsWithFlag)
            return [action]
        elif self.method.__name__ == '_changeRecord':
            if redo:
                oldRecord,newRecord = self.params
            else: newRecord,oldRecord = self.params
        
            if oldRecord.flag != newRecord.flag:
                return [
                    ('remove',oldRecord.flag,oldRecord.elementsWithFlag),
                    ('add',   newRecord.flag,newRecord.elementsWithFlag)
                  ]
            else:
                oldElements = set(oldRecord.elementsWithFlag)
                newElements = set(newRecord.elementsWithFlag)
                removeList = list(oldElements - newElements)
                addList = list(newElements - oldElements)
                actions = []
                if len(removeList):
                    actions.append(('remove',oldRecord.flag,removeList))
                if len(addList):
                    actions.append(('add',newRecord.flag,addList))
                return actions
           
    def _modify(self,redo):
        """This method changes things outside of the flageditor (database or editor). It will fetch a list of
        actions from _getActions and either call corresponding methods from modify.db (level = REAL) or emit
        the corresponding events (level=editor).
        
        If *redo* is true the method will redo this command otherwise it will undo it.
        """
        actions = self._getActions(redo)
        if self.model.level == modify.EDITOR:
            for action in actions:
                if action[0] == 'add':
                    event = modify.events.FlagAddedEvent(modify.EDITOR,*action[1:])
                elif action[0] == 'remove':
                    event = modify.events.FlagRemovedEvent(modify.EDITOR,*action[1:])
        else: # level == REAL
            for action in actions:
                if action[0] == 'add':
                    modify.real.addFlag(*action[1:])
                elif action[0] == 'remove':
                    modify.real.removeFlag(*action[1:])
                    