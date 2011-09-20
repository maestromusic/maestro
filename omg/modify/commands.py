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

from .. import tags as tagsModule, logging, database as db, models
from . import events, real, dispatcher
from ..constants import *

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)


class UndoCommand(QtGui.QUndoCommand):
    """A generic undo command for arbitrary changes. The constructor gets an OrderedDict mapping
    ids to a tuple, specifying the state of that element before and after the change, respectively.
    
    Whenever possible, use specialized undo commands (or create own subclasses) below which allow for
    a more efficient implementation and widget notification."""
    
    level = REAL
    
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
        self.setText('commit')
        # store (copies of) contents of all open editors in self.editorRoots
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
          - copy roots of all editors, clear them afterwards
          - generate real IDs for new elements
          - call real.commit() for all elements contained in the editors; this will also
            invoke a ElementsChangeEvent for all the changes (new elements will have a negative
            id as key in the dictionary)
          - restore the (committed) content in the editors by an appropriate event"""
        
        progress = QtGui.QProgressDialog(translate(__name__, "Commiting files..."),
                                         None, 0, 7)
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModal)
        from .. import models
        progress.setValue(1)
        # assign new IDs to all elements which have editor IDs so far
        if hasattr(self, 'idMap'): # this is not the first redo
            elementsToCreate = []
            for elem in self.newElements.values():
                elemCopy = elem.copy()
                elemCopy.id = self.idMap[elem.id]
                elementsToCreate.append(elemCopy)
            real.createNewElements(elementsToCreate)
        else:
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
            oldElem.tags = tagsModule.Storage()
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
                

class ChangeSingleElementCommand(UndoCommand):
    """A specialized undo command for the modification of a single element (tags, position, ..., but no 
    contents)."""
    
    def __init__(self, level, before, after, text=''):
        QtGui.QUndoCommand.__init__(self, text)
        if level != EDITOR:
            raise NotImplementedError()
        self.level = level
        self.before = before.copy()
        self.after = after.copy()
    
    def redo(self):
        dispatcher.changes.emit(events.SingleElementChangeEvent(self.level, self.after))
        
    def undo(self):
        dispatcher.changes.emit(events.SingleElementChangeEvent(self.level, self.before))


class ChangeMajorFlagCommand(ChangeSingleElementCommand):
    """A command to toggle the 'major' flag of a single element."""
    def __init__(self, level, element, text = ''):
        QtGui.QUndoCommand.__init__(self, text)
        self.level = level
        self.element = element.copy()
        
    def redo(self):
        self.element.major = not self.element.major
        if self.level == REAL:
            real.setMajor(self.element, emitEvent = False)
        dispatcher.changes.emit(events.MajorFlagChangeEvent(self.level, self.element))
    
    undo = redo
    
class PositionChangeCommand(UndoCommand):
    """An undo command for changing positions of elements below one single parent."""
    
    def __init__(self, level, parentId, positionChanges, text = ''):
        """Initialize the PositionChangeCommand. *positionChanges* is a list of tuples
        mapping old to new positions."""
        QtGui.QUndoCommand.__init__(self, text)
        self.level = level
        self.parentId = parentId
        self.positionChanges = positionChanges
        
    def redo(self):
        if self.level == REAL:
            real.changePositions(self.parentId, self.positionChanges)
        else:
            dispatcher.changes.emit(events.PositionChangeEvent(self.level, self.parentId, 
                                                           dict(self.positionChanges)))
    
    def undo(self):
        if self.level == REAL:
            real.changePositions(self.parentId, [ (b,a) for a,b in self.positionChanges ])
        else:
            dispatcher.changes.emit(events.PositionChangeEvent(self.level, self.parentId,
                                                           dict(map(reversed,self.positionChanges))))
        
        
class InsertElementsCommand(UndoCommand):
    """A specialized command to insert elements into an existing container."""
    
    def __init__(self, level, insertions, text=''):
        """Create the command. *insertions* is a dict mapping parent ID to pairs
        (position, insertedElement). If the node given by parent ID is a container,
        position == insertedElement.position should hold. If the parent is a RootNode,
        then position is interpreted as the index at which the container is to be inserted."""
        QtGui.QUndoCommand.__init__(self, text)
        for v in insertions.values():
            assert len(v) > 0
        self.level = level
        self.insertions = insertions
    
    def redo(self):
        if self.level == REAL:
            real.addContents(self.insertions)
        else:
            dispatcher.changes.emit(events.InsertContentsEvent(self.level, self.insertions))
        
    def undo(self):
        if self.level == REAL:
            real.removeContents({parent:list(zip(*pairs))[0] for (parent,pairs) in self.insertions.items() })
        else:
            dispatcher.changes.emit(events.RemoveContentsEvent(EDITOR,
                                      {parent:list(zip(*pairs))[0] for parent,pairs in self.insertions.items() }))


class RemoveElementsCommand(UndoCommand):
    """A specialized undo command for the removal of elements. There are three types of removals:
    - DISK: delete the file corresponding to an element on disk,
    - DB: remove an element from the database,
    - CONTENTS: remove the "is-child-of" relation between an element and its parent.
    In EDITOR mode, the latter is the only valid remove operation. The operations above are ordered
    in such a way that any of them implies all of those below (e.g., if a file is deleted on the disk,
    it is automatically removed from the database and all parents)."""
    
    
    
    def __init__(self, level, elements, mode = CONTENTS, text=''):
        """Creates the remove command. Elements must be an iterable of Element objects, mode
        one of DISK, DB, CONTENTS (see the class doc for details)."""
        QtGui.QUndoCommand.__init__(self, text)
        
        if level == EDITOR and mode != CONTENTS:
            logger.error('cannot remove in mode other than CONTENTS in EDITOR mode -- please fix.')
            mode = CONTENTS
        self.mode = mode
        self.level = level
        assert len(elements) > 0
        
        self.changes = {}
        self.elementPool = {}
        # need to get, for each element, _all_ containers containing that element, in order to
        # be able to restore the content relations on undo.
        for element in elements:
            if not element.id in self.elementPool:
                self.elementPool[element.id] = element.copy()
            if mode == CONTENTS:
                parentIDs = (element.parent.id,)
                parentIsRoot = isinstance(element.parent, models.RootNode)
            else:
                parentIDs = db.parents(element.id)
                parentIsRoot = False
            
            for parentID in parentIDs:
                if parentID not in self.changes:
                    self.changes[parentID] = set()
                if mode == CONTENTS:
                    positions = (element.parent.index(element, True) if parentIsRoot else element.position,)
                else:
                    positions = db.positions(parentID, element.id)
                for position in positions:
                    self.changes[parentID].add( (position, element.id) )
        self.positionOnlyChanges = {parent:tuple(zip(*tup))[0] for parent,tup in self.changes.items()}
    
    def redo(self):
        if self.level == REAL:
            if self.mode == CONTENTS:
                real.removeContents(self.positionOnlyChanges)
            else:
                real.deleteElements(list(self.elementPool.keys()))
        else:
            dispatcher.changes.emit(events.RemoveContentsEvent(self.level, self.positionOnlyChanges))
    
    def undo(self):
        elementChanges = {}
        for parent, values in self.changes.items():
            changeList = elementChanges[parent] = []
            for position, elementID in values:
                changeList.append((position, self.elementPool[elementID]))
        if self.level == REAL:
            """Reinsert the elements. First we create them, then handle content relations."""
            real.createNewElements(list(self.elementPool.values()))
            real.addContents(elementChanges)
        else:
            dispatcher.changes.emit(events.InsertContentsEvent(EDITOR, elementChanges))

        
class CreateContainerCommand(UndoCommand):
    """A specialized command to create a single container in the database with the given
    attributes, but without any content relations."""
    
    def __init__(self, tags = None, flags = None, major = True, text = translate(__name__, 'create container')):
        QtGui.QUndoCommand.__init__(self, text)
        self.tags = tags if tags else tagsModule.Storage()
        self.flags = flags if flags else []
        self.major = major
        self.id = None
        
    def redo(self):
        self.id = real.newContainer(self.tags, self.flags, self.major, self.id)
        
    def undo(self):
        real.deleteElements([self.id])
        
        
class TagUndoCommand(UndoCommand):
    """An UndoCommand that changes only tags. The difference to UndoCommand is that the dict *changes*
    contains tuples of tags.Storage: the tags before and after the change."""
    def __init__(self,level,changes,elements=None,text = ''):
        UndoCommand.__init__(self,level,changes,contentsChanged=False,text=text)
        if level == REAL:
            self.elements = [el.export(attributes=['path']) for el in elements]
        
    def redo(self):
        logger.debug('TagUndoCommand -- redo (REAL:{})'.format(self.level == REAL))
        if self.level == REAL:
            real.changeTags(self.changes,self.elements)
        else:
            changes = {k: v[1] for k,v in self.changes.items()}
            dispatcher.changes.emit(events.TagChangeEvent(self.level, changes))

    def undo(self):
        logger.debug('TagUndoCommand -- undo (REAL:{})'.format(self.level == REAL))
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
    def __init__(self, tag, valueId, oldSort = -1, newSort = None, text = translate('modify.commands','change sort value')):
        QtGui.QUndoCommand.__init__(self,text)
        self.tag = tag
        self.valueId = valueId
        self.oldSort = oldSort
        self.newSort = newSort
        
    def redo(self):
        real.setSortValue(self.tag,self.valueId,self.newSort,self.oldSort)
        
    def undo(self):
        real.setSortValue(self.tag,self.valueId,self.oldSort,self.newSort)

class ValueHiddenUndoCommand(UndoCommand):
    """An UndoCommand to change the "hidden" attribute of a tag value."""
    def __init__(self, tag, valueId, newState = None, text = translate('modify.commands', 'change hidden flag')):
        """Create the command. If newState is None, then the old one will be fetched from the database
        and the new one set to its negative.
        Otherwise, this class assumes that the current state is (not newState), so don't call this
        whith newState = oldState."""
        QtGui.QUndoCommand.__init__(self, text)
        self.tag = tag
        self.valueId = valueId
        self.newState = db.hidden(tag, valueId) if newState is None else newState
        
    def redo(self):
        real.setHidden(self.tag, self.valueId, self.newState)
    
    def undo(self):
        real.setHidden(self.tag, self.valueId, not self.newState)      

class RenameTagValueCommand(UndoCommand):
    """A command to rename *all* occurences of a specific tag value, e.g. all "Frederic Chopin" to
    "Frédéric Chopin"."""
    def __init__(self, tag, oldValue, newValue, text = None):
        QtGui.QUndoCommand.__init__(self)
        if text is None:
            text = translate('modify.commands', 'change {}-tag value from {} to {}'.format(tag, oldValue, newValue))
        self.setText(text)
        self.valueId = db.idFromValue(tag, oldValue)
        self.oldValue = oldValue
        self.newValue = newValue
        self.tag = tag
        # store elements that will be changed
        changedIDs = set(db.elementsWithTagValue(tag, self.valueId))
        
        # store elements that already have the new value
        try:
            existingIDs = set(db.elementsWithTagValue(tag, newValue))
        except db.sql.EmptyResultException:
            existingIDs = set()
        
        self.both = changedIDs & existingIDs
        self.changeSimple = changedIDs - self.both
    
    def redo(self):
        real.changeTagValue(self.tag, self.oldValue, self.newValue, self.changeSimple | self.both)
        
    def undo(self):
        real.changeTagValue(self.tag, self.newValue, self.oldValue, self.changeSimple)
        if len(self.both) > 0:
            real.addTagValue(self.tag, self.oldValue, self.both)