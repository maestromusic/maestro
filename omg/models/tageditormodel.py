#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#
import itertools

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from omg import constants, models, tags, utils, strutils
from . import simplelistmodel

RATIO = 0.75

class Record:
    def __init__(self,tag,value,allElements,elementsWithValue):
        self.tag = tag
        self.value = value
        self.allElements = allElements
        self.elementsWithValue = elementsWithValue
    
    def copy(self):
        return Record(self.tag,self.value,self.allElements,self.elementsWithValue)
        
    def isCommon(self):
        return len(self.elementsWithValue) == len(self.allElements)
    
    def isUsual(self):
        return len(self.elementsWithValue) >= RATIO * len(self.allElements)
    
    def getExceptions(self):
        return [element for element in self.allElements if element not in self.elementsWithValue]
    
    def append(self,element):
        if element not in self.elementsWithValue:
            self.elementsWithValue.append(element)
            return True
        return False
    
    def extend(self,elements):
        # Take care that self.append is executed for all elements
        results = [self.append(element) for element in elements]
        return any(results)
            
    def removeElements(self,elements):
        for element in elements:
            self.elementsWithValue.remove(element)
            
    def __str__(self):
        if self.isCommon():
            return str(self.value)
        elif len(self.elementsWithValue) == 1:
            return "{} in {}".format(self.value,self.elementsWithValue[0])
        elif len(self.getExceptions()) == 1:
            return "{} außer in {}".format(self.value,self.getExceptions()[0])
        else: return "{} in {} Stücken".format(self.value,len(self.elementsWithValue))


class InnerModel(QtCore.QObject):
    tagInserted = QtCore.pyqtSignal(int,tags.Tag)
    tagRemoved = QtCore.pyqtSignal(tags.Tag)
    tagChanged = QtCore.pyqtSignal(tags.Tag,tags.Tag)
    recordInserted = QtCore.pyqtSignal(int,Record)
    recordRemoved = QtCore.pyqtSignal(Record)
    recordChanged = QtCore.pyqtSignal(tags.Tag,Record,Record)
    recordMoved = QtCore.pyqtSignal(tags.Tag,int,int)

    def __init__(self,elements):
        QtCore.QObject.__init__(self)
        self.elements = [element.copy(copyTags=False) for element in elements]
        self.createTags()

    def createTags(self):
        self.tags = utils.OrderedDict()
        for element in self.elements:
            for tag in element.tags:
                if not tag in self.tags:
                    self.tags[tag] = []
                recordList = self.tags[tag]
                for value in element.tags[tag]:
                    record = self.getRecord(tag,value)
                    if record is None:
                        # Create a new record
                        recordList.append(Record(tag,value,self.elements,[element]))
                    else: record.append(element)
    
    def getRecord(self,tag,value):
        if tag in self.tags:
            for record in self.tags[tag]:
                if record.value == value:
                    return record
        return None

    def insertRecord(self,pos,record):
        self.tags[record.tag].insert(pos,record)
        self.recordInserted.emit(pos,record)

    def removeRecord(self,record):
        pos = self.tags[record.tag].index(record)
        del self.tags[record.tag][pos]
        self.recordRemoved.emit(record)
            
    def changeRecord(self,tag,oldRecord,newRecord):
        pos = self.tags[tag].index(oldRecord)
        self.tags[tag][pos] = newRecord
        self.recordChanged.emit(tag,oldRecord,newRecord)

    def moveRecord(self,tag,oldPos,newPos):
        if oldPos != newPos:
            self.tags[tag].insert(newPos,self.tags[tag][oldPos])
            if oldPos < newPos:
                del self.tags[tag][oldPos]
            else: del self.tags[tag][oldPos + 1]
            self.recordMoved.emit(tag,oldPos,newPos)
            
    def insertTag(self,pos,tag):
        self.tags.insert(pos,tag,[])
        self.tagInserted.emit(pos,tag)

    def removeTag(self,tag):
        assert len(self.tags[tag]) == 0
        del self.tags[tag]
        self.tagRemoved.emit(tag)

    def changeTag(self,oldTag,newTag):
        self.tags.changeKey(oldTag,newTag)
        self.tagChanged.emit(oldTag,newTag)


