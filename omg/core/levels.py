# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

import weakref

from PyQt4 import QtCore, QtGui

from . import data, elements, tags, flags
from .nodes import Wrapper
from .. import application, filebackends, database as db, logging

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)


allLevels = weakref.WeakSet()

# The two special levels
real = None
editor = None


def init():
    """Initialize the level module. Creates the real and editor levels."""
    global real,editor
    from . import reallevel
    real = reallevel.RealLevel()
    editor = Level('EDITOR',real)
    

class ElementGetError(RuntimeError):
    """Error indicating that some elements failed to be loaded by some level. *params* is a list of either
    ids or urls for which no element could be loaded."""
    def __init__(self, level, params, text="Could not load some elements"):
        super().__init__(text)
        self.level = level
        self.params = params
        
    def __str__(self):
        return "{} ({}): {}".format(super().__str__(), self.level, self.params) 


class RenameFilesError(RuntimeError):
    """An error that is raised when renaming files fails."""
    
    def __init__(self, oldUrl, newUrl, message):
        super().__init__("Error renaming '{}' to '{}': '{}'".format(oldUrl, newUrl, message))
        self.oldUrl = oldUrl
        self.newUrl = newUrl
        self.message = message
        
    def displayMessage(self):
        from ..gui import dialogs
        title = translate("RenameFilesError", "Error renaming file")
        msg = translate("RenameFilesError", "Could not rename '{}' to '{}':\n"
                                  "{}").format(self.oldUrl, self.newUrl, self.message)
        dialogs.warning(title, msg)


class ConsistencyError(RuntimeError):
    """Error signaling a consistency violation of element data."""
    pass


class LevelChangedEvent(application.ChangeEvent):
    """Event that is emitted when elements on a level change.
    
    The event stores the ids of changed elements in several sets, grouped by the type of the change:
        - dataIds: tags, flags, parents, data etc. have changed,
        - contentIds: contents have changed
        - addedIds, removedIds: have been added to/removed from the level
        - dbAddedIds, dbRemovedIds: have been added to/removed from the database (such events are sent to
          all levels, not only the real-level).
        
    The constructor accepts these sets as keyword-arguments.
    Note: ids in 'removedIds' will be removed from all other sets.
    """
    # Attributes which store a list of element ids; used by the generic implementation of merge and filtered.
    _idAttributes = ('dataIds', 'contentIds', 'addedIds', 'removedIds', 'dbAddedIds', 'dbRemovedIds')
       
    def __init__(self, **args):
        super().__init__()
        for attr in self._idAttributes:
            if attr in args and len(args[attr]) > 0:
                ids = args[attr]
                if not isinstance(ids, set):
                    ids = set(ids)
                setattr(self, attr, ids)
        if len(self.removedIds) > 0:
            self._clearIds(self.removedIds)
            
    def __getattr__(self, attr):
        if attr in self._idAttributes:
            return set()
        else: raise AttributeError("LevelChangedEvent has no attribute '{}'.".format(attr))
        
    def _clearIds(self, ids):
        """Remove *ids* from all idLists except 'removedIds'.""" 
        for attr in self._idAttributes:
            if attr != 'removedIds':
                getattr(self, attr).difference_update(ids)
        
    def merge(self, other):
        if type(other) is type(self): # do not merge with subclasses because they might carry more data
            for attr in self._idAttributes:
                if len(getattr(other, attr)) > 0:
                    idList = getattr(other, attr)
                    if len(getattr(self, attr)) > 0:
                        getattr(self, attr).update(idList)
                    else: setattr(self, attr, idList)
            if len(other.removedIds) > 0:
                self._clearIds(other.removedIds)
            return True
        else: return False
        
    def forwardEvent(self, level):
        """Check whether this event should be forwarded to *level* (which must be a sublevel of the level
        where the event was originally emitted). If so, return a version of the event to be forwarded (this
        can be the event or a modified copy of it). Otherwise return None.
        Note: The resulting event must be usable on a different level, which is not a problem as long as
        events only use ids.
        """
        if len(self.addedIds) == 0 and len(self.removedIds) == 0 and \
            all(id not in self.dataIds and id not in self.contentIds for id in level.elements):
            return self
        idLists = {}
        
        if len(self.dataIds) > 0:
            idLists['dataIds'] = self.dataIds.difference(level.elements.keys())
        if len(self.contentIds) > 0:
            idLists['contentIds'] = self.contentIds.difference(level.elements.keys())
        # Never forward addedIds/removedIds
        # Always forward dbAddedIds/dbRemovedIds completely
        if len(self.dbAddedIds) > 0:
            idLists['dbAddedIds'] = self.dbAddedIds
        if len(self.dbRemovedIds) > 0:
            idLists['dbRemovedIds'] = self.dbRemovedIds
        
        if any(len(l) > 0 for l in idLists.values()):
            return LevelChangedEvent(**idLists)
        else: return None
        
    def __repr__(self):
        abbreviations = {'dataIds': 'D', 'contentIds': 'C', 'addedIds': 'L+', 'removedIds': 'L-',
                         'dbAddedIds': 'DB+', 'dbRemovedIds': 'DB-'}
        formattedLists = []
        for attr in self._idAttributes:
            if len(getattr(self, attr)) > 0:
                formattedLists.append("{}:{}".format(abbreviations[attr],
                                                     ",".join(str(id) for id in getattr(self, attr))))
        return "<{}: {}>".format(type(self).__name__, "; ".join(formattedLists))


