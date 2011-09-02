#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer, Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#

import copy, itertools
from collections import OrderedDict

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import tags, logging, database as db, realfiles2
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


class UndoCommand(QtGui.QUndoCommand):
    """A generic undo command for arbitrary changes. The constructor gets an OrderedDict mapping
    ids to a tuple, specifying the state of that element before and after the change, respectively.
    
    Whenever possible, use specialized undo commands (or create own subclasses) below which allow for
    a more efficient implementation and widget notification."""
    
    def __init__(self, level, changes, contentsChanged = False, text = ''):
        """Creates an UndoCommand, i.e. an object that stores what has changed in one
        step of database editing.
        
        <changes> is an OrderedDict of ids to tuples of Elements:
        The state before and after the change.
        <level> must be either EDITOR or REAL.
        <contentsChanged> must be True if for at least one of the elements the content
        relations are changed.
        <text> is a user-readable text describing the action; this will appear in the undo/redo menu entries."""
        QtGui.QUndoCommand.__init__(self)
        self.level  = level
        self.changes = changes
        self.contentsChanged = contentsChanged
        self.setText(text)
        
    def redo(self):
        if self.level == REAL:
            real.commit(self.changes)
        else:
            redoChanges = OrderedDict(( (k,v[1]) for k,v in self.changes.items() ))
            redoEvent = events.ElementChangeEvent(self.level, redoChanges, contentsChanged = self.contentsChanged)
            dispatcher.changes.emit(redoEvent)

    def undo(self):
        if self.level == REAL:
            undoChanges = {k:(v[1],v[0]) for k,v in self.changes.items() }
            assert len(undoChanges) > 0
            real.commit(undoChanges)
        else:
            undoChanges = OrderedDict(( (k,v[0]) for k,v in self.changes.items() ))
            undoEvent = events.ElementChangeEvent(self.level, undoChanges, contentsChanged = self.contentsChanged)
            dispatcher.changes.emit(undoEvent)

