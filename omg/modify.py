# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer, Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import database as db, tags


def changeContents(elid,oldContents,newContents):
    command = DBUndo

def DBUndoCommand(QtGui.QUndoCommand):
    def __init__(self,redoMethod,redoParams,undoMethod,undoParams):
        QtGui.QUndoCommand.__init__(self)
        self.redoMethod = redoMethod
        self.redoParams = redoParams
        self.undoMethod = undoMethod
        self.undoParams = undoParams
    
    def redo(self):
        self.redoMethod(*self.redoParams)
        
    def undo(self):
        self.undoMethod(*self.undoParams)


class ChangeEvent:
    level = REAL # REAL oder EDITOR
    contentsChanged = False # Haben sich auch die Contents geändert?
    
    # id -> geändertes Element. Falls der betroffene Knoten ein RootNode ist, ist id None. Depth first sortiert.
    changes = None


def changeTags(element,newTags):
    if not isinstance(newTags,tags.Storage):
        raise ValueError("newTags must be of type tags.Storage")
    undoCommand = 
    
class UndoCommand(QtGui.QUndoCommand):
    def __init__(self,parent = None):
        QtGui.QUndoCommand.__init__(self,parent)
    
class ChangeTagsCommand(QtGui.QUndoCommand):
    def __init__(self,elid,oldTags,newTags):
        self.elid = elid
        self.oldTags = oldTags.copy()
        self.newTags = newTags.copy()
                
    def redo(self):
        db.setTags(self.elid,self.newTags)
        
    def undo(self):
        db.setTags(self.elid,self.oldTags)
        

class AddFileCommand(QtGui.QUndoCommand):
    def __init__(self,path,hash,length):
        self.data = (path,hash,time.strftime('%Y-%m-%d %H:%M:%S'),length)
    
    def redo(self):
        self.id = db.addFile(*self.data)
    
    def undo(self):
        db.removeFile(self.id)
    

class RemoveFileCommand(QtGui.QUndoCommand):
    def __init__(self,id,data = None):
        self.id = id
        if data is not None:
            self.data = list(db.query("""
                SELECT path,hash,DATE_FORMAT(verified,''%Y-%m-%d %H:%i:%s'),length
                FROM files
                WHERE id = ?
                """,self.id).getSingleRow())
        else: self.data = data
    
    def redo(self):
        db.removeFile(self.id)
        
    def undo(self):
        db.addFile(*self.data)
        
        
  level =  # REAL oder EDITOR
  origin = # Die Komponente, in der die Änderung passiert ist
  before = # Kopie des betroffenen Elements vor der Änderung
  after =  # Kopie des betroffenen Elements nach der Änderung



def setTags(tagDict): # mapping elids to tags
    for id in tagDict:
    command = TagChangeCommand()
updateTags(elements)

addElements(elementData)
removeElements(elids)

addFiles(fileData)
removeFiles(elids)

setContents(elid,contents)
updateContents(elements)