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
from . import events, commands
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
          

def changePosition(level, element, position):
    elemOld = element.copy()
    elemNew = element.copy()
    elemNew.position = position
    
    stack.activeStack().push(ModifySingleElementCommand(level, elemOld, elemNew, translate('modify', 'change position'))) # TODO: richtigen Stack auswählen        
    
def merge(level, parent, positions, newTitle, removeString, adjustPositions):
    from ..models import Container
    if level == REAL:
        raise NotImplementedError('Maddin, tu was!')
    if stack.state() == REAL:
        stack.setActiveStack(stack.editorStack)

    beginMacro(EDITOR, translate('modify', 'merge elements'))
    copies = []
    insertPosition = positions[0]
    insertElementPosition = parent.contents[insertPosition].position
    removeCommand = RemoveElementsCommand(EDITOR, [parent.contents[i] for i in positions])
    
    for i,element in enumerate(parent.contents[insertPosition:], start=insertPosition):
        if i in positions:
            elemC = parent.contents[i].copy()
            copies.append(elemC)
            elemC.position = len(copies)
            if tags.TITLE in elemC.tags:
                elemC.tags[tags.TITLE] = [ t.replace(removeString, '') for t in elemC.tags[tags.TITLE] ]
            push(ModifySingleElementCommand(EDITOR, element, elemC))
        elif adjustPositions:
            changePosition(EDITOR, element, element.position - len(copies) + 1)
    push(removeCommand)        
    t = tags.findCommonTags(copies, True)
    t[tags.TITLE] = [newTitle]
    newContainer = Container(id = newEditorId(),
                             contents = copies,
                             tags = t,
                             flags = None,
                             position = insertElementPosition)
    insertions = { parent.id : [(insertPosition, [newContainer])] }
    push(InsertElementsCommand(EDITOR, insertions))
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
    