class UndoCommand(QtGui.QUndoCommand):
    def __init__(self,model,method,*params,text=None):
        QtGui.QUndoCommand.__init__(self,text)
        self.model = model
        self.method = method
        self.params = params
        if method.__name__ == 'insertRecord':
            pos,record = params
            self.undoMethod = model.inner.removeRecord
            self.undoParams = [record]
        elif method.__name__ == 'removeRecord':
            record = params[0] # 'record, = params' would work, too.
            pos = model.inner.tags[record.tag].index(record)
            self.undoMethod = model.inner.insertRecord
            self.undoParams = [pos,record]
            
        elif method.__name__ == 'changeRecord':
            tag,oldRecord,newRecord = params
            self.undoMethod = model.inner.changeRecord
            self.undoParams = [tag,newRecord,oldRecord]
        elif method.__name__ == 'moveRecord':
            tag,oldPos,newPos = params
            self.undoMethod = model.inner.moveRecord
            self.undoParams = [tag,newPos,oldPos]
        elif method.__name__ == 'insertTag':
            pos,tag = params
            self.undoMethod = model.inner.removeTag
            self.undoParams = [tag]
        elif method.__name__ == 'removeTag':
            tag = params[0]
            pos = model.inner.tags.index(tag)
            self.undoMethod = model.inner.insertTag
            self.undoParams = [pos,tag]
        elif method.__name__ == 'changeTag':
            oldTag,newTag = params
            self.undoMethod = model.inner.changeTag
            self.undoParams = [newTag,oldTag]

    def redo(self):
        self.method(*self.params)

    def undo(self):
        self.undoMethod(*self.undoParams)


