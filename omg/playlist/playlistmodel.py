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

class ContainerNode(models.Container):
    def __init__(self,param,position=None,parent=None):
        if isinstance(param,int):
            models.Container.__init__(self,param)
        else:
            assert isinstance(param,models.Container)
            models.Container.__init__(self,param.id)
            self.elements = param.elements
            self.tags = param.tags
        if self.elements is None:
            self.loadElements(True)
        if self.tags is None:
            self.loadTags(True)
        self.position = position
        self.parent = parent
    
    # Methods for ForestModel
    def hasChildren(self):
        return len(self.elements) > 0
        
    def getElementsCount(self):
        return len(self.elements)
        
    def getElements(self):
        return self.elements

    def getParent(self):
        return self.parent

    def getPosition(self):
        return self.position
        
    def getPath(self):
        try:
            return self.path
        except AttributeError:
            self.path = models.Container.getPath(self)
            return self.path
        
    def getLength(self):
        try:
            return self.length
        except AttributeError:
            self.length = models.Container.getLength(self)
            return self.length
            
            
class PlaylistModel(forestmodel.ForestModel):
    def __init__(self,columns,roots=None):
        forestmodel.ForestModel.__init__(self,len(columns),roots)
        self.columns = columns
        
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
        forestmodel.ForestModel.setColumnCount(len(columns))
    
    def addNode(self,node):
        elementList = node.retrieveElementList()
        self.model.setRoots([playlistmodel.ContainerNode(element) for element in elementList])


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
    def __init__(self,type):
        self.type = type
    
    def getName(self):
        if self.type == 'title':
            return "Titel"
        elif self.type == 'length':
            return "Länge"
        elif self.type == 'path':
            return "Pfad"
        assert False
    
    def getData(self,container):
        if self.type == 'title':
            if container.getPosition() is not None:
                return "{0} - {1}".format(position,container.getTitle())
            else: return container.getTitle()
        elif self.type == 'length':
            return strutils.formatLength(container.getLength())
        elif self.type == 'path':
            if container.isFile():
                return container.getPath()
            else: return ''
        assert False