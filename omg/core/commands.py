# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2012 Martin Altmayer, Michael Helmling
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

# This module contains common QUndoCommands for modifying Elements in Levels

from PyQt4 import QtCore, QtGui

from . import levels, tags, flags
from .elements import ContentList
from .. import database as db, logging, utils
from ..modify import real as modifyReal
from ..database import write

logger = logging.getLogger(__name__)

class CommitCommand(QtGui.QUndoCommand):
    """The CommitCommand is used to "commit" the state of some elements in one level to its parent level.
    If the parent level is *real*, then also the database and, if needed, files on disk are updated
    accordingly."""
    
    def __init__(self, level, ids, text = None):
        """Sets up a commit command for the given *ids* in *level*."""
        super().__init__(text)
        self.level = level
        
        allIds = set(ids)
        # add IDs of all children to ensure a consistent commit
        additionalIds = set()
        for id in allIds:
            additionalIds.update(level.children(id))
        allIds.update(additionalIds)
        
        self.real = level.parent is levels.real # a handy shortcut
        if self.real:
            self.newInDatabase = [ id for id in allIds if id < 0 ]
            self.realFileChanges = {}
            self.idMap = None # maps tempId -> realId
        else:
            # if non-real parent, newId is the identity function
            self.newId = self.oldId = lambda x : x
            
        self.newElements = [] # elements which are not in parent level before the commit
        self.flagChanges, self.tagChanges, self.contentsChanges, self.majorChanges = {}, {}, {}, {}
        self.pathChanges = {}
        self.ids, self.contents = [], [] # for the events
        for id in allIds:
            element, contents =  self.recordChanges(id)
            if element:
                self.ids.append(id)
            if contents:
                self.contents.append(id)
    
    def recordChanges(self, id):
        """Store changes of a single element, return two booleans (changeElement, changeContents)
        reflecting whether the elements itself and/or its contents have changed."""
        myEl = self.level.get(id)
        changeElement, changeContents = False, False
        if id in self.level.parent:
            oldEl = self.level.parent.get(id)
            oldTags = oldEl.tags
            oldFlags = oldEl.flags
            if oldEl.isContainer():
                oldMajor = oldEl.major
                oldContents = oldEl.contents
            else:
                oldPath = oldEl.path
        else:
            changeElement = True
            self.newElements.append(id)
            oldTags = None
            oldFlags = []
            if myEl.isContainer():
                oldMajor = None
                oldContents = ContentList()
            else:
                oldPath = levels.pathFromId(id)  
        
        if oldTags != myEl.tags:
            changes = tags.TagDifference(oldTags, myEl.tags)
            self.tagChanges[id] = changes
            if self.real and myEl.isFile():
                # check for file tag changes
                if id not in self.newElements:
                    if not changes.onlyPrivateChanges():
                        # element already loaded in real level (already commited or loaded in playlist)
                        self.realFileChanges[myEl.path] = changes
                else:
                    fileTags = myEl.fileTags # set by Element drop into editor; avoids costly disk access
                    fileChanges = tags.TagDifference(fileTags, myEl.tags)
                    if not fileChanges.onlyPrivateChanges():
                        self.realFileChanges[myEl.path] = fileChanges
                        
                
            changeElement = True
        if oldFlags != myEl.flags:
            self.flagChanges[id] = flags.FlagDifference(oldFlags, myEl.flags)
            changeElement = True
        if myEl.isContainer():
            if oldContents != myEl.contents:
                changeContents = True
                self.contentsChanges[id] = (oldContents.copy(), myEl.contents.copy())
            if oldMajor != myEl.major:
                self.majorChanges[id] = (oldMajor, myEl.major)
                changeElement = True
        elif oldPath != myEl.path:
            self.pathChanges[id] = (oldPath, myEl.path)
            changeElement = True 
        return changeElement, changeContents
            
    def redo(self):
        if self.real:
            # create new elements in DB to obtain id map, and change IDs in current level 
            db.transaction()
            if self.idMap is None:
                # first redo -> prepare id mapping
                self.idMap = modifyReal.createNewElements(self.level, self.newInDatabase)
                self.newId = utils.dictOrIdentity(self.idMap)
                self.oldId = utils.dictOrIdentity({b:a for a,b in self.idMap.items() })
                # update contentsChanges to use the new ids
                for _, newContents in self.contentsChanges.values():
                    newContents.ids[:] = map(self.newId, newContents.ids)
            else:
                modifyReal.createNewElements(self.level, self.newInDatabase, self.idMap)
            # change IDs of new elements in both current and parent level
            for id in self.newInDatabase:
                self.level.changeId(id, self.newId(id))
                if id in self.level.parent:
                    self.level.parent.changeId(id, self.newId(id))
                    
        # Add/update elements in parent level
        newFilesPaths = []
        for id in set(self.ids + self.contents):
            nid = self.newId(id)
            elem = self.level.elements[nid]
            if id in self.newElements:
                copy = elem.copy()
                copy.level = self.level.parent
                self.level.parent.elements[nid] = copy
                if elem.isFile():
                    newFilesPaths.append(elem.path)
            else:
                pElem = self.level.parent.elements[nid]
                if id in self.majorChanges:
                    pElem.major = self.majorChanges[id][1]
                if id in self.tagChanges:
                    self.tagChanges[id].apply(pElem.tags)
                if id in self.flagChanges:
                    self.flagChanges[id].apply(pElem.flags)
                if id in self.contentsChanges:
                    pElem.contents = self.contentsChanges[id][1].copy()
                if id in self.pathChanges:
                    pElem.path = self.pathChanges[id][1]
                        
        # apply changes in DB, if parent level is real
        if self.real:
            if len(self.majorChanges) > 0:
                db.write.setMajor((self.newId(id), newMajor) for id,(_,newMajor) in self.majorChanges.items())
            if len(self.contentsChanges) > 0:
                modifyReal.changeContents({self.newId(id):changes for id, changes in self.contentsChanges.items()})
            if len(self.tagChanges) > 0:
                # although the difference from our level to the parent might affect only a subset of the tags,
                # for elements new to the database the complete tags must be written (happens if a non-db file is
                # loaded in real)
                def dbDiff(id):
                    if id in self.newInDatabase:
                        return tags.TagDifference(None, self.level.get(self.newId(id)).tags)
                    else:
                        return self.tagChanges[id]
                modifyReal.changeTags({self.newId(id):dbDiff(id) for id in self.tagChanges.keys()})
            if len(self.flagChanges) > 0:
                modifyReal.changeFlags({self.newId(id):diff for id,diff in self.flagChanges.items()})            
            db.commit()
            if len(self.pathChanges) > 0:
                levels.real.renameFiles({self.newId(id):diff for id,diff in self.pathChanges.items()})
            for path,changes in self.realFileChanges.items():
                logger.debug("changing file tags: {0}-->{1}".format(path, changes))
                modifyReal.changeFileTags(path, changes)

        # an event for both levels
        self.level.parent.emitEvent([self.newId(id) for id in self.ids], [self.newId(id) for id in self.contents])
        self.level.emitEvent([self.newId(id) for id in self.ids], [])
        
        if len(newFilesPaths) > 0:
            self.level.parent.changed.emit(levels.FileCreateDeleteEvent(newFilesPaths))
        self.newFilesPaths = newFilesPaths # store for undo
        
    def undo(self):
        if self.real:
            for path, changes in self.realFileChanges.items():
                logger.debug("reverting file tags: {0}<--{1}".format(path, changes))
                modifyReal.changeFileTags(path, changes, reverse = True)
            if len(self.pathChanges) > 0:
                levels.real.renameFiles({self.newId(id):(b,a) for id,(a,b) in self.pathChanges.items()})
            db.transaction()
            if len(self.newInDatabase) > 0:
                db.write.deleteElements(list(self.idMap.values()))
            majorChangesExisting = [(self.newId(id),oldMajor) for id,(oldMajor,_) in self.majorChanges.items()
                                        if id not in self.newInDatabase]
            if len(majorChangesExisting) > 0:
                db.write.setMajor(majorChangesExisting)
            contentsChangesExisting = {self.newId(id):(b,a) for id, (a,b) in self.contentsChanges.items()
                                        if id not in self.newInDatabase}
            if len(contentsChangesExisting) > 0:
                modifyReal.changeContents(contentsChangesExisting)
            tagChangesExisting = {self.newId(id):diff for id,diff in self.tagChanges.items()
                                    if id not in self.newInDatabase}
            if len(tagChangesExisting) > 0:
                modifyReal.changeTags(tagChangesExisting, reverse = True)
            flagChangesExisting = {self.newId(id):diff for id,diff in self.tagChanges.items()
                                    if id not in self.newInDatabase}
            if len(flagChangesExisting) > 0:
                modifyReal.changeFlags(flagChangesExisting, reverse = True)
        
        for id in set(self.ids + self.contents):
            if id in self.newElements:
                del self.level.parent.elements[self.newId(id)]
            else:
                pElem = self.level.parent.elements[self.newId(id)]
                if id in self.majorChanges:
                    pElem.major = self.majorChanges[id][0]
                if id in self.tagChanges:
                    self.tagChanges[id].revert(pElem.tags)
                if id in self.flagChanges:
                    self.flagChanges[id].revert(pElem.flags)
                if id in self.contentsChanges:
                    pElem.contents = self.contentsChanges[id][0].copy()
                if id in self.pathChanges:
                    pElem.path = self.pathChanges[id][0]
        
        if self.real:
            for id in self.newInDatabase:
                self.level.changeId(self.newId(id), id)
                if self.newId(id) in self.level.parent:
                    self.level.parent.changeId(self.newId(id), id)
            db.commit()
        self.level.parent.emitEvent(self.ids, self.contents)
        self.level.emitEvent(self.ids, []) # no contents changed in current level!
        if len(self.newFilesPaths) > 0:
            self.level.parent.changed.emit(levels.FileCreateDeleteEvent(None, self.newFilesPaths))
 
