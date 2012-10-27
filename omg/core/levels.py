# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

import collections, numbers, weakref

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import data, elements, tags, flags
from .nodes import Wrapper
from .. import application, filebackends, database as db, logging

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)


allLevels = weakref.WeakSet() # List of all levels

# The two special levels
real = None
editor = None


def init():
    global real,editor
    from . import reallevel
    real = reallevel.RealLevel()
    editor = Level("EDITOR", parent=real)
    

#TODO is not used currently
class ElementGetError(RuntimeError):
    """Error indicating that an element failed to be loaded by some level."""
    pass


class RenameFilesError(RuntimeError):
    """An error that is raised when renaming files fails."""
    
    def __init__(self, oldUrl, newUrl, message):
        super().__init__("Error renaming '{}' to '{}': '{}'".format(oldUrl, newUrl, message))
        self.oldUrl = oldUrl
        self.newUrl = newUrl
        self.message = message
        
    def displayMessage(self):
        from ..gui import dialogs
        title = translate(__name__, "Error renaming file")
        msg = translate(__name__, "Could not rename '{}' to '{}':\n"
                                  "{}".format(self.oldUrl, self.newUrl, self.message))
        dialogs.warning(title, msg)


class ConsistencyError(RuntimeError):
    """Error signaling a consistency violation of element data."""
    pass


class ElementChangedEvent(application.ChangeEvent):
    #TODO comment
    def __init__(self, dataIds=None, contentIds=None):
        super().__init__()
        if dataIds is None:
            dataIds = []
        elif type(dataIds) is not list:
            dataIds = list(dataIds)
        self.dataIds = dataIds
        if contentIds is None:
            contentIds = []
        elif type(contentIds) is not list:
            contentIds = list(contentIds)
        self.contentIds = contentIds
        
    def merge(self,other):
        if isinstance(other,ElementChangedEvent):
            if self.dataIds is None:
                self.dataIDs = other.dataIds
            else:
                self.dataIds.extend([id for id in other.dataIds if id not in self.dataIds])
            if self.contentIds is None:
                self.dataIDs = other.contentIds
            else:
                self.contentIds.extend([id for id in other.contentIds if id not in self.contentIds])
            return True
        else:
            return False


class GenericLevelCommand(QtGui.QUndoCommand):
    #TODO comment
    def __init__(self, redoMethod, redoArgs, undoMethod, undoArgs, text=None):
        super().__init__()
        if text is not None:
            self.setText(text)
        self.redoMethod, self.redoArgs = redoMethod, redoArgs
        self.undoMethod, self.undoArgs = undoMethod, undoArgs
            
    def redo(self):
        self.redoMethod(**self.redoArgs)
            
    def undo(self):
        self.undoMethod(**self.undoArgs)
        

