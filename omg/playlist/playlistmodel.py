#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtCore
from omg import models, strutils
from . import forestmodel

class PlaylistModel(QtCore.QAbstractTableModel):
    def __init__(self,columns,elements=None):
        QtCore.QAbstractTableModel.__init__(self)
        self.columns = columns
        self.elements = elements if elements is not None else []
        
    def headerData(self,section,orientation,role = QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole or orientation != QtCore.Qt.Horizontal:
            return None
        if section > len(self.columns):
            return None
        return self.columns[section].getName()

    def getColumns(self):
        return self.columns
    
    def setColumns(self,columns):
        self.columns = columns
    
    def rowCount(self,parent=None):
        return len(self.elements)
        
    def columnCount(self,parent=None):
        return len(self.columns)
        
    def data(self,index,role=QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole:
            return None
        if index.row() >= self.rowCount() or index.column() >= self.columnCount():
            return None
        return self.elements[index.row()] # Data is the same for all columns. The delegate will display different values in different columns.
        
    def _handleFilesInserted(self,start,end):
        print("filesInserted: {0} {1}".format(start,end))
        self.elements[start:start] = self.syncPlaylist.get()[start:end+1]
        for element in self.elements[start:end+1]:
            element.ensureTagsAreLoaded()
        self.rowsInserted.emit(QtCore.QModelIndex(),start,end)
        
    def _handleFilesRemoved(self,start,end):
        print("filesRemoved: {0} {1}".format(start,end))
        del self.elements[start:end+1]
        self.rowsRemoved.emit(QtCore.QModelIndex(),start,end)
        
    def _handleReset(self):
        print("RESET")
        self.elements = self.syncPlaylist.get()[:]
        for element in self.elements:
            element.ensureTagsAreLoaded()
        self.modelReset.emit()

    def connectToSyncPlaylist(self,syncPlaylist):
        self.syncPlaylist = syncPlaylist
        syncPlaylist.filesInserted.connect(self._handleFilesInserted)
        syncPlaylist.filesRemoved.connect(self._handleFilesRemoved)
        syncPlaylist.listReset.connect(self._handleReset)
        
    def disconnectFromSyncPlaylist(self):
        self.syncPlaylist.filesInserted.disconnect(self._handleFilesInserted)
        self.syncPlaylist.filesRemoved.disconnect(self._handleFilesRemoved)
        self.syncPlaylist.listReset.disconnect(self._handleReset)
        self.syncPlaylist = None
    
    
class Column:
    def getName(self): pass
    def getData(self,container): pass
    
class TagColumn(Column):
    def __init__(self,tag):
        self.tag = tag
        
    def getName(self):
        return self.tag.name
    
    def getData(self,container):
        return ", ".join(str(value) for value in container.tags[self.tag])

class DataColumn(Column):
    types = {
        'title': "Titel",
        'length': "Länge",
        'path': "Pfad"
        }
        
    def __init__(self,type):
        assert type in self.types
        self.type = type
    
    def getName(self):
        return self.types[self.type]
    
    def getData(self,element):
        if self.type == 'title':
            return element.getTitle()
        elif self.type == 'length':
            length = element.getLength()
            if length is not None:
                return strutils.formatLength(element.getLength())
            else: return ""
        elif self.type == 'path':
            if element.isFile():
                return element.getPath()
            else: return ''
        assert False