class GenericLevelCommand:
    """Generic UndoCommand that is used by all undoable methods of Level. It will call *redoMethod* with
    *redoArgs* on redo an handle undos analogously. *text* is an optional text for the command.
    """
    def __init__(self, redoMethod, redoArgs, undoMethod, undoArgs, text=''):
        self.text = text
        self.redoMethod, self.redoArgs = redoMethod, redoArgs
        self.undoMethod, self.undoArgs = undoMethod, undoArgs
            
    def redo(self):
        self.redoMethod(**self.redoArgs)
            
    def undo(self):
        self.undoMethod(**self.undoArgs)
        

class Level(application.ChangeEventDispatcher):
    """A collection of elements corresponding to a specific state.
    
    The "same" element (i.e. element with the same ID) might be present in different levels with
    different states (different tags, flags, contents, ...). Via the concept of a parent level,
    these are connected. The topmost levels is the "real" level reflecting the state of the
    database and the filesystem. Child levels can commit their changes into the parent level and
    load new elements from there.
    A level offers undo-aware methods to alter elements as well as content relations. The according
    bare methods not handling undo/redo are marked by a leading underscore.
    If elements change in a level, its signal *changed* is emitted.
    
    Constructor arguments:
    
        - *name*: each level has a name for debugging purposes,
        - *parent*: the parent level,
        - *stack*: the undostack which will be used by methods of this level (e.g. changeTags).
          Only levels which are only used in a modal dialog may use their own stack.
          
    """ 
    def __init__(self, name, parent, elements=None, stack=None):
        super().__init__()
        allLevels.add(self)
        self.name = name
        self.parent = parent
        if elements is None:
            self.elements = {}
        else: self.elements = {element.id: element.copy(level=self) for element in elements}
        self.stack = stack if stack is not None else application.stack
        
        # These are necessary to solve ticket #138
        self.lastInsertId = None      # last element into which something has been inserted
        self.lastInsertPositions = [] # positions of that element that have been inserted
    
    def emit(self, event):
        super().emit(event)
        for level in allLevels:
            if level.parent is self:
                forwardEvent = event.forwardEvent(level)
                if forwardEvent is not None:
                    level.emit(forwardEvent)
        
    def emitEvent(self, **args):
        """Simple shortcut to emit an LevelChangedEvent."""
        self.emit(LevelChangedEvent(**args))
    
    def __contains__(self, param):
        """Returns if the given element is loaded in this level.
        
        *param* may be either an ID or a URL. Note that if the element could be loaded from the
        parent but is not contained in this level, then *False* is returned.
        """
        if isinstance(param, int):
            return param in self.elements
        elif isinstance(param, filebackends.BackendURL):
            try:
                id = idFromUrl(param)
            except KeyError:
                return False
            return id in self.elements
        else:
            raise ValueError("param must be either ID or URL, not {} of type {}"
                             .format(param, type(param)))
  
    def __getitem__(self, key):
        if isinstance(key, int):
            return self.elements[key]
        elif isinstance(key, filebackends.BackendURL):
            return self.elements[idFromUrl(key)] # __getitem__ and idFromUrl may raise KeyErrors
        else:
            raise ValueError("param must be either ID or URL, not {} of type {}"
                             .format(key, type(key)))

    def _ensureLoaded(self, params):
        """Make sure that the elements specified by params (ids and/or urls) are loaded on this level or 
        any parent level."""
        missing = [param for param in params if param not in self]
        if len(missing) > 0:
            self.parent._ensureLoaded(missing)
    
    #TODO do something about this ugly correct parents stuff
    def _correctParents(self, element, changeLevel):
        # This does only work if element comes from a level that is an ancestor or descendant of self,
        # if element is not contained in any levels in between and not contained in this level.
        parentsToRemove = [parentId for parentId in element.parents
                           if parentId in self and element.id not in self[parentId].contents]
        if len(parentsToRemove) > 0 or changeLevel:
            # To be consistent with the case where no parents need to be removed, we do not change the
            # level attribute if not explicitly asked for it.
            element = element.copy(level=self if changeLevel else None)
            for parentId in parentsToRemove:
                element.parents.remove(parentId)
            
        return element
    
    def fetch(self, param):
        """Return the element specified by the id or url *param* from this level or the nearest parent level.
        Do not load the element onto this level. Correct the 'parents' attribute if the element is fetched
        from a parent level.
        """
        if param in self:
            return self[param]
        else: return self._correctParents(self.parent._fetch(param), changeLevel=False)
    
    def _fetch(self, param):
        """Like fetch, but do not correct the 'parents' attribute."""
        if param in self:
            return self[param]
        else: return self.parent._fetch(param)
    
    def fetchMany(self, params):
        """Fetch several elements by their id/url and return them."""
        self._ensureLoaded(params) # without this line all missing elements would be loaded separately.
        return [self.fetch(param) for param in params]
        
    def collect(self, param):
        """Return the element specified by the id or url *param* from this level. Load the element if it is
        not loaded yet."""
        return self.collectMany([param])[0]
    
    def collectMany(self, params):
        """Collect several elements by their id/url and return them."""
        self._ensureLoaded(params) # without this line all missing elements would be loaded separately.
        newElements = [self._correctParents(self.parent.fetch(param), changeLevel=True)
                       for param in params if param not in self]
        if len(newElements):
            self.addElements(newElements)
        return [self[param] for param in params]
  
    def files(self):
        """Return a generator of all files in this level."""
        return (element for element in self.elements.values() if element.isFile())
    
    # ===========================================================================
    # The following functions provide undo-aware implementations of level changes
    # ===========================================================================
    def addElements(self, elements):
        """Undoably add elements to this level."""
        command = GenericLevelCommand(redoMethod=self._addElements,
                                      redoArgs={"elements": elements},
                                      undoMethod=self._removeElements,
                                      undoArgs={"elements": elements},
                                      text=self.tr("Add elements"))
        self.stack.push(command)
        
    def removeElements(self, elements):
        """Undoably remove elements from this level."""
        command = GenericLevelCommand(redoMethod=self._removeElements,
                                      redoArgs={"elements": elements},
                                      undoMethod=self._addElements,
                                      undoArgs={"elements": elements},
                                      text=self.tr("Remove elements"))
        self.stack.push(command)

    def createContainer(self, tags=None, flags=None, data=None, major=True, contents=None):
        """Create a new container with the given properties and load it into this level.
        
        Can be undone. Returns the new container.
        """ 
        container = elements.Container(level=self,
                                       id=db.nextId(),
                                       major=major, 
                                       tags=tags,
                                       flags=flags,
                                       data=data)
        self.stack.beginMacro(self.tr("Create container"))
        self.addElements([container])
        # addElements on real level does not allow for contents
        # Furthermore this will also update the 'parents' attribute of all contents
        if contents is not None:
            self.setContents(container, contents)
        self.stack.endMacro()
        return container
        
    def changeTags(self, changes):
        """Change tags of elements. *changes* maps elements to tags.TagDifference objects.
        On real level this method might raise a TagWriteError if writing (some or all) tags to the
        filesystem fails.
        """
        self._changeSomething(self._changeTags, changes, self.tr("change tags"))
        
    def changeFlags(self, changes):
        """Change flags of elements. *changes* maps elements to flags.FlagDifference objects."""
        self._changeSomething(self._changeFlags, changes, self.tr("change flags"))

    def changeData(self, changes):
        """Change flags of elements. *changes* maps elements to data.DataDifference objects."""
        self._changeSomething(self._changeData, changes, self.tr("change data"))
    
    def _changeSomething(self,method,changes,text):
        """Helper for changeTags, changeFlags and similar methods which only need to undoably call
        *method* with *changes* (or its inverse). *text* is used as text for the created undocommand."""
        if len(changes) > 0:
            inverseChanges = {elem:diff.inverse() for elem,diff in changes.items()}
            command = GenericLevelCommand(redoMethod=method,
                                          redoArgs={"changes" : changes},
                                          undoMethod=method,
                                          undoArgs={"changes": inverseChanges},
                                          text=text)
            self.stack.push(command)
        
    def setCovers(self, coverDict):
        """Set the covers for one or more elements.
        
        The action can be undone. *coverDict* must be a dict mapping elements to either
        a cover path or a QPixmap or None.
        """
        from . import covers
        self.stack.push(covers.CoverUndoCommand(self, coverDict))
    
    def setMajorFlags(self, elemToMajor):
        """Set the major flags of one or more containers.
        
        The action can be undone. *elemToMajor* maps elements to boolean values indicating the
        desired major state.
        """
        if len(elemToMajor) > 0:
            inverseChanges = {elem: (not major) for (elem, major) in elemToMajor.items()}
            command = GenericLevelCommand(redoMethod=self._setMajorFlags,
                                          redoArgs={"elemToMajor" : elemToMajor},
                                          undoMethod=self._setMajorFlags,
                                          undoArgs={"elemToMajor" : inverseChanges},
                                          text=self.tr("change major property"))
            self.stack.push(command)
    
    def changeContents(self, contentDict):
        """Set contents according to *contentDict* which maps parents to content lists."""
        if len(contentDict) > 0:
            inverseChanges = {parent: parent.contents for parent in contentDict}
            command = GenericLevelCommand(redoMethod=self._changeContents,
                                          redoArgs={"contentDict": contentDict},
                                          undoMethod=self._changeContents,
                                          undoArgs={"contentDict": inverseChanges},
                                          text=self.tr("change contents"))
            self.stack.push(command)
        
    def setContents(self, parent, contents):
        """Set the content list of *parent*."""
        if not isinstance(contents, elements.ContentList):
            contents = elements.ContentList.fromList(contents)
        command = GenericLevelCommand(redoMethod=self._setContents,
                                      redoArgs={"parent": parent,
                                                "contents": contents},
                                      undoMethod=self._setContents,
                                      undoArgs={"parent": parent,
                                                "contents": parent.contents},
                                      text=self.tr("set contents"))
        self.stack.push(command)
        
    def insertContents(self, parent, insertions):
        """Insert contents with predefined positions into a container.
        
        *insertions* is a list of (position, element) tuples.
        """
        command = GenericLevelCommand(redoMethod=self._insertContents,
                                      redoArgs={"parent" : parent,
                                                "insertions" : insertions},
                                      undoMethod=self._removeContents,
                                      undoArgs={"parent" : parent,
                                                "positions" : [pos for pos,_ in insertions]},
                                      text=self.tr("insert contents"))
        self.stack.push(command)
        
    def insertContentsAuto(self, parent, index, elements):
        """Undoably insert elements into a parent container.
        
        *parent* is the container in which to insert the elements *elements*. The insert index
        (not position) is given by *index*; the position is automatically determined, and
        subsequent elements' positions are shifted if necessary.
        """
        self.stack.beginMacro(self.tr("insert contents"))
        firstPos = 1 if index == 0 else parent.contents.positions[index-1] + 1
        if len(parent.contents) > index:
            #  need to alter positions of subsequent elements
            lastPosition = firstPos + len(elements) - 1
            shift = lastPosition - parent.contents.positions[index] + 1
            if shift > 0:
                self.shiftPositions(parent, parent.contents.positions[index:], shift)
        self.insertContents(parent, list(enumerate(elements, start=firstPos)))
        self.stack.endMacro()
    
    def removeContents(self, parent, positions):
        """Undoably remove children with *positions* from *parent*."""
        undoInsertions = [(pos, self[parent.contents.at(pos)]) for pos in positions]
        command = GenericLevelCommand(redoMethod=self._removeContents,
                                      redoArgs={"parent" : parent,
                                                "positions" : positions},
                                      undoMethod=self._insertContents,
                                      undoArgs={"parent" : parent,
                                                "insertions" : undoInsertions},
                                      text=self.tr("remove contents"))
        self.stack.push(command)

    def removeContentsAuto(self, parent, positions=None, indexes=None):
        """Undoably remove contents under the container *parent*.
        
        The elements to remove may be given either by specifying their *positions* or
        *indexes*.        
        If there are subsequent elements behind the deleted ones, and the position of the first of
        those is one more than the position of the last deleted element (i.e., there is no gap),
        then their positions will be diminished such that there's no gap afterwards, too.
        """
        if positions is None:
            positions = ( parent.contents.positions[i] for i in indexes )
        positions = sorted(positions)
        lastRemovePosition = positions[-1]
        lastRemoveIndex = parent.contents.positions.index(lastRemovePosition)
        shiftPositions = None
        if len(parent.contents) > lastRemoveIndex+1 \
                and parent.contents.positions[lastRemoveIndex+1] == positions[-1] + 1:
            shiftPositions = parent.contents.positions[lastRemoveIndex+1:]
            for i in range(1, len(positions)+1):
                if positions[-i] == parent.contents.positions[lastRemoveIndex+1-i]:
                    shift = -i
                else:
                    break
        self.stack.beginMacro(self.tr("remove contents"))
        self.removeContents(parent, positions) 
        #TODO: when the positions are not connected, using several different shifts might be more
        # appropriate
        if shiftPositions is not None:
            self.shiftPositions(parent, shiftPositions, shift)
        self.stack.endMacro()
    
    def shiftPositions(self, parent, positions, shift):
        """Undoably shift the positions of several children of a parent by the same amount.
        
        If this can not be done without conflicts, a ConsistencyError is raised.
        """
        untouched = set(parent.contents.positions) - set(positions)
        changes = {pos:pos+shift for pos in positions}
        if any(i <= 0 for i in changes.values()):
            raise ConsistencyError('Positions may not drop below one')
        if any(pos in untouched for pos in changes.values()):
            raise ConsistencyError('Position conflict: cannot perform change')
        command = GenericLevelCommand(redoMethod=self._changePositions,
                                      redoArgs={"parent" : parent,
                                                "changes" : changes},
                                      undoMethod=self._changePositions,
                                      undoArgs={"parent" : parent,
                                                "changes" : {b:a for a,b in changes.items()}
                                                },
                                      text=self.tr("change positions"))
        self.stack.push(command)
    
    def renameFiles(self, renamings):
        """Rename several files. *renamings* maps element to (oldUrl, newUrl) paths.
        
        On the real level, this can raise a FileRenameError.
        """
        if len(renamings):
            reversed =  {file:(newUrl, oldUrl) for  (file, (oldUrl, newUrl)) in renamings.items()}
            command = GenericLevelCommand(redoMethod=self._renameFiles,
                                          redoArgs={"renamings" : renamings},
                                          undoMethod=self._renameFiles,
                                          undoArgs={"renamings": reversed},
                                          text=self.tr("rename files"))
            self.stack.push(command)
    
    def commit(self, elements=None):
        """Undoably commit given *elements* (or everything, if not specified) into the parent level.
        """
        if elements is None:
            elements = self.elements.values()
        if len(elements) == 0:
            return
        self.stack.beginMacro(self.tr("commit"), transaction=self.parent is real)
      
        if self.parent is real:
            # First load all missing files
            for element in elements:
                if element.isFile() and element.id not in real:
                    real.collect(element.id if element.isInDb() else element.url)
            
            # 1. Collect data
            # 2. Write file tags (do this first because it is most likely to fail). Private tags must
            #    be excluded first, because files have not yet been added to the database. Tags must be
            #    changed before adding files to the db, because files on real might contain external tags.
            # 3. Add elements to database
            # 4. Change remaining tags (i.e. container tags and private tags)
            # 5. change other stuff (same as if self.parent is not real)
            
            # 1. Collect data
            addToDbElements = [] # Have to be added to the db (this does overlap oldElements below)
            fileTagChanges = {}
            remainingTagChanges = {}
            for element in elements:
                if element.isFile():
                    inParent = self.parent[element.id]
                    if element.isInDb():
                        newTags = element.tags.copy()
                    else:
                        addToDbElements.append(inParent)
                        if element.tags.containsPrivateTags():
                            newTags = element.tags.withoutPrivateTags()
                            remainingTagChanges[inParent] = tags.TagDifference(
                                                    additions=list(element.tags.privateTags().getTuples()))
                        else: newTags = element.tags.copy()
                    if inParent.tags != newTags:
                        fileTagChanges[inParent] = tags.TagStorageDifference(inParent.tags, newTags)
                else: # containers
                    if element.isInDb():
                        inParent = self.parent[element.id]
                        remainingTagChanges[inParent] = tags.TagStorageDifference(inParent.tags,
                                                                                  element.tags.copy())
                    else:
                        addToDbElements.append(element.copy(level=self.parent))
                        # we do not have to change tags of new containers
                        
            # 2.-4.
            try:
                real.changeTags(fileTagChanges)
            except (filebackends.TagWriteError, OSError) as e:
                self.stack.abortMacro()
                raise e
            real.addToDb(addToDbElements)
            real.changeTags(remainingTagChanges)
        else:
            self.parent.addElements([element.copy(level=self.parent)
                                     for element in elements if element.id not in self.parent])
        
        # 5. Change other stuff
        oldElements = (element for element in elements if element.id in self.parent)
        contentChanges = {}
        tagChanges = {}
        flagChanges = {}
        dataChanges = {}
        majorChanges = {}
        urlChanges = {}
        # It is important to copy lists etc. in the following because this level will continue to use 
        # the old elements.
        for element in oldElements:
            inParent = self.parent[element.id]
            # Tag changes have been done already if parent is real
            if self.parent is not real and element.tags != inParent.tags:
                tagChanges[inParent] = tags.TagStorageDifference(inParent.tags, element.tags.copy())
            if element.flags != inParent.flags:
                flagChanges[inParent] = flags.FlagListDifference(inParent.flags, element.flags[:])
            if element.data != inParent.data:
                dataChanges[inParent] = data.DataDifference(inParent.data, element.data.copy())
            if element.isContainer():
                if element.contents != inParent.contents:
                    contentChanges[inParent] = element.contents.copy()
                if element.major != inParent.major:
                    majorChanges[inParent] = element.major
            else:
                if element.url != inParent.url:
                    urlChanges[inParent] = (inParent.url, element.url)
                
        self.parent.changeContents(contentChanges)
        self.parent.changeTags(tagChanges)
        self.parent.changeFlags(flagChanges)
        self.parent.changeData(dataChanges)
        self.parent.setMajorFlags(majorChanges)
        self.parent.renameFiles(urlChanges)
        
        self.stack.endMacro()
    
    # ====================================================================================
    # The following functions implement no undo/redo handling and should be used with care
    # ====================================================================================   
    def _addElements(self, elements):
        for element in elements:
            assert element.id not in self and element.level is self
            self.elements[element.id] = element
        if len(elements) > 0:
            self.emit(LevelChangedEvent(addedIds=[element.id for element in elements]))
            
    def _removeElements(self, elements):
        for element in elements:
            if element.id in self.elements: # *elements* might contain some elements more than once
                del self.elements[element.id]
        if len(elements) > 0:
            self.emit(LevelChangedEvent(removedIds=[element.id for element in elements]))
            
    def _applyDiffs(self, changes):
        """Given the dict *changes* mapping elements to Difference objects (e.g. tags.TagDifference, apply
        these differences to the elements.
        """
        for element, diff in changes.items():
            diff.apply(element)
        self.emitEvent(dataIds=[element.id for element in changes])
        
    # On real level these methods are implemented differently
    _changeTags = _applyDiffs
    _changeFlags = _applyDiffs
    _changeData = _applyDiffs

    def _setData(self,type,elementToData):
        """For each (element, datalist) tuple in *elementToData* change the data of element of type *type*
        to datalist. Do not change data of other types.
        """
        for element,data in elementToData.items():
            if data is not None:
                if isinstance(data,tuple):
                    element.data[type] = data
                else: element.data[type] = tuple(data)
            elif type in element.data:
                del element.data[type]
        self.emitEvent(dataIds=[element.id for element in elementToData])
    
    def _setMajorFlags(self, elemToMajor):
        """Set major of several elements."""
        for elem, major in elemToMajor.items():
            elem.major = major
        self.emitEvent(dataIds=[elem.id for elem in elemToMajor])
    
    def _changeContents(self, contentDict):
        """Set contents according to *contentDict* which maps parents to content lists."""
        for parent, contents in contentDict.items():
            # Note that the created events will be merged if this is used inside an UndoCommand.
            self._setContents(parent, contents)
            
    def _setContents(self, parent, contents):
        """Set the contents of *parent* to the ContentList *contents*."""
        assert isinstance(contents, elements.ContentList)
        dataIds = []
        for id in parent.contents:
            if id not in contents:
                self[id].parents.remove(parent.id)
                dataIds.append(id)
        for id in contents:
            if parent.id not in self[id].parents:
                self[id].parents.append(parent.id)
                dataIds.append(id)
        parent.contents = contents
        self.emitEvent(dataIds=dataIds, contentIds=(parent.id,))

    def _insertContents(self, parent, insertions):
        """Insert some elements under *parent*. The insertions must be given as an iterable of
        (position, element) tuples.
        """
        self.lastInsertId = parent.id
        self.lastInsertPositions = set()
        dataIds = []
        for pos, element in insertions:
            self.lastInsertPositions.add(pos)
            parent.contents.insert(pos, element.id)
            if parent.id not in element.parents:
                element.parents.append(parent.id)
                dataIds.append(element.id)
        self.emitEvent(dataIds=dataIds, contentIds=(parent.id, ))

    def _removeContents(self, parent, positions):
        """Remove the children at given *positions* under parent.
        """
        positions = list(positions) # copy because the list will change
        childIds = [parent.contents.at(position) for position in positions]
        dataIds = []
        for pos in positions:
            parent.contents.remove(pos=pos)
        for id in childIds:
            if id not in parent.contents:
                self[id].parents.remove(parent.id)
                dataIds.append(id)
        self.emitEvent(dataIds=dataIds, contentIds=(parent.id, ))

    def _renameFiles(self, renamings):
        """Rename files based on *renamings*, a dict from elements to (oldUrl, newUrl) pairs.
        """
        for element, (_, newUrl) in renamings.items():
            element.url = newUrl
        self.emitEvent(dataIds=[elem.id for elem in renamings])

    def _changePositions(self, parent, changes):
        """Change positions of elements."""
        for i, position in enumerate(parent.contents.positions):
            if position in changes:
                parent.contents.positions[i] = changes[position]
        self.emitEvent(contentIds=(parent.id, ))
    
    # ====================================================================================
    # Special stuff
    # ====================================================================================           
    def createWrappers(self, wrapperString, createFunc=None):
        """Create a wrapper tree containing elements of this level and return its root node. This method
        is used to restore a tree from a string representation using elements of this level.
        
        *wrapperString* must be a string like   "X[A[A1,A2],B[B1,B2]],Z"
        where the identifiers must be names of existing elements of this level. If the given structure is
        invalid a ValueError is raised.
        
        If *createFunc* is not None, it will be used to create wrappers (instead of the constructor of
        Wrapper). It must take the parent wrapper and the name as arguments and return a Wrapper instance.
        It might raise ValueErrors if the wrapper string is invalid and an ElementGetError if the string
        is basically valid but no element can be loaded for it (like an id that does not belong to a file). 
        
        If *createFunc* is None, all names in *wrapperString* must be ids and wrappers are created using
        these ids.
        
        Identifiers for which no element can be created due to an ElementGetError will simply be skipped.
        """  
        roots = []
        currentWrapper = None
        currentList = roots
        
        def _getTokens(s):
            """Helper: Yield each token of *s*."""
            # s should be a string like "A,B[B1,B2],C[C1[C11,C12],C2],D"
            last = 0
            i = 0
            while i < len(s):
                if s[i] in (',','[',']'):
                    if last != i:
                        yield s[last:i]
                    last = i+1
                    yield s[i]
                i += 1
            if last != i:
                yield s[last:i]
        
        for token in _getTokens(wrapperString):
            if token == ',':
                continue
            if token == '[':
                if len(currentList) == 0:
                    raise ValueError("Invalid wrapper string: {}".format(wrapperString))
                currentWrapper = currentList[-1]
                if not currentWrapper.isContainer():
                    raise ValueError("Invalid wrapper string: {} is not a container."
                                     .format(currentWrapper.element.id))
                currentList = currentWrapper.contents
            elif token == ']':
                currentWrapper = currentWrapper.parent
                if currentWrapper is None:
                    currentList = roots
                else: currentList = currentWrapper.contents
            else:
                try:
                    if createFunc is None:
                        element = self.get[int(token)] # might raise ValueError
                        wrapper = Wrapper(element)
                        if currentWrapper is not None:
                            wrapper.parent = currentWrapper
                    else:
                        wrapper = createFunc(currentWrapper,token) # may raise ValueError
                
                    if currentWrapper is not None and wrapper.element.id not in currentWrapper.element.contents:
                        raise ValueError("Invalid wrapper string: {} is not contained in {}."
                                         .format(wrapper.element.id, currentWrapper.element.id))
                    currentList.append(wrapper)
                except ElementGetError as e:
                    logger.warning(str(e))
                    continue
        return roots
    
    def __str__(self):
        return 'Level({})'.format(self.name)
    
        
_urlToId = {}

def idFromUrl(url, create=False):
    """Return the id for the given url. If *create* is True and no id exists so far, create one."""
    if url in _urlToId:
        return _urlToId[url]
    else:
        id = db.idFromUrl(url)
        if id is None:
            if create:
                id = db.nextId()
            else: raise KeyError("There is no id for url '{}'".format(url))
        _urlToId[url] = id
        return id