class InsertElementsCommand(QtGui.QUndoCommand):
    """A specialized command to insert elements into an existing container."""
    
    def __init__(self, level, parentId, row, insertedIds, text='insert elements'):
        """Create the command for inserting elements into *parentId* at row index *row*.
        
        *insertedIds* is the IDs list of the elements to be inserted. This will lead
        to unpredictable problems if the needed position range is not free; use insertElements
        instead."""
        super().__init__()
        self.row = row
        self.level = level
        self.parentId = parentId
        contents = level.get(parentId).contents
        firstPosition = 1 if row == 0 else contents.positions[row-1]+1
        import itertools
        self.insertions = list(zip(itertools.count(start=firstPosition), insertedIds))
        
    def redo(self):
        self.level.insertChildren(self.parentId, self.insertions)
        self.level.emitEvent(contentIds = (self.parentId, ))
        
    def undo(self):
        self.level.removeChildren(self.parentId, list(zip(*self.insertions))[0])
        self.level.emitEvent(contentIds = (self.parentId, ))

def insertElements(level, parentId, row, insertedIds, text = None):
    """Safely insert elements into a parent container.
    
    This method changes positions of subsequent elements, if necessary."""
    from ..application import stack
    stack.beginMacro(text)
    parent = level.get(parentId)
    if len(parent.contents) > row:
        firstPos = 1 if row == 0 else parent.contents.positions[row-1]+1
        lastPosition = firstPos + len(insertedIds) - 1
        shift = lastPosition - parent.contents.positions[row] + 1
        if shift > 0:
            posCommand = ChangePositionsCommand(level, parentId,
                                                parent.contents.positions[row:],
                                                shift)
            stack.push(posCommand)
    insertCommand = InsertElementsCommand(level, parentId, row, insertedIds)
    stack.push(insertCommand)
    stack.endMacro()
    
