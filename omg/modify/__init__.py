#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer, Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import tags, logging, database as db
from . import events
# At the end of the file we will import the submodules real and events.

translate = QtCore.QCoreApplication.translate

logger = logging.getLogger(__name__)

# Levels
REAL = 1
EDITOR = 2

# Type of a change
ADDED,CHANGED,DELETED = range(1,4)
    
            
         
def _debugAll(event):
    logger.debug("EVENT: " + str(event))

    
class ChangeEventDispatcher(QtCore.QObject):
    
    changes = QtCore.pyqtSignal(events.ChangeEvent)
    
    def __init__(self):
        QtCore.QObject.__init__(self)


dispatcher = ChangeEventDispatcher()
dispatcher.changes.connect(_debugAll)


def commitEditors():
    logger.debug('creating commit command')
    command = commands.CommitCommand()
    logger.debug('created commit command. Pushing...')
    try:
        push(command)
    except StackChangeRejectedException:
        pass
             
    
def merge(level, parent, indices, newTitle, removeString, adjustPositions):
    """Merge creates a new container between *parent* and the children at the given *indices*.
    Those child elements will be removed from *parent* and instead inserted as children of
    the new container at indices[0]. The new container will contain all tags that are equal in
    all of its new children; its TITLE tag will be set to *newTitle*.
    
    removeString defines what to remove from the titles of the elements that are moved below the
    new container; this will usually be similar to *newTitle* plus possibly some punctutaion.
    If *adjustPositions* is True, the positions of items that are *not* removed are decreased
    to fill the gaps arising from moved elements.
    Example: Consider the following setting of an album containing a Sonata: 
    
    * parent
    |- pos1: child0 (title = Sonata Nr. 5: Allegro)
    |- pos2: child1 (tilte = Sonata Nr. 5: Adagio)
    |- pos3: child2 (title = Sonata Nr. 5: Finale. Presto)
    |- pos4: child3 (title = Nocturne Op. 13/37)
    |- pos5: child4 (title = Prelude BWV 42)
    
    After a call to merge with *indices=(0,1,2)*, *newTitle='Sonata Nr. 5'*, *removeString='Sonata Nr. 5: '*,
    *adjustPositions = True* the layout would be:
    
    * parent
    |- * pos1: new container (title = Sonata Nr. 5)
       |- pos1: child0 (title = Allegro)
       |- pos2: child1 (title = Adagio)
       |- pos3: child2 (title = Finale. Presto)
    |- pos2: child3 (title = Nocturne Op. 13/37)
    |- pos3: child4 (title = Prelude BWV 42)
    """ 
    from ..models import Container
    if level == REAL:
        raise NotImplementedError('Maddin, tu was!')
    if stack.state() == REAL:
        stack.setActiveStack(stack.editorStack)

    beginMacro(EDITOR, translate('modify', 'merge elements'))
    
    insertIndex = indices[0]
    insertPosition = parent.contents[insertIndex].position
    newChildren = []
    toRemove = []    
    positionChanges = []
    
    for i, element in enumerate(parent.contents[insertIndex:], start = insertIndex):
        if i in indices:
            currentPosition = element.position
            copy = parent.contents[i].copy()
            if tags.TITLE in copy.tags:
                copy.tags[tags.TITLE] = [ t.replace(removeString, '') for t in copy.tags[tags.TITLE] ]
            copy.position = len(newChildren) + 1
            newChildren.append(copy)
            toRemove.append(parent.contents[i])
        elif adjustPositions:
            positionChanges.append( (element.position, element.position - len(newChildren) + 1) )
    push(commands.RemoveElementsCommand(EDITOR, toRemove))
    push(commands.PositionChangeCommand(EDITOR, parent.id, positionChanges))
    t = tags.findCommonTags(newChildren, True)
    t[tags.TITLE] = [newTitle]
    newContainer = Container(id = newEditorId(),
                             contents = newChildren,
                             tags = t,
                             flags = None,
                             major = False,
                             position = insertPosition)
    insertions = { parent.id : [(insertIndex, [newContainer])] }
    push(commands.InsertElementsCommand(EDITOR, insertions))
    endMacro()
    

_currentEditorId = 0
_fileEditorIds = {}
# TODO: Liste wieder leeren?

def editorIdForPath(path):
    global _fileEditorIds
    if path not in _fileEditorIds:
        _fileEditorIds[path] = newEditorId()
    return _fileEditorIds[path]

def newEditorId():
    global _currentEditorId
    _currentEditorId -= 1
    return _currentEditorId

class StackChangeRejectedException(Exception):
    pass

class UndoGroup(QtGui.QUndoGroup):
    def __init__(self, parent = None):
        QtGui.QUndoGroup.__init__(self, parent)
        
        self.mainStack = QtGui.QUndoStack()
        
        self.addStack(self.mainStack)
        self.editorStack = None
        
        self._createEditorStack()
        self.setActiveStack(self.mainStack)
       
    def state(self):
        if self.activeStack() is self.editorStack:
            return EDITOR
        else:
            return REAL

    def setState(self, level):
        if level == REAL and self.state() == EDITOR:
            from ..gui.dialogs import question
            if not question('warning', 'you are about to switch from editor to real stack. The \
editor command history will be lost. Continue?'):
                raise StackChangeRejectedException()
            self.editorStack.clear()
        self.setActiveStack(self.mainStack if level == REAL else self.editorStack)
            
    def _createEditorStack(self):
        if self.editorStack is not None:
            self.removeStack(self.editorStack)
        self.editorStack = QtGui.QUndoStack()
        self.addStack(self.editorStack)
    
stack = UndoGroup()

def beginMacro(level,name):
    stack.setState(level)
    stack.activeStack().beginMacro(name)

def endMacro():
    stack.activeStack().endMacro()

def push(command):
    stack.setState(command.level)
    stack.activeStack().push(command)

def createUndoAction(level,parent,prefix):
    if level == REAL:
        return stack.mainStack.createUndoAction(parent,prefix)
    else: return stack.editorStack.createUndoAction(parent,prefix)

def createRedoAction(level,parent,prefix):
    if level == REAL:
        return stack.mainStack.createRedoAction(parent,prefix)
    else: return stack.editorStack.createRedoAction(parent,prefix)


# This is simply so that other modules can use modify.real.<stuff>
from . import real