class CommitCommand(UndoCommand):
    
    def __init__(self):
        QtGui.QUndoCommand.__init__(self)
        self.level = REAL
        self.setText('commit')
        # store contents of all open editors in self.editorRoots
        from ..gui import mainwindow
        models = [dock.editor.model() for dock in mainwindow.mainWindow.getWidgets('editor')]
        self.editorRoots = [model.root.copy() for model in models]
        
        # save current state in the editors in dicts mapping id->element
        self.newElements, self.dbElements = dict(), dict()
        for element in itertools.chain( *(root.getAllNodes(skipSelf = True) for root in self.editorRoots) ):
            if element.isInDB():
                if not element.id in self.dbElements:
                    self.dbElements[element.id] = element
            else:
                if not element.id in self.newElements:
                    self.newElements[element.id] = element
        
        #load original states of in-db elements (needed for undo)
        self.originalElements = dict()
        for element in self.dbElements.values():
            origEl = Element.fromId(element.id, loadData = True)
            if origEl.isContainer():
                origEl.loadContents(recursive = False, loadData = False)
            originalElements[element.id] = origEl
        
    def redo(self):
        """Perform the commit. This is done by the following steps:
          - copy contents of all editors, clear them afterwards
          - generate real IDs for new elements
          - call real.commit() for all elements contained in the editors; this will also
            invoke a ElementsChangeEvent for all the changes (new elements will have a negative
            id as key in the dictionary)
          - restore the (committed) content in the editors by an appropriate event"""
        from .. import models
        # clear all editors by event
        emptyRoots = [root.copy(contents = []) for root in self.editorRoots]
        dispatcher.changes.emit(events.ElementChangeEvent(REAL, {root.id:root for root in emptyRoots}, True))
        
        # assign new IDs to all elements which have editor IDs so far
        self.idMap = real.createNewElements(self.newElements.values())
        
        # store new IDs in the editors (old ones are still available via self.idMap
        for elem in itertools.chain( *(root.getAllNodes(skipSelf = True) for root in self.editorRoots) ):
            if not elem.isInDB():
                elem.id = self.idMap[elem.id]
                
        # commit all the changes
        changes = {}
        for id, elem in self.newElements.items():
            changes[self.idMap[id]] = ( models.Element.fromId(self.idMap[id]), elem )
        for id, elem in self.dbElements.items():
            changes[id] = ( self.originalElements[id], self.dbElements[id] )
        real.commit(changes)
        
        # notify the editors to display the new commited content
        dispatcher.changes.emit(events.ElementChangeEvent(REAL, {root.id:root for root in self.editorRoots}, True))
        
        
    def undo(self):
        """Undo the commit. This is relatively easy:
          - empty all editors
          - revert the changes for elements which previously existed in the DB
          - delete elements which didn't; if they are files, restore the original tags
        """
        # clear the editors
        emptyRoots = [root.copy(contents = []) for root in self.editorRoots]
        dispatcher.changes.emit(events.ElementChangeEvent(REAL, {root.id:root for root in emptyRoots}, True))
        
        # undo changes to elements that were in the db before
        changes = {}
        for id, elem in self.dbElements.items():
            changes[id] = ( self.dbElements[id], self.originalElements[id] )
        real.commit(changes)
        # write original tags to files which were newly added
        tagChanges = {}
        for elem in self.newElements.values():
            if elem.isFile():
                tagChanges[elem] = (elem.tags, elem.fileTags)
        real.changeTags(tagChanges, emitEvent = False) 
        
        # delete all elements which had editorIDs before
        real.deleteElements([el.id for el in self.newElements.values() ])
        
        # restore original element IDs
        revIdMap = {b:a for (a,b) in self.idMap.items()}
        for elem in itertools.chain( *(root.getAllNodes(skipSelf = True) for root in self.editorRoots) ):
            elem.id = revIdMap[elem.id]

def commitEditors():
    command = CommitCommand()
    try:
        push(command)
    except StackChangeRejectedException:
        pass
          
        
class ModifySingleElementCommand(UndoCommand):
    """A specialized undo command for the modification of a single element (tags, position, ..., but no 
    contents)."""
    
    def __init__(self, level, before, after, text=''):
        QtGui.QUndoCommand.__init__(self)
        if level != EDITOR:
            raise NotImplementedError()
        self.level = level
        self.before = before.copy()
        self.after = after.copy()
        self.setText(text)
    
    def redo(self):
        dispatcher.changes.emit(events.SingleElementChangeEvent(self.level, self.after))
    def undo(self):
        dispatcher.changes.emit(events.SingleElementChangeEvent(self.level, self.before))

class PositionChangeCommand(UndoCommand):
    """An undo command for changing positions of elements below one single parent."""
    
    def __init__(self, level, parentId, positionChanges, text = ''):
        QtGui.QUndoCommand.__init__(self)
        if level != EDITOR:
            raise NotImplementedEror()
        self.level = level
        self.parentId = parentId
        self.positionChanges = positionChanges
        
    def redo(self):
        dispatcher.changes.emit(events.PositionChangeEvent(self.level, self.parentId, 
                                                           dict(self.positionChanges)))
    
    def undo(self):
        dispatcher.changes.emit(events.PositionChangeEvent(self.level, self.parentId,
                                                           dict(map(reversed,self.positionChanges))))
        
def createRanges(tuples):
        previous = None
        start = None
        elements = []
        for i, elem in sorted(tuples):
            if previous is None:
                previous = start = i
            if i > previous + 1:
                # emit previous range
                yield start, elements
                start = i
                elements = []
            previous = i
            elements.append(elem)
        yield start, elements
        
class RemoveElementsCommand(UndoCommand):
    """A specialized undo command for the removal of elements."""
    
    def __init__(self, level, elements, text=''):
        """Creates the remove command. Elements must be an iterable of Element objects.
        
        The constructor checks for redundancies in the list (e.g., if an item and its parent
        are both in the list, then the item itself is redundant)."""
        QtGui.QUndoCommand.__init__(self)
        if level != EDITOR:
            raise NotImplementedError()
        self.level = level
        if len(elements) == 0:
            return
        for i in reversed(elements):
            for p in i.getParents():
                if p in elements:
                    elements.remove(i)
        changes = {} # map of parent id -> set of (index, elementId) tuples
        self.elementPool = {}
        for elem in elements:
            parent = elem.parent
            if parent.id not in changes:
                changes[parent.id] = set()
            changes[parent.id].add((parent.index(elem), elem.id))
            self.elementPool[elem.id] = elem.copy()
        # now create index ranges from the unordered sets
        self.removals = {}
        for parentId, changeSet in changes.items():
            self.removals[parentId] = []
            for tuple in createRanges(changeSet):
                self.removals[parentId].append( tuple )
                 
    def redo(self):
        dispatcher.changes.emit(events.RemoveElementsEvent(
             self.level, dict((pid, [ ( tup[0], len(tup[1]) ) for tup in reversed(elemSet)]) for pid,elemSet in self.removals.items())))
    
    def undo(self):
        dispatcher.changes.emit(events.InsertElementsEvent(
             self.level, dict((pid, [ (tup[0], [self.elementPool[i] for i in tup[1]]) for tup in elemSet ] ) for pid, elemSet in self.removals.items())))

class InsertElementsCommand(UndoCommand):
    def __init__(self, level, insertions, text=''):
        super().__init__(level, insertions, text)
        if level != EDITOR:
            raise NotImplementedError()
        self.level = level
        self.insertions = insertions
    
    def redo(self):
        dispatcher.changes.emit(events.InsertElementsEvent(
              self.level, self.insertions))
    def undo(self):
        dispatcher.changes.emit(events.RemoveElementsEvent(
              self.level, dict((pid, [ (tup[0], len(tup[1]) ) for tup in reversed(elemSet)]) for pid,elemSet in self.insertions.items())))

class TagUndoCommand(UndoCommand):
    """An UndoCommand that changes only tags. The difference to UndoCommand is that the dict *changes*
    contains tuples of tags.Storage: the tags before and after the change."""
    def __init__(self, level, changes, text = ''):
        UndoCommand.__init__(self,level,changes,contentsChanged=False,text=text)
        
    def redo(self):
        # Note that real.changeTags and TagModifyEvent expect a different format for changes 
        if self.level == REAL:
            real.changeTags(self.changes)
        else:
            changes = OrderedDict((k,v[1]) for k,v in self.changes.items())
            dispatcher.changes.emit(events.TagModifyEvent(changes))

    def undo(self):
        # Note that real.changeTags and TagModifyEvent expect a different format for changes
        if self.level == REAL:
            real.changeTags({k: (v[1],v[0]) for k,v in self.changes.items()})
        else:
            changes = OrderedDict((k,v[0]) for k,v in self.changes.items())
            dispatcher.changes.emit(events.TagModifyEvent(changes))

class SortValueUndoCommand(UndoCommand):
    """An UndoCommand that changes the sort value of a tag value."""
    def __init__(self, tag, valueId, oldSort = None, newSort = None, text = ''):
        QtGui.QUndoCommand.__init__(self)
        self.tag = tag
        self.valueId = valueId
        self.oldSort = oldSort
        self.newSort = newSort
        self.setText(text)
        
    def redo(self):
        db.write.changeSortValue(self.tag, self.valueId, self.newSort)
    def undo(self):
        db.write.changeSortValue(self.tag, self.valueId, self.oldSort)
        
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
    newContainer = Container(id = newEditorId(), contents = copies, tags = t, position = insertElementPosition)
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


from . import real
    