class RemoveElementsCommand(QtGui.QUndoCommand):
    """Remove some elements from a single parent."""
    def __init__(self, level, parentId, positions, text = None):
        super().__init__()
        if text:
            self.setText(text)
        self.level = level
        self.parentId = parentId
        self.positions = positions
        parent = level.get(parentId)
        self.childIds = [parent.contents.getId(position) for position in positions]
        
    def redo(self):
        self.level.removeChildren(self.parentId, self.positions)
        self.level.emitEvent(contentIds= (self.parentId,) )
    
    def undo(self):
        self.level.insertChildren(self.parentId, list(zip(self.positions, self.childIds)))
        self.level.emitEvent(contentIds= (self.parentId,) )

def removeElements(level, parentId, positions, text = None):
    """Remove elements from a parent and intelligently adjust subsequent positions.
    
    If there is an element following the last one deleted, and that element's position
    is the previous one's plus 1, then positions of subsequent elements are reduced
    to fit."""
    from .. import application
    import itertools
    parent = level.get(parentId)
    positions = sorted(positions)
    lastRemovePosition = positions[-1]
    lastRemoveIndex = parent.contents.positions.index(lastRemovePosition)
    for i,p1,p2 in zip(
        itertools.count(start=1),
        reversed(positions),
        reversed(parent.contents.positions[lastRemoveIndex-len(positions):lastRemoveIndex+1])):
        if p1 == p2:
            shift = -i
        else:
            break
            
                 
    if len(parent.contents) > lastRemoveIndex+1 and parent.contents.positions[lastRemoveIndex+1] == positions[-1] + 1:
        shiftPositions = parent.contents.positions[lastRemoveIndex+1:]
    else:
        shiftPositions = None
    removeCommand = RemoveElementsCommand(level, parentId, positions, text)
    application.stack.beginMacro(text)
    application.stack.push(removeCommand)
    if shiftPositions:
        posCommand = ChangePositionsCommand(level, parentId, shiftPositions, shift)
        application.stack.push(posCommand)
    application.stack.endMacro()
    
