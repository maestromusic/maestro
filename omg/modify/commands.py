#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer, Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#

import itertools
from collections import OrderedDict

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import tags, logging, database as db, models
from . import events, real, REAL, EDITOR, dispatcher

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)


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
        from ..gui import editor
        editorModels = editor.activeEditorModels()
        self.editorRoots = [model.root.copy() for model in editorModels]
        
        # save current state in the editors in dicts mapping id->element
        self.newElements, self.dbElements = dict(), dict()
        for element in itertools.chain.from_iterable(
                                            root.getAllNodes(skipSelf = True) for root in self.editorRoots):
            if element.isInDB():
                if not element.id in self.dbElements:
                    self.dbElements[element.id] = element
            else:
                if not element.id in self.newElements:
                    self.newElements[element.id] = element
        
        #load original states of in-db elements (needed for undo)
        self.originalElements = dict()
        for element in self.dbElements.values():
            origEl = models.Element.fromId(element.id, loadData = True)
            if origEl.isContainer():
                origEl.loadContents(recursive = False, loadData = False)
            self.originalElements[element.id] = origEl
        
    def redo(self):
        """Perform the commit. This is done by the following steps:
          - copy contents of all editors, clear them afterwards
          - generate real IDs for new elements
          - call real.commit() for all elements contained in the editors; this will also
            invoke a ElementsChangeEvent for all the changes (new elements will have a negative
            id as key in the dictionary)
          - restore the (committed) content in the editors by an appropriate event"""
        
        progress = QtGui.QProgressDialog(translate('modify.commands', "Commiting files..."),
                                         None, 0, 7)
        progress.setMinimumDuration(1500)
        progress.setWindowModality(Qt.WindowModal)
        from .. import models
        # clear all editors by event
        emptyRoots = [root.copy(contents = []) for root in self.editorRoots]
        dispatcher.changes.emit(events.ElementChangeEvent(REAL, {root.id:root for root in emptyRoots}, True))
        progress.setValue(1)
        # assign new IDs to all elements which have editor IDs so far
        self.idMap = real.createNewElements(self.newElements.values())
        progress.setValue(2)
        # store new IDs in the editors (old ones are still available via self.idMap
        for elem in itertools.chain( *(root.getAllNodes(skipSelf = True) for root in self.editorRoots) ):
            if not elem.isInDB():
                elem.id = self.idMap[elem.id]
                
        # commit all the changes
        changes = {}
        for id, elem in self.newElements.items():
            oldElem = models.Element.fromId(self.idMap[id], loadData = False)
            if hasattr(elem, 'fileTags'):
                oldElem.fileTags = elem.fileTags
            oldElem.tags = tags.Storage()
            oldElem.flags = list()
            changes[self.idMap[id]] = ( oldElem, elem )
        progress.setValue(3)
        for id, elem in self.dbElements.items():
            changes[id] = ( self.originalElements[id], self.dbElements[id] )
        progress.setValue(4)
        real.commit(changes)
        progress.setValue(5)
        # notify the editors to display the new commited content
        dispatcher.changes.emit(events.ElementChangeEvent(REAL, {root.id:root for root in self.editorRoots}, True))
        progress.setValue(6)
        
        
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
                tagChanges[elem.id] = (elem.tags, elem.fileTags)
        real.changeTags(tagChanges,self.newElements.values(),emitEvent = False) 
        
        # delete all elements which had editorIDs before
        real.deleteElements([el.id for el in self.newElements.values() ])
        
        # restore original element IDs (for next redo)
        revIdMap = {b:a for (a,b) in self.idMap.items()}
        for elem in itertools.chain.from_iterable(
                                            root.getAllNodes(skipSelf = True) for root in self.editorRoots):
            if elem.id in revIdMap:
                elem.id = revIdMap[elem.id]
                
     
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
        """Initialize the PositionChangeCommand. *positionChanges* is a list of tuples
        mapping old to new positions."""
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
        
        
class InsertElementsCommand(UndoCommand):
    def __init__(self, level, insertions, text=''):
        super().__init__(level, insertions, text)
        if level != EDITOR:
            raise NotImplementedError()
        self.level = level
        self.insertions = insertions
    
    def redo(self):
        dispatcher.changes.emit(events.InsertElementsEvent(self.level, self.insertions))
        
    def undo(self):
        dispatcher.changes.emit(events.RemoveElementsEvent(
              self.level, dict((pid, [ (tup[0], len(tup[1]) ) for tup in reversed(elemSet)])
                               for pid,elemSet in self.insertions.items())))


