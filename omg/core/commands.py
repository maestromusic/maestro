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

"""This module contains common QUndoCommands for modifying Elements in Levels."""

import itertools

from PyQt4 import QtCore, QtGui

from . import levels, tags, flags
from .elements import ContentList
from .. import database as db, logging, utils
from ..modify import real as modifyReal
from ..database import write

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)


class CommitCommand(QtGui.QUndoCommand):
    """The CommitCommand is used to commit the state of elements of one level into the parent level.
    
    It takes a level and list of element IDs and ensures that those elements (and all descendants)
    - exist in the parent level, and
    - are the same there than in this level.
    Tags, flags, contents, the "major" property, and so on are adjusted in the parent level.

    The most complex case happens when the parent level is levels.real; in that case,
    - temporary elements must be given positive IDs,
      and the IDs in the child level must also be changed,
    - the database has to be updated,
    - the filesystem has to be updated.
    """
    
    def __init__(self, level, ids, text=None):
        """Sets up a commit command for the given *ids* in *level*."""
        super().__init__(text)
        self.level = level
        # add IDs of all descendants to ensure a consistent commit
        ids = self.level.children(ids)
        self.real = (level.parent is levels.real)  # a handy shortcut
        if self.real:
            self.newInDatabase = [ id for id in ids if id < 0 ]
            self.realFileChanges = {} # maps (new) path -> changes on filesystem
            self.idMap = None # maps tempId -> realId
        else:
            # if non-real parent, newId is the identity function
            self.newId = self.oldId = lambda x : x
        self.newElements = [] # elements which are not in parent level before the commit
        self.newFilesUrls = [] #  the URLs of new files; for FS module
        self.flagChanges, self.tagChanges, self.contentsChanges = {}, {}, {}
        self.majorChanges, self.urlChanges = {}, {}
        self.ids, self.contents = [], []  # for the events
        for id in ids:
            element, contents = self.recordChanges(id)
            if element:
                self.ids.append(id)
            if contents:
                self.contents.append(id)
    
    def recordChanges(self, id):
        """Internally recodrs changes for a single element.
        
        The function returns a pair of booleans indicating whether whether the elements itself and
        its contents have changed, respectively.
        """
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
                oldUrl = oldEl.url
        else:
            changeElement = True
            self.newElements.append(id)
            oldTags = None
            oldFlags = []
            if myEl.isContainer():
                oldMajor = None
                oldContents = ContentList()
            else:
                oldUrl = levels.urlFromId(id)
                self.newFilesUrls.append(myEl.url)
        if oldTags != myEl.tags:
            changes = tags.TagDifference(oldTags, myEl.tags)
            self.tagChanges[id] = changes
            if self.real and myEl.isFile():
                if id not in self.newElements:
                    if not changes.onlyPrivateChanges():
                        self.realFileChanges[myEl.url] = changes
                else:
                    if hasattr(myEl, "fileTags"):
                        fileTags = myEl.fileTags # set by Element drop into editor; avoids costly disk access
                    else:
                        from .. import filebackends
                        realFile = filebackends.get(myEl.url)
                        realFile.read()
                        fileTags = realFile.tags
                    fileChanges = tags.TagDifference(fileTags, myEl.tags)
                    if not fileChanges.onlyPrivateChanges():
                        self.realFileChanges[myEl.url] = fileChanges
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
        elif oldUrl != myEl.url:
            self.urlChanges[id] = (oldUrl, myEl.url)
            changeElement = True 
        return changeElement, changeContents
            
    def redo(self):
        """Do the commit.
        
        The redo function operates in three main steps:
        - if parent level is real, change IDs of temporary elements
        - update the elements in the parent level
        - if level is real, update database, rename files, update file's tags
        """
        if self.real:
            #  create new elements in DB to obtain id map, and change IDs in current level 
            db.transaction()
            if self.idMap is None:
                #  first redo -> prepare id mapping
                self.idMap = modifyReal.createNewElements(self.level, self.newInDatabase)
                self.newId = utils.dictOrIdentity(self.idMap)
                self.oldId = utils.dictOrIdentity({b:a for a,b in self.idMap.items() })
                #  update contentsChanges to use the new ids
                for _, newContents in self.contentsChanges.values():
                    newContents.ids[:] = map(self.newId, newContents.ids)
            else:
                modifyReal.createNewElements(self.level, self.newInDatabase, self.idMap)
            #  change IDs of new elements in both current and parent level
            for id in self.newInDatabase:
                self.level._changeId(id, self.newId(id))
                if id in self.level.parent:
                    self.level.parent._changeId(id, self.newId(id))
            #  TODO: what about child levels!?
        # ** At this point, all elements have their IDs, if applicable **
        for id in set(self.ids + self.contents):
            # Add/update elements in parent level
            nid = self.newId(id)
            elem = self.level.elements[nid]
            if id in self.newElements:
                copy = elem.copy()
                copy.level = self.level.parent
                self.level.parent.elements[nid] = copy
            else:
                pElem = self.level.parent.elements[nid]
                if id in self.majorChanges:
                    pElem.major = self.majorChanges[id][1]
                if id in self.tagChanges:
                    self.tagChanges[id].apply(pElem.tags)
                if id in self.flagChanges:
                    self.flagChanges[id].apply(pElem.flags)
                if id in self.contentsChanges:
                    oldContents, newContents = self.contentsChanges[id]
                    pElem.contents = newContents.copy()
                    # Update parents
                    for child in oldContents.ids:
                        if child not in newContents.ids:
                            self.level.parent.get(child).parents.remove(id)
                    for child in newContents.ids:
                        if child not in oldContents.ids:
                            self.level.parent.get(child).parents.append(id)
                if id in self.urlChanges:
                    pElem.url = self.urlChanges[id][1]
        # ** At this point, elements in parent level equal those in current level **
        if self.real:
            if len(self.majorChanges) > 0:
                db.write.setMajor((self.newId(id), newMajor) for id,(_,newMajor) in self.majorChanges.items())
            if len(self.contentsChanges) > 0:
                modifyReal.changeContents({self.newId(id):changes for id, changes in self.contentsChanges.items()})
            if len(self.tagChanges) > 0:
                def dbDiff(id):
                    """Return a modified TagDifference for the DB, not the level itself.
                    
                    From the DB's perspective, the TagDifference of a newly created element is from
                    an empty tag storage to the current one, while self.tagChanges only captures
                    the difference between the two level states.
                    """ 
                    if id in self.newInDatabase:
                        return tags.TagDifference(None, self.level.get(self.newId(id)).tags)
                    else:
                        return self.tagChanges[id]
                modifyReal.changeTags({self.newId(id):dbDiff(id) for id in self.tagChanges.keys()})
            if len(self.flagChanges) > 0:
                modifyReal.changeFlags({self.newId(id):diff for id,diff in self.flagChanges.items()})            
            db.commit()
            if len(self.urlChanges) > 0:
                levels.real._renameFiles({self.newId(id):diff for id,diff in self.urlChanges.items()})
            for url, changes in self.realFileChanges.items():
                logger.debug("changing file tags: {0}-->{1}".format(url, changes))
                modifyReal.changeFileTags(url, changes)
        # ** At this point, database and filesystem have been updated **
        self.level.parent.emitEvent([self.newId(id) for id in self.ids], [self.newId(id) for id in self.contents])
        self.level.emitEvent([self.newId(id) for id in self.ids], [])       
        if len(self.newFilesUrls) > 0:
            # specialized event for filesystem module
            self.level.parent.changed.emit(levels.FileCreateDeleteEvent(self.newFilesUrls))
        
    def undo(self):
        """Undo the commit.
        
        Performs inverse operations as redo() in reverse order:
        - restore file tags, rename files, reverse DB changes
        - restore elements in parent level
        - if parent level is real: restore original IDs
        """
        
        if self.real:
            for url, changes in self.realFileChanges.items():
                logger.debug("reverting file tags: {0}<--{1}".format(url, changes))
                modifyReal.changeFileTags(url, changes, reverse=True)
            if len(self.urlChanges) > 0:
                levels.real._renameFiles({self.newId(id):(b,a) for id,(a,b) in self.urlChanges.items()})
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
        # ** At this point, database and filesystem are in the original state **
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
                    oldContents, newContents = self.contentsChanges[id]
                    pElem.contents = oldContents.copy()
                    # Update parents
                    for child in oldContents.ids:
                        if child not in newContents.ids:
                            self.level.parent.get(child).parents.append(id)
                    for child in newContents.ids:
                        if child not in oldContents.ids:
                            self.level.parent.get(child).parents.remove(id)               
                            
                if id in self.urlChanges:
                    pElem.url = self.urlChanges[id][0]
        # ** At this point, the parent level is in its original state
        if self.real:
            for id in self.newInDatabase:
                self.level._changeId(self.newId(id), id)
                if self.newId(id) in self.level.parent:
                    self.level.parent._changeId(self.newId(id), id)
            db.commit()
        # **  At this point, IDs have been reset **
        self.level.parent.emitEvent(self.ids, self.contents)
        self.level.emitEvent(self.ids, [])
        if len(self.newFilesUrls) > 0:
            self.level.parent.changed.emit(levels.FileCreateDeleteEvent(None, self.newFilesUrls))


