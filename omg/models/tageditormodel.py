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

from omg import models, tags
from . import simplelistmodel

RATIO = 0.75
SEPARATORS = ('/', " / ", ' - ', ", ")

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
        return any(self.append(element) for element in elements)
            
    def removeElements(self,elements):
        for element in elements:
            self.elementsWithValue.remove(element)
            
    def __str__(self):
        return str(self.value)

        #~ return "{0} in {1}".format(self.value," - ".join(str(elem) for elem in self.elements))
        #~ return "{0} außer in {1}".format(self.value," - ".join(str(elem) for elem in self.exceptions))


class TagEditorModel(QtCore.QObject):
    tagChanged = QtCore.pyqtSignal(tags.Tag)
    tagRemoved = QtCore.pyqtSignal(tags.Tag)
    recordAdded = QtCore.pyqtSignal(Record)
    recordRemoved = QtCore.pyqtSignal(Record)
    recordChanged = QtCore.pyqtSignal(Record,Record)
    resetted = QtCore.pyqtSignal()
    
    def __init__(self,elements):
        QtCore.QObject.__init__(self)
        self.elements = elements
        self.createTags()
    
    def reset(self):
        self.createTags()
        self.resetted.emit()
        
    def createTags(self):
        self.tags = {}
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
    
    def getTags(self):
        return list(self.tags.keys())
        
    def getRecords(self,tag):
        return self.tags[tag]

    def changeTag(self,oldTag,newTag):
        if newTag not in self.tags:
            self.tags[newTag] = self.tags[oldTag]
            del self.tags[oldTag]
            for record in self.tags[newTag]:
                record.tag = newTag
            self.tagChanged.emit(oldTag,newTag)
        else:
            # This is a bit more tricky: We have to insert all records of oldTag to the already existing records in newTag
            oldRecords = self.tags[oldTag]
            del self.tags[oldTag]
            self.tagRemoved.emit(oldTag)
            for oldRecord in oldRecords:
                newRecord = self.getRecord(newTag,oldRecord.value)
                if newRecord is None:
                    oldRecord.tag = newTag
                    self.tags[newTag].append(oldRecord)
                    self.recordAdded.emit(oldRecord)
                else:
                    copy = newRecord.copy()
                    if newRecord.extend(oldRecord.elementsWithValue):
                        self.recordChanged.emit(copy,newRecord)
    
    def removeTag(self,tag):
        del self.tags[tag]
        self.tagRemoved.emit(tag)
    
    def getRecord(self,tag,value):
        for record in self.tags[tag]:
            if record.value == value:
                return record
        return None
    
    def addRecord(self,record):
        if record.tag not in self.tags:
            self.tags[record.tag] = []
        existingRecord = self.getRecord(record.tag,record.value)
        if existingRecord is None:
            self.tags[record.tag].append(record)
            self.recordAdded.emit(record)
        else:
            copy = existingRecord.copy()
            copy.extend(record.elementsWithValue)
            self.recordChanged.emit(existingRecord,copy)
    
    def insertRecord(self,index,record):
        if record.tag not in self.tags:
            if index != 0:
                raise IndexError()
            self.tags[record.tag] = []
        existingRecord = self.getRecord(record.tag,record.value)
        if existingRecord is None:
            self.tags[record.tag].insert(index,record)
            self.recordAdded.emit(record)
            return True
        else:
            copy = existingRecord.copy()
            copy.extend(record.elementsWithValue)
            self.recordChanged.emit(existingRecord,copy)
            return False

    def changeRecord(self,oldRecord,newRecord):
        if oldRecord.tag == newRecord.tag:
            # Do not allow double tag values
            if newRecord.value not in [record.value for record in self.tags[oldRecord.tag]]:
                index = self.tags[oldRecord.tag].index(oldRecord)
                self.tags[oldRecord.tag][index] = newRecord
                self.recordChanged.emit(oldRecord,newRecord)
        else:
            self.removeRecord(oldRecord)
            self.addRecord(newRecord)

    def removeRecord(self,record):
        for i in range(len(self.tags[record.tag])):
            if self.tags[record.tag][i].value == record.value:
                del self.tags[record.tag][i]
                if len(self.tags[record.tag]) == 0:
                    self.removeTag(record.tag)
                else: self.recordRemoved.emit(record)
                return
        raise ValueError("There is no record with tag {} and value '{}'".format(record.tag,record.value))
    
    def getPossibleSeparators(self,records):
        # Collect all separators appearing in the first record
        if len(records) == 0 or any(record.tag.type == 'date' for record in records):
            return []
        result = [s for s in SEPARATORS if s in records[0].value]
        for record in records[1:]:
            if len(result) == 0:
                break
            # Filter those that do not appear in the other records
            result = list(filter(lambda s: s in record.value,result))
        return result
        
    def split(self,record,separator):
        for i in range(len(self.tags[record.tag])):
            if self.tags[record.tag][i] == record:
                # Do not allow double tag values for the first value (later values will be inserted via insertRecord which checks uniqueness itself)
                existingValues = [r.value for r in self.tags[record.tag]]
                splittedValues = list(itertools.dropwhile(lambda x: x in existingValues,record.value.split(separator)))
                if len(splittedValues) > 1: # Split was successful
                    # An easier solution would be to remove record and insert new records for all values in splittedValues. But if there is no other record with record.tag, the tag will be deleted and the new values would appear at the end of the WidgetList.
                    copy = record.copy()
                    copy.value = splittedValues.pop(0)
                    self.tags[record.tag][i] = copy
                    self.recordChanged.emit(record,copy)
                    # Values will all be inserted at the same position. Inserting them in reverse order guarantees that the order is correct in the end.
                    splittedValues.reverse() 
                    for value in splittedValues:
                        newRecord = Record(record.tag,value,record.allElements,record.elementsWithValue)
                        self.insertRecord(i+1,newRecord)
                    return True
                return False
        raise ValueError("Record is not contained in this model. Tag: {} Value: '{}'".format(record.tag,record.value))

    def splitMany(self,records,separator):
        return any(self.split(record,separator) for record in records)