class Level(application.ChangeEventDispatcher):
    """A collection of elements corresponding to a specific state.
    
    A level consists of a consistent set of elements: All children of an element in a level must
    also be contained in the level.
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
    def __init__(self, name, parent, stack=None):
        super().__init__()
        allLevels.add(self)
        self.name = name
        self.parent = parent
        self.elements = {}
        self.stack = stack if stack is not None else application.stack
        
    def emitEvent(self, dataIds=None, contentIds=None):
        """Simple shortcut to emit an event."""
        self.emit(ElementChangedEvent(dataIds,contentIds))
    
    def get(self, param):
        """Return the element determined by *param*. Load it if necessary.
        
        *param* may be either the id or, in case of files, the url.
        """
        if not isinstance(param, int):
            if not isinstance(param, filebackends.BackendURL):
                raise ValueError("param must be either ID or URL, not {} of type {}"
                                    .format(param,type(param)))
            param = idFromUrl(param)
        if param not in self.elements:
            self.parent.loadIntoChild([param],self)
        return self.elements[param]
    
    def getFromIds(self, ids):
        """Load all elements given by the list of ids *ids* into this level and return them."""
        notFound = []
        for id in ids:
            if id not in self.elements:
                notFound.append(id)
        if len(notFound) > 0:
            self.parent.loadIntoChild(notFound, self)
        return [self.elements[id] for id in ids]
                
    def getFromUrls(self, urls):
        """Convenience method: load elements for the given urls and return them."""
        ids = [ idFromUrl(url) for url in urls ]
        return self.getFromIds(ids)
    
    def loadIntoChild(self, ids, child):
        """Load all elements given by the list of ids *ids* into the level *child*.
        
        This method does not check whether elements are already loaded in the child. Note that
        elements are *not* loaded into the *self* level.
        """
        notFound = []
        for id in ids:
            if id in self.elements:
                child.elements[id] = self.elements[id].copy()
                child.elements[id].level = child
            else: notFound.append(id)
        if len(notFound) > 0:
            self.parent.loadIntoChild(notFound, self)
        
    def __contains__(self, param):
        """Returns if the given element is loaded in this level.
        
        *param* may be either an ID or a URL. Note that if the element could be loaded from the
        parent but is not contained in this level, then *False* is returned.
        """
        if not isinstance(arg, int):
            if not isinstance(param, filebackends.BackendURL):
                raise ValueError("param must be either ID or URL, not {} of type {}"
                                    .format(param,type(param)))
            try:
                param = idFromUrl(param, create=False)
            except KeyError:
                #  no id for that path -> element can not be contained
                return False
        return (param in self.elements)
    
    def children(self, spec):
        """Returns a set of (recursively) all children of one or more elements.
        
        *spec* may be a single element, a list of elements, a single ID or a list of IDs.
        """
        if isinstance(spec, collections.Iterable):
            spec = list(spec)
            if len(spec) == 0:
                return set()
            #TODO: Why numbers.Integral?
            if isinstance(spec[0], numbers.Integral):
                spec = [self.get(id) for id in spec]
            return set.union(*(self.children(element) for element in spec))
        if isinstance(spec, numbers.Integral):
            spec = self.get(spec)
        if spec.isFile():
            return set( (spec, ) )
        else:
            return set.union(set( (spec, ) ),
                             *(self.children(childId) for childId in spec.contents))
    
    def files(self):
        """Return a generator of all files in this level."""
        return ( elem for elem in self.elements.values() if elem.isFile() )
 
    def subLevel(self, elements, name):
        """Return a child level of *self* containing copies of the given *elements* and
        named *name*.
        """
        level = Level(name, self)
        #TODO: Why load all children, too? Storing the ids in element.contents makes it possible to refer
        # to children which are not loaded
        level.getFromIds([elem.id for elem in self.children(elements)])
        return level

    # ===========================================================================
    # The following functions provide undo-aware implementations of level changes
    # ===========================================================================
    
    def createContainer(self, tags=None, flags=None, data=None, major=True, contents=None):
        """Create a new container with the given properties and load it into this level.
        
        Can be undone. Returns the new container.
        """
        from . import commands
        command = commands.CreateContainerCommand(self, tags, flags, data, major, contents)
        self.stack.push(command)
        return command.container
        
    def changeTags(self, changes):
        """Change tags of elements. *changes* maps elements to tags.TagDifference objects.
        On real level this method might raise a TagWriteError if writing (some or all) tags to the
        filesystem fails.
        """
        self._changeSomething(changes,self.tr("change tags"))
        
    def changeFlags(self, changes):
        """Change flags of elements. *changes* maps elements to flags.FlagDifference objects."""
        self._changeSomething(changes,self.tr("change flags"))
    
    def changeData(self, changes):
        """Change flags of elements. *changes* maps elements to data.DataDifference objects."""
        self._changeSomething(changes,self.tr("change data"))
    
    def _changeSomething(self,changes,text):
        """Helper for changeTags, changeFlags and similar methods which only need to undoably call
        _applyDiffs. *text* is used as text for the created undocommand."""
        inverseChanges = {elem:diff.inverse() for elem,diff in changes.items()}
        command = GenericLevelCommand(redoMethod=self._applyDiffs,
                                      redoArgs={"changes" : changes},
                                      undoMethod=self._applyDiffs,
                                      undoArgs={"changes": inverseChanges},
                                      text=text,
                                      errorClass=filebackends.TagWriteError)
        self.stack.push(command)
        
    def setCovers(self, coverDict):
        """Set the covers for one or more elements.
        
        The action can be undone. *coverDict* must be a dict mapping elements to either
        a cover path or a QPixmap or None.
        """
        from . import covers
        self.stack.push(covers.CoverUndoCommand(self, coverDict))
    
    def setMajorFlags(self, elemToMajor, emitEvent=True):
        """Set the major flags of one or more containers.
        
        The action can be undone. *elemToMajor* maps elements to boolean values indicating the
        desired major state.
        """
        reversed = {elem:(not major) for (elem, major) in elemToMajor.items()}
        command = GenericLevelCommand(redoMethod=self._setMajorFlags,
                                      redoArgs={"elemToMajor" : elemToMajor,
                                                "emitEvent" : emitEvent},
                                      undoMethod=self._setMajorFlags,
                                      undoArgs={"elemToMajor" : reversed,
                                                "emitEvent" : emitEvent},
                                      text=self.tr("change major property"))
        self.stack.push(command)
    
    def insertContents(self, parent, insertions):
        """Insert contents with predefined positions into a container.
        
        *insertions* is a list of (position, element) tuples.
        """
        command = GenericLevelCommand(redoMethod=self._insertContents,
                                      redoArgs={"parent" : parent,
                                                "insertions" : insertions,
                                                "emitEvent" : True},
                                      undoMethod=self._removeContents,
                                      undoArgs={"parent" : parent,
                                                "positions" : [pos for pos,_ in insertions],
                                                "emitEvent" : True},
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
        undoInsertions = [(pos, self.get(parent.contents.at(pos))) for pos in positions]
        command = GenericLevelCommand(redoMethod=self._removeContents,
                                      redoArgs={"parent" : parent,
                                                "positions" : positions,
                                                "emitEvent" : True},
                                      undoMethod=self._insertContents,
                                      undoArgs={"parent" : parent,
                                                "insertions" : undoInsertions,
                                                "emitEvent" : True},
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
                                                "changes" : changes,
                                                "emitEvent" : True},
                                      undoMethod=self._changePositions,
                                      undoArgs={"parent" : parent,
                                                "changes" : {b:a for a,b in changes.items()},
                                                "emitEvent" : True},
                                      text=self.tr("change positions"))
        self.stack.push(command)
    
    def renameFiles(self, renamings):
        """Rename several files. *renamings* maps element to (oldUrl, newUrl) paths.
        
        On the real level, this can raise a FileRenameError.
        """
        reversed =  {file:(newUrl, oldUrl) for  (file, (oldUrl, newUrl)) in renamings.items()}
        command = GenericLevelCommand(redoMethod=self._renameFiles,
                                      redoArgs={"renamings" : renamings,
                                                "emitEvent" : True},
                                      undoMethod=self._renameFiles,
                                      undoArgs={"renamings": reversed},
                                      text=self.tr("rename files"),
                                      errorClass=RenameFilesError)
        self.stack.push(command)
    
    def commit(self, elements=None):
        """Undoably commit given *elements* (or everything, if not specified) into the parent level.
        """
        from . import commands
        self.stack.beginMacro('commit')
        if elements is None:
            elements = list(self.elements.values())
        else:
            elements = self.children(elements)

        if self.parent is real:
            try:
                #  files with neg. ID that exist in DB (due to playlist loads) suck ... get rid of them
                # quickly by putting them into DB.
                tempFilesInReal = [real.get(elem.id) for elem in elements if elem.id < 0 and elem.id in real]
                newFiles = [elem for elem in elements if elem.id < 0 and elem.isFile() and elem.id not in real]
                newElements = newFiles + [elem for elem in elements if elem.isContainer() and elem.id < 0]
                oldElements = [elem for elem in elements if elem not in newElements]
                if len(tempFilesInReal) > 0:
                    self.stack.push(commands.CreateDBElementsCommand(tempFilesInReal, newInLevel=False))
                if len(newFiles) > 0:
                    #TODO: Doesn't this forget the tempFilesInReal?
                    # no - they can't have tags different from the filesystem
                    real.setFileTagsAndRename(newFiles)
                if len(newElements) > 0:
                    self.stack.push(commands.CreateDBElementsCommand(newElements, newInLevel=True))
                db.transaction()
            except (filebackends.TagWriteError, OSError) as e:
                self.stack.abortMacro()
                raise e
        else:
            newElements = [elem for elem in elements if elem.id not in self.parent.elements ]
            oldElements = [elem for elem in elements if elem.id in self.parent.elements ]
            self.parent.copyElements(newElements)
        tagChanges = {}
        for oldEl in oldElements:
            inParent = self.parent.get(oldEl.id)
            if oldEl.flags != inParent.flags:
                self.parent.changeFlags({inParent : flags.FlagListDifference(inParent.flags, oldEl.flags)})
            if oldEl.tags != inParent.tags:
                tagChanges[inParent] = tags.TagStorageDifference(inParent.tags, oldEl.tags)
            if oldEl.data != inParent.data:
                self.parent.changeData({inParent : data.DataDifference(inParent.data, oldEl.data)})
            if oldEl.isContainer():
                if oldEl.major != inParent.major:
                    self.parent.setMajorFlags({inParent: oldEl.major})
            else:
                if oldEl.url != inParent.url:
                    self.parent.renameFiles( {inParent:(inParent.url, oldEl.url)} )
        if len(tagChanges) > 0:
            self.parent.changeTags(tagChanges)
        if self.parent is real:
            db.commit()
        self.stack.endMacro()
            
    def copyElements(self, elements):
        """Copy and load *elements* into self. Supports undo/redo."""
        from . import commands
        self.stack.push(commands.CopyElementsCommand(self, elements))

    def deleteElements(self, elements):
        elements = list(elements)
        self.stack.beginMacro("delete elements")
        # 1st step: isolate the elements (remove contents & parents)
        for element in elements:
            if element.isContainer() and len(element.contents) > 0:
                self.removeContents(element, element.contents.positions)
            if len(element.parents) > 0:
                for parentId in element.parents:
                    parent = self.get(parentId)
                    self.removeContents(parent, parent.contents.positionsOf(id=element.id))
        command = GenericLevelCommand(redoMethod=self._removeElements,
                                      redoArgs={"elements" : elements},
                                      undoMethod=self._addElements,
                                      undoArgs={"elements" : elements})
        self.stack.push(command)
        self.stack.endMacro()
    
    # ====================================================================================
    # The following functions implement no undo/redo handling and should be used with care
    # ====================================================================================
    
    def _createContainer(self, tags, flags, data, major, contents, id=None):
        if id is None:
            id = db.nextId()
        container = elements.Container(self, id,
                                       inDB=False, # inDB is corrected in reallevel's reimplementation
                                       major=major,
                                       tags=tags,
                                       flags=flags,
                                       data=data,
                                       contents=contents)
        self.elements[id] = container
        if contents is not None:
            for childId in contents:
                self.get(childId).parents.append(id)
            self.emitEvent(dataIds=contents)
        return container
    
    def _applyDiffs(self, changes, emitEvent=True):
        """Given the dict *changes* mapping elements to Difference objects (e.g. tags.TagDifference, apply
        these differences to the elements. Do not emit an ElementChangedEvent if *emitEvent* is False.
        """
        for element, diff in changes.items():
            diff.apply(element)
        if emitEvent:
            self.emitEvent([element.id for element in changes])

    def _setData(self,type,elementToData):
        for element,data in elementToData.items():
            if data is not None:
                if isinstance(data,tuple):
                    element.data[type] = data
                else: element.data[type] = tuple(data)
            elif type in element.data:
                del element.data[type]
        self.emitEvent([element.id for element in elementToData])
    
    def _setMajorFlags(self, elemToMajor, emitEvent=True):
        """Set major of several elements."""
        for elem, major in elemToMajor.items():
            elem.major = major
        if emitEvent:
            self.emitEvent([elem.id for elem in elemToMajor])
    
    def _addElements(self, elements):
        for element in elements:
            assert element.level is self
            self.elements[element.id] = element
            if element.isContainer():
                for childId in element.contents:
                    self.get(childId).parents.append(element.id)
    
    def _removeElements(self, elements):
        """Remove the given element from this level.
        """
        for element in elements:
            del self.elements[element.id]
            if element.isContainer():
                for childId in element.contents:
                    self.get(childId).parents.remove(element.id)
    
    def _importElements(self, elements):
        """Create the elements *elements* from a different level into this one."""
        for elem in elements:
            self.elements[elem.id] = elem.copy()
            elem.level = self

    def _insertContents(self, parent, insertions, emitEvent=True):
        """Insert some elements under *parent*. The insertions must be given as an iterable of
        (position, element) tuples.
        """
        dataIds = []
        for pos, element in insertions:
            parent.contents.insert(pos, element.id)
            if parent.id not in element.parents:
                element.parents.append(parent.id)
                dataIds.append(element.id)
        if emitEvent:
            self.emitEvent(dataIds=dataIds, contentIds=(parent.id, ))

    def _removeContents(self, parent, positions, emitEvent=True):
        """Remove the children at given *positions* under parent.
        """
        positions = list(positions) # copy because the list will change
        childIds = [parent.contents.at(position) for position in positions]
        dataIds = []
        for pos in positions:
            parent.contents.remove(pos=pos)
        for id in childIds:
            if id not in parent.contents:
                self.get(id).parents.remove(parent.id)
                dataIds.append(id)
        if emitEvent:
            self.emitEvent(dataIds=dataIds, contentIds=(parent.id, ))

    def _renameFiles(self, renamings, emitEvent=True):
        """Rename files based on *renamings*, a dict from elements to (oldUrl, newUrl) pairs.
        """
        for element, (_, newUrl) in renamings.items():
            element.url = newUrl
        if emitEvent:
            self.emitEvent([elem.id for elem in renamings])

    def _changePositions(self, parent, changes, emitEvent=True):
        """Change positions of elements."""
        for i, position in enumerate(parent.contents.positions):
            if position in changes:
                parent.contents.positions[i] = changes[position]
        if emitEvent:
            self.emitEvent(contentIds=(parent.id, ))
    
    # ====================================================================================
    # Special stuff
    # ====================================================================================
         
    def reload(self, id):
        """Reload the file with *id* from the parent level and return the new version.
        
        This will (by means of an undo command) detach the file from all potential parents;
        afterwards it is reloaded from the parent level (or filesystem, if it is not found
        there).
        """
        assert id in self.elements
        assert self.get(id).isFile()
        self.stack.beginMacro(self.tr('reload'))
        for parentId in self.elements[id].parents:
            parent = self.get(parentId)
            self.removeContents(parent, parent.contents.positionsOf(id))
        self.stack.endMacro()
        del self.elements[id]
        return self.get(id)
            
    def createWrappers(self, wrapperString, createFunc=None):
        """Create a wrapper tree containing elements of this level and return its root node.
        
        *wrapperString* must be a string like   "X[A[A1,A2],B[B1,B2]],Z"
        where the identifiers must be names of existing elements of this level. This method does not check
        whether the given structure is valid.
        
        If *createFunc* is not None, it will be used to create wrappers (instead of the constructor of
        Wrapper). It must take the parent wrapper and the name as arguments and return a Wrapper instance.
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
                
        #TODO check consistency
        for token in _getTokens(wrapperString):
            if token == ',':
                continue
            if token == '[':
                currentWrapper = currentList[-1]
                currentList = currentWrapper.contents
            elif token == ']':
                currentWrapper = currentWrapper.parent
                if currentWrapper is None:
                    currentList = roots
                else: currentList = currentWrapper.contents
            else:
                if createFunc is None:
                    element = self.get(int(token))
                    wrapper = Wrapper(element)
                    if currentWrapper is not None:
                        assert currentWrapper.element.id in wrapper.element.parents
                        wrapper.parent = currentWrapper
                else: wrapper = createFunc(currentWrapper,token)
                currentList.append(wrapper)
        return roots
    
    def __str__(self):
        return 'Level({})'.format(self.name)


_idToUrl = {}
_urlToId = {}

def idFromUrl(url, create=True):
    """Return the id for the given url.
    
    For elements in the database this is a positive number. Otherwise if the url is known
    under a temporary id, that one is returned. If not and *create* is True, a new id is reserved for this
    url and returned. Otherwise a KeyError is raised.
    """
    if url in _urlToId:
        return _urlToId[url]
    else:
        id = db.idFromUrl(url)
        if id is None:
            if create:
                id = db.nextId()
            else: raise KeyError("There is no id for url '{}'".format(url))
        _urlToId[url] = id
        _idToUrl[id] = url
        return id


def urlFromId(id):
    if id in _idToUrl:
        return _idToUrl[id]
    else:
        url = db.url(id)
        if url is None:
            raise KeyError("There is not url for id {}".format(id))
        url = filebackends.BackendURL.fromString(db.url(id))
        _idToUrl[id] = url
        _urlToId[url] = id
        