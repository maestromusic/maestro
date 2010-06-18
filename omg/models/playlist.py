#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import difflib

from omg import database
from . import rootedtreemodel, treebuilder, Element

db = database.get()

class PlaylistElement(Element):
    def __init__(self,id,contents):
        Element.__init__(self,id)
        self.length = None
        self.position = None
        self.contents = contents
    
    def getPosition(self):
        if self.parent is None or isinstance(self.parent,RootNode): # Without parent, there can't be a position
            return None
        if self.position is None:
            self.position = db.query("SELECT position FROM contents WHERE container_id = ? AND element_id = ?", 
                                     self.parent.id,self.id).getSingle()
        return self.position
    
    def getLength(self):
        if self.length is None:
            self.length = Element.getLength(self)
        return self.length
        
        
class Playlist(rootedtreemodel.RootedTreeModel):
    pathList = None
    toplevelElements = None
    
    _treeBuilder = None
    
    def __init__(self):
        rootedtreemodel.RootedTreeModel.__init__(self,RootNode(self))
        self.toplevelElements = []
        self._treeBuilder = treebuilder.TreeBuilder(self._getId,self._getParentIds,self._createNode)
        
    def startSynchronization(self):
        self.pathList = [file.getPath() for file in self.root.getAllFiles()]
    
    def stopSynchronization(self):
        self.pathList = None
    
    def _getFilteredOpcodes(self,a,b):
        opCodes = difflib.SequenceMatcher(None,a,b).get_opcodes()
        offset = 0
        for tag,i1,i2,j1,j2 in opCodes:
            if tag == 'equal':
                continue
            elif tag == 'delete':
                yield (tag,i1+offset,i2+offset,-1,-1)
                offset = offset - i2 + i1
            elif tag == 'insert':
                yield (tag,i1+offset,i2+offset,j1,j2)
                offset == offset + j2 - j1
            elif tag == 'replace':
                yield ('delete',i1+offset,i2+offset,-1,-1)
                offset = offset - i2 + i1
                yield (tag,i1+offset,i2+offset,j1,j2)
                offset == offset + j2 - j1
            else: raise ValueError("Opcode tag {0} is not supported.".format(tag))
                        
    def synchronize(self,pathList):
        if len(pathList) == 0 and len(self.toplevelElements) > 0:
            self.toplevelElements = []
            self.reset()
        else:
            for tag,j1,j2,i1,i2 in self._getFilteredOpcodes(self.pathList,pathList):
                #~ if tag == 'delete':  # TODO
                #~ elif tag == 'insert' # TODO
                self.toplevelElements = self._treeBuilder.build([self._createItem(path) for path in pathList])
                for element in self.toplevelElements:
                    element.parent = self.root
                self.pathList = pathList
                self.reset()
                break
    
    def _createItem(self,path):
        id = db.query("SELECT container_id FROM files WHERE path = ?",path).getSingle()
        if id is None:
            return ExternalFile(path)
        else: return PlaylistElement(id,[])
    
    def _getId(self,item):
        if isinstance(item,ExternalFile):
            return None
        else: return item.id
        
    def _getParentIds(self,id):
        return [id for id in db.query("SELECT container_id FROM contents WHERE element_id = ?",id).getSingleColumn()]
               
    def _createNode(self,id,children):
        newElement = PlaylistElement(id,children)
        for element in children:
            element.parent = newElement
        return newElement


class ExternalFile:
    def __init__(self,path,parent = None):
        self.path = path
        self.parent = parent
    
    def isFile(self):
        return True
        
    def getParent(self):
        return self.parent
        
    def getPath(self):
        return self.path
    
    def hasChildren(self):
        return False
        

class RootNode:
    def __init__(self,model):
        self.model = model
    
    def hasChildren(self):
        return len(self.model.toplevelElements) > 0
        
    def getChildren(self):
        return self.model.toplevelElements
    
    def getChildrenCount(self):
        return len(self.model.toplevelElements)
    
    def getParent(self):
        return None
    
    def getAllFiles(self):
        for child in self.model.toplevelElements:
            for file in child.getAllFiles():
                yield file