class TagEditorModel(QtCore.QObject):
    resetted = QtCore.pyqtSignal()
    commonChanged = QtCore.pyqtSignal(Record)
    
    def __init__(self,elements):
        QtCore.QObject.__init__(self)
        self.inner = InnerModel(elements)
        self.tagInserted = self.inner.tagInserted
        self.tagRemoved = self.inner.tagRemoved
        self.tagChanged = self.inner.tagChanged
        self.recordInserted = self.inner.recordInserted
        self.recordRemoved = self.inner.recordRemoved
        self.recordChanged = self.inner.recordChanged
        self.recordMoved = self.inner.recordMoved

        self.undoStack = QtGui.QUndoStack(self)

    def getTags(self):
        return list(self.inner.tags.keys())

    def getRecords(self,tag):
        return self.inner.tags[tag]

    def getElements(self):
        return self.inner.elements
    
    def setElements(self,elements):
        self.inner.elements = [element.copy(copyTags=False) for element in elements]
        self.reset()
        
    def reset(self):
        self.inner.createTags()
        self.undoStack.clear()
        self.resetted.emit()

    def addRecord(self,record):
        self.undoStack.beginMacro("Add Record")
        result = self._insertRecord(None,record)
        self.undoStack.endMacro()
        return result

    def _insertRecord(self,pos,record):
        if record.tag not in self.inner.tags:
            # Add the missing tag
            command = UndoCommand(self,self.inner.insertTag,len(self.inner.tags),record.tag)
            self.undoStack.push(command)

        # Does there already exist a record with the same tag and value?
        existingRecord = self.inner.getRecord(record.tag,record.value)
        if existingRecord is None:
            # Simply add the record
            if pos is None:
                if record.isCommon():
                    pos = self._commonCount(record.tag)
                else: pos = len(self.inner.tags[record.tag])
            else: assert pos <= len(self.inner.tags[record.tag])
            command = UndoCommand(self,self.inner.insertRecord,pos,record)
            self.undoStack.push(command)
            return True
        else:
            # Now things get complicated: Add the record's elements to those of (a copy of) the existing record
            copy = existingRecord.copy()
            copy.extend(record.elementsWithValue)
            command = UndoCommand(self,self.inner.changeRecord,record.tag,existingRecord,copy)
            self.undoStack.push(command)
            # Now here's a problem: If the changed record is common, whereas the old one is not, we have to keep the sorting (common records to the top).
            if existingRecord.isCommon() != copy.isCommon():
                # As we add elements, it must be this way:
                assert not existingRecord.isCommon() and copy.isCommon()
                pos = self.inner.tags[record.tag].index(existingRecord)
                newPos = self._commonCount(record.tag)
                if pos != newPos:
                    command = UndoCommand(self,self.inner.moveRecord,pos,newPos)
                    self.undoStack.push(command)
                self.commonChanged.emit(copy)
            return False
            
    def removeRecord(self,record):
        self.undoStack.beginMacro("Remove record")
        command = UndoCommand(self,self.inner.removeRecord,record)
        self.undoStack.push(command)
        if len(self.inner.tags[record.tag]) == 0:
            # Remove the empty tag
            command = UndoCommand(self,self.inner.removeTag,record.tag)
            self.undoStack.push(command)
        self.undoStack.endMacro()

    def removeRecords(self,records):
        if len(records) > 0:
            self.undoStack.beginMacro("Einträge entfernen" if len(records) > 1 else "Eintrag entfernen")
            for record in records:
                self.removeRecord(record)
            self.undoStack.endMacro()

    def changeRecord(self,oldRecord,newRecord):
        self.undoStack.beginMacro("Change record")

        # If the tag has changed or the new value does already exist, we simply remove the old and add the new record. Otherwise we really change the record so that its position stays the same because this is what the user expects.
        if oldRecord.tag != newRecord.tag or self.inner.getRecord(newRecord.tag,newRecord.value) is not None:
            self.removeRecord(oldRecord)
            self.addRecord(newRecord)
        else:
            # I am not sure, but the order of changing, moving end emitting commonChanged maybe important
            # Change the record
            command = UndoCommand(self,self.inner.changeRecord,oldRecord.tag,oldRecord,newRecord)
            self.undoStack.push(command)
            # Maybe we have to move the record as the common records are sorted to the top
            if oldRecord.isCommon() != newRecord.isCommon():
                pos = self.inner.tags[oldRecord.tag].index(oldRecord)
                newPos = self._commonCount(oldRecord.tag) # Move to the border
                if pos != newPos:
                    command = UndoCommand(self,self.inner.moveRecord,pos,newPos)
                    self.undoStack.push(command)
                self.commonChanged.emit(newRecord)
        self.undoStack.endMacro()

    def removeTag(self,tag):
        self.undoStack.beginMacro("Remove tag")
        # First remove all records
        for record in self.inner.tags[tag]:
            command = UndoCommand(self,self.inner.removeRecord,record)
            self.undoStack.push(command)
        # Remove the empty tag
        command = UndoCommand(self,self.inner.removeTag,record.tag)
        self.undoStack.push(command)
        self.undoStack.endMacro()

    def changeTag(self,oldTag,newTag):
        # First check whether the existing values in oldTag are convertible to newTag
        try:
            for record in self.inner.tags[oldTag]:
                oldTag.type.convertValue(newTag.type,record.value)
        except ValueError:
            return False # conversion not possible
        self.undoStack.beginMacro("Change Tag")

        if newTag not in self.inner.tags:
            # First change all records:
            for record in self.inner.tags[oldTag]:
                newRecord = record.copy()
                newRecord.tag = newTag
                newRecord.value = oldTag.type.convertValue(newTag.type,record.value)
                command = UndoCommand(self,self.inner.changeRecord,oldTag,record,newRecord)
                self.undoStack.push(command)
            # Finally change the tag itself
            command = UndoCommand(self,self.inner.changeTag,oldTag,newTag)
            self.undoStack.push(command)
        else: # Now we have to add all converted records to the existing tag
            # The easiest way to do this is to remove all records and add the converted records again
            for record in self.inner.tags[oldTag]:
                newRecord = record.copy()
                newRecord.tag = newTag
                newRecord.value = oldTag.type.convertValue(newTag.type,record.value)
                self.addRecord(newRecord)
            # Finally remove the old tag
            self.removeTag(oldTag)

        self.undoStack.endMacro()
            
        return True

    def save(self):
        # Remove the stored elements
        for element in self.inner.elements:
            element.oldTags = element.tags
            element.tags = tags.Storage()

        # And store the changed tags
        for tag,records in self.inner.tags.items():
            for record in records:
                for element in record.elementsWithValue:
                    element.tags.add(tag,record.value)

        for element in self.inner.elements:
            if element.isFile():
                element.writeToFileSystem(tags=True)
            
        # First remove values contained in the database, but not in self.inner.tags from the database.
        # AND remove values which are already contained in the database and in self.inner.tags (that is, those tag-values where nothing has changed) from self.inner.tags so that they won't be added to the db later.
        for tag in tags.tagList:
            for element in self.inner.elements:
                if not element.isInDB():
                    continue
                if tag not in element.oldTags:
                    continue
                for value in db.tagValues(element.id,tag):
                    record = self.inner.getRecord(tag,value)
                    if record is None or element not in record.elementsWithValue:
                        # The value is contained in the db, but not in self.inner.tags => remove it
                        db.removeTag(element.id,tag,value)
                    else:
                        # This value is already in the database, so there is no need to add it
                        record.elementsWithValue.remove(element)

        # In the second step add the tags which remained in self.tags to the database.
        for tag in self.inner.tags:
            # Ensure that the tag exists
            if not tag.isIndexed():
                tag = tags.addIndexedTag(tag.name,tag.type)
            for record in self.inner.tags[tag]:
                if len(record.elementsWithValue) > 0: # For unchanged tags this is []
                    db.addTag([element.id for element in record.elementsWithValue if element.isInDB()],tag,record.value)

        changedIds = [element.id for element in self.getElements() if element.isInDB()] #TODO: This is not very accurate...
        if len(changedIds) > 0:
            distributor.indicesChanged.emit(distributor.DatabaseChangeNotice(changedIds,tags=True))
        
    def getPossibleSeparators(self,records):
        # Collect all separators appearing in the first record
        if len(records) == 0 or any(record.tag.type == tags.TYPE_DATE for record in records):
            return []
        result = [s for s in constants.SEPARATORS if s in records[0].value]
        for record in records[1:]:
            if len(result) == 0:
                break
            # Filter those that do not appear in the other records
            result = list(filter(lambda s: s in record.value,result))
        return result
        
    def split(self,record,separator):
        splittedValues = record.value.split(separator)
        if len(splittedValues) == 0:
            return True # Nothing to split...thus the split was successful :-)
        if not all(record.tag.isValid(value) for value in splittedValues):
            return False
            
        # Now here starts the split
        pos = self.inner.tags[record.tag].index(record)
        self.undoStack.beginMacro("Split")
        # First remove the old value
        command = UndoCommand(self,self.inner.removeRecord,record)
        self.undoStack.push(command)
        # Now create new records and insert them at pos
        for value in splittedValues:
            newRecord = record.copy()
            newRecord.value = value
            if self._insertRecord(pos,newRecord): # This is false if the record was added to an already existing one
                pos = pos + 1
        self.undoStack.endMacro()
        return True

    def splitMany(self,records,separator):
        return any(self.split(record,separator) for record in records)

    def editMany(self,records,newValues):
        self.undoStack.beginMacro("Edit many")
        for record, value in zip(records,newValues):
            newRecord = record.copy()
            newRecord.value = value
            command = UndoCommand(self,self.inner.changeRecord,record.tag,record,newRecord)
            self.undoStack.push(command)
        self.undoStack.endMacro()

    def extendRecords(self,records):
        self.undoStack.beginMacro("Extend records")
        for record in records:
            newRecord = record.copy()
            newRecord.elementsWithValue = self.inner.elements[:] # copy the list!
            command = UndoCommand(self,self.inner.changeRecord,record.tag,record,newRecord)
            self.undoStack.push(command)
        self.undoStack.endMacro()

    def _commonCount(self,tag):
        c = 0
        for record in self.inner.tags[tag]:
            if record.isCommon():
                c = c + 1
            else: break
        return c