class ChangeMajorFlagCommand(QtGui.QUndoCommand):
    def __init__(self, level, ids):
        super().__init__()
        self.level = level
        self.previous = {id: level.get(id).major for id in ids}
    
    def redo(self):
        for id, prev in self.previous.items():
            self.level.get(id).major = not prev
        if self.level is levels.real:
            write.setMajor([id, not prev] for id,prev in self.previous.items())
        self.level.emitEvent(list(self.previous.keys()))
    
    def undo(self):
        for id, prev in self.previous.items():
            self.level.get(id).major = prev
        if self.level is levels.real:
            write.setMajor(list(self.previous.items()))
        self.level.emitEvent(list(self.previous.keys()))

class ChangePositionsCommand(QtGui.QUndoCommand):
    """Change the positions of several elements below the same parent. Checks for
    invalid changes."""
    def __init__(self, level, parentId, oldPositions, shift):
        super().__init__()
        self.level = level
        self.parentId = parentId
        self.oldPositions = level.get(parentId).contents.positions[:]
        self.newPositions = list(map(lambda p:p + shift if p in oldPositions else p, self.oldPositions))
        if any(i <=0 for i in self.newPositions):
            raise levels.ConsistencyError('Positions may not drop below one')
        if len(set(self.oldPositions)) != len(set(self.newPositions)):
            raise levels.ConsistencyError('Position conflict: cannot perform change')
        if self.level is levels.real:
            self.changes = [ (p,p+shift) for p in oldPositions ]
        
    def redo(self):
        parent = self.level.get(self.parentId)
        parent.contents.positions = self.newPositions[:]
        if self.level is levels.real:
            db.write.changePositions(self.parentId, self.changes)
        self.level.emitEvent(contentIds = (self.parentId,))
    
    def undo(self):
        parent = self.level.get(self.parentId)
        parent.contents.positions = self.oldPositions[:]
        if self.level is levels.real:
            db.write.changePositions(self.parentId, [(b,a) for a,b in self.changes])
        self.level.emitEvent(contentIds = (self.parentId,))