class InsertElementsCommand(QtGui.QUndoCommand):
    """A command to insert elements into an existing container."""
    
    def __init__(self, level, parent, row, elements, text=None):
        """Create the command for inserting *elements* into *parent* at index *row*."""
        
        super().__init__()
        if text is None:
            text = translate(__name__, "insert")
        self.setText(text)
        self.level = level
        self.parent = parent
        oldContents = parent.contents
        firstPosition = 1 if row == 0 else oldContents.positions[row-1]+1
        self.insertions = list(zip(itertools.count(start=firstPosition), elements))
        
    def redo(self):
        self.level._insertContents(self.parent, self.insertions)
        self.level.emitEvent(contentIds = (self.parent.id, ))
        
    def undo(self):
        self.level._removeContents(self.parent, list(zip(*self.insertions))[0])
        self.level.emitEvent(contentIds = (self.parent.id, ))


class RemoveElementsCommand(QtGui.QUndoCommand):
    """Remove some elements from a single parent."""
    
    def __init__(self, level, parent, positions, text=None):
        """Create the command to remove elements at *positions* under *parent* in *level*."""
        
        super().__init__()
        if text is None:
            text = translate(__name__, "remove")
        self.setText(text)
        self.level = level
        self.parent = parent
        self.positions = positions
        self.children = [self.level.get(parent.contents.getId(position))
                         for position in positions]
        
    def redo(self):
        self.level._removeContents(self.parent, self.positions)
        self.level.emitEvent(contentIds=(self.parent.id,) )
    
    def undo(self):
        self.level._insertContents(self.parent, list(zip(self.positions, self.children)))
        self.level.emitEvent(contentIds= (self.parent.id,) )

 
class ChangeMajorFlagCommand(QtGui.QUndoCommand):
    """A command to change the major flag of several elements."""
    
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
    def __init__(self, level, parent, oldPositions, shift):
        super().__init__()
        self.level = level
        self.parent = parent
        self.oldPositions = parent.contents.positions[:]
        self.newPositions = list(map(lambda p:p + shift if p in oldPositions else p, self.oldPositions))
        if any(i <=0 for i in self.newPositions):
            raise levels.ConsistencyError('Positions may not drop below one')
        if len(set(self.oldPositions)) != len(set(self.newPositions)):
            raise levels.ConsistencyError('Position conflict: cannot perform change')
        if self.level is levels.real:
            self.changes = [ (p,p+shift) for p in oldPositions ]
        
    def redo(self):
        self.parent.contents.positions = self.newPositions[:]
        if self.level is levels.real:
            db.write.changePositions(self.parent.id, self.changes)
        self.level.emitEvent(contentIds=(self.parent.id,))
    
    def undo(self):
        self.parent.contents.positions = self.oldPositions[:]
        if self.level is levels.real:
            db.write.changePositions(self.parent.id, [(b,a) for a,b in self.changes])
        self.level.emitEvent(contentIds = (self.parent.id,))