class RemoveElementsCommand(UndoCommand):
    """A specialized undo command for the removal of elements."""
    
    def __init__(self, level, elements, text=''):
        """Creates the remove command. Elements must be an iterable of Element objects.
        
        The constructor checks for redundancies in the list (e.g., if an item and its parent
        are both in the list, then the item itself is redundant)."""
        QtGui.QUndoCommand.__init__(self)
        if level != EDITOR:
            logger.warning('tu was')
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
            for tuple in _createRanges(changeSet):
                self.removals[parentId].append( tuple )
                 
    def redo(self):
        dispatcher.changes.emit(events.RemoveElementsEvent(
             self.level, dict((pid, [ ( tup[0], len(tup[1]) ) 
                                 for tup in reversed(elemSet)]) for pid,elemSet in self.removals.items())))
    
    def undo(self):
        dispatcher.changes.emit(events.InsertElementsEvent(
             self.level, dict((pid, [ (tup[0], [self.elementPool[i] for i in tup[1]]) for tup in elemSet ] )
                               for pid, elemSet in self.removals.items())))

        
# Helper function for RemoveElementsCommand
def _createRanges(tuples):
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
    
        
class TagUndoCommand(UndoCommand):
    """An UndoCommand that changes only tags. The difference to UndoCommand is that the dict *changes*
    contains tuples of tags.Storage: the tags before and after the change."""
    def __init__(self,level,changes,elements=None,text = ''):
        UndoCommand.__init__(self,level,changes,contentsChanged=False,text=text)
        if level == REAL:
            self.elements = [el.export(attributes=['path']) for el in elements]
        
    def redo(self):
        if self.level == REAL:
            real.changeTags(self.changes,self.elements)
        else:
            changes = {k: v[1] for k,v in self.changes.items()}
            dispatcher.changes.emit(events.TagChangeEvent(self.level, changes))

    def undo(self):
        if self.level == REAL:
            real.changeTags({k: (v[1],v[0]) for k,v in self.changes.items()},self.elements)
        else:
            changes = {k: v[0] for k,v in self.changes.items()}
            dispatcher.changes.emit(events.TagChangeEvent(self.level, changes))


class FlagUndoCommand(UndoCommand):
    """An UndoCommand that changes only tags. The difference to UndoCommand is that the dict *changes*
    contains tuples of tags.Storage: the tags before and after the change."""
    def __init__(self,level,changes,text = ''):
        super().__init__(level,changes,contentsChanged=False,text=text)
        
    def redo(self):
        if self.level == REAL:
            real.changeFlags(self.changes)
        else:
            changes = {k: v[1] for k,v in self.changes.items()}
            dispatcher.changes.emit(events.FlagChangeEvent(self.level, changes))

    def undo(self):
        if self.level == REAL:
            real.changeFlags({k: (v[1],v[0]) for k,v in self.changes.items()})
        else:
            changes = {k: v[0] for k,v in self.changes.items()}
            dispatcher.changes.emit(events.FlagChangeEvent(self.level, changes))
            
            
class SortValueUndoCommand(UndoCommand):
    """An UndoCommand that changes the sort value of a tag value."""
    def __init__(self, tag, valueId, oldSort = None, newSort = None, text = ''):
        QtGui.QUndoCommand.__init__(self,text)
        self.tag = tag
        self.valueId = valueId
        self.oldSort = oldSort
        self.newSort = newSort
        
    def redo(self):
        real.changeSortValue(self.tag,self.valueId,self.newSort,self.oldSort)
        
    def undo(self):
        real.changeSortValue(self.tag,self.valueId,self.oldSort,self.newSort)
        