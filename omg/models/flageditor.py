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


class Record:
    def __init__(self,flag,allElements,elementsWithValue):
        self.flag = flag
        self.allElements = allElements
        self.elementsWithValue = elementsWithValue


class FlagEditorModel(QtCore.QObject):    
    resetted = QtCore.pyqtSignal()
    
    def __init__(self,level,elements,saveDirectly):
        QtCore.QObject.__init__(self)
        
        self.level = level
        self.saveDirectly = saveDirectly
        self.elements = [element.copy(contents=[],copyTags=False) for element in elements]
        
        self.createRecords()
        
    def setElements(self,elements):
        """Set the list of edited elements and reset the flageditor."""
        self.elements = [element.copy(contents=[],copyTags=False) for element in elements]
        self.reset()
        
    def createRecords(self):
        self.records = []
        for element in self.elements:
            for flag in element.flags:
                existingRecord = self.getRecord(flag)
                if existingRecord is None:
                    self.records.append(Record(flag,self.elements,[element]))
                else: existingRecord.elementsWithValue.append(element)
        
    def getRecord(self,flag):
        for record in self.records:
            if record.flag == flag:
                return record
        return None 
        
    def reset(self):
        """Reset the flageditor."""
        self.createRecords()
        self.resetted.emit()