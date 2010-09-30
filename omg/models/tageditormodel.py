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
    
    def __str__(self):
        return str(self.value)

        #~ return "{0} in {1}".format(self.value," - ".join(str(elem) for elem in self.elements))
        #~ return "{0} außer in {1}".format(self.value," - ".join(str(elem) for elem in self.exceptions))


class TagEditorModel(QtCore.QObject):
    recordAdded = QtCore.pyqtSignal(Record)
    recordRemoved = QtCore.pyqtSignal(Record)
    recordChanged = QtCore.pyqtSignal(Record,Record)
    tagRemoved = QtCore.pyqtSignal(tags.Tag)
    resetted = QtCore.pyqtSignal()
    
    def __init__(self,elements):
        QtCore.QObject.__init__(self)
        self.elements = [element.copy() for element in elements]
        self.oldElements = elements
    
    def reset(self):
        self.elements = [element.copy() for element in self.oldElements]
        self.resetted.emit()
        
    def getTags(self):
        tags = []
        for tag in itertools.chain.from_iterable(element.tags.keys() for element in self.elements):
            if tag not in tags:
                tags.append(tag)
        return tags
        
    def getTagValues(self,tag):
        tagValues = {}
        for element in self.elements:
            if tag in element.tags:
                for value in element.tags[tag]:
                    if value not in tagValues:
                        tagValues[value] = []
                tagValues[value].append(element)
        return tagValues
        
    def getRecords(self,tag):
        return [Record(tag,value,self.elements,elementsWithValue)
                        for value,elementsWithValue in self.getTagValues(tag).items()]

    def addRecord(self,record):
        for element in record.elementsWithValue:
            element.tags.addUnique(record.tag,record.value)
        self.recordAdded.emit(record)
    
    def addRecords(self,records):
        for record in records:
            self.addRecord(record)
            
    def changeRecord(self,oldRecord,newRecord):
        for element in oldRecord.elementsWithValue:
            element.tags.removeValues(oldRecord.tag,oldRecord.value)
        for element in newRecord.elementsWithValue:
            element.tags.addUnique(newRecord.tag,newRecord.value)
        self.recordChanged.emit(oldRecord,newRecord)
            
    def removeRecord(self,record):
        for element in record.elementsWithValue:
            element.tags.removeValues(record.tag,record.value)
        self.recordRemoved.emit(record)
                

class TagListModel(simplelistmodel.SimpleListModel):
    def __init__(self,editorModel,tag):
        simplelistmodel.SimpleListModel.__init__(self)
        self.setEditable(True)
        self.editorModel = editorModel
        self.tag = tag
        elements = editorModel.elements
        self.records = self.items # Just an alias
        if len(elements) > 0:
            seenValues = []
            for value in itertools.chain.from_iterable(element.tags[tag] for element in elements):
                if value not in seenValues:
                    seenValues.append(value)
                    elementsWithThisValue = [element for element in elements if value in element.tags[tag]]
                    self.records.extend(Record(tag,value,elements,elementsWithThisValue))
    
    def addRecords(self,records):
        self.beginInsertRows(QtCore.QModelIndex(),len(self.records),len(self.records)+len(records)-1)
        self.records.extend(records)
        #  TODO: Sort
        self.endInsertRows()