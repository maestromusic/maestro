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

from . import tags, flags
from .elements import File, Container
from .nodes import Wrapper
from .. import application, filebackends, database as db, config, logging
from ..database import write as dbwrite


instances = weakref.WeakSet() #TODO: Do not rely on the GC to delete this fast enough
real = None
editor = None

logger = logging.getLogger(__name__)


def init():
    global real,editor
    real = RealLevel()
    editor = Level("EDITOR", parent=real)
    

class ElementGetError(RuntimeError):
    """Error indicating that an element failed to be loaded by some level."""
    pass


class ConsistencyError(RuntimeError):
    """Error signaling a consistency violation of element data."""
    pass


class ElementChangedEvent(application.ChangeEvent):
    #TODO comment
    def __init__(self,dataIds=None,contentIds=None):
        super().__init__()
        if dataIds is None:
            self.dataIds = []
        else: self.dataIds = dataIds
        if contentIds is None:
            self.contentIds = []
        else: self.contentIds = contentIds


class FileCreateDeleteEvent(ElementChangedEvent):
    """Special event for creation and/or deletion of files in the database. Has
    the attributes "created" and "deleted", which are lists of paths. The boolean
    *disk* attribute indicates that a file removal has taken place on disk (not only
    DB) which helps the filesystem module to efficiently update its folder states.
    """
    def __init__(self, created = None, deleted = None, disk = False):
        super().__init__()
        self.created = created if created is not None else []
        self.deleted = deleted if deleted is not None else []
        self.disk = disk


class FileRenameEvent(ElementChangedEvent):
    """Event indicating that files have been renamed on disk."""
    def __init__(self, renamings):
        super().__init__()
        self.renamings = renamings


class DataUndoCommand(QtGui.QUndoCommand):
    def __init__(self,level,element,type,new):
        self.level = level
        self.element = element
        self.type = type
        if type in element.data:
            self.old = element.data[type]
        else: self.old = None
        self.new = new
        assert isinstance(self.old,tuple) and isinstance(self.new,tuple)

    def redo(self):
        self.level._setData(self.type,{self.element: self.new})
        
    def undo(self):
        self.level._setData(self.type,{self.element: self.old})


class Level(QtCore.QObject):
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
    """ 
    
    """Signal that is emitted if something changes on this level."""
    changed = QtCore.pyqtSignal(application.ChangeEvent)
    
    def __init__(self, name, parent, stack=None):
        """Create a level named *name* with parent *parent* and an optional undo stack.
        
        If no undo stack is given, the main application.stack will be used.
        """
        super().__init__()
        instances.add(self)
        self.name = name
        self.parent = parent
        self.elements = {}
        self.stack = stack if stack is not None else application.stack
        
        if config.options.misc.debug_events:
            def _debugAll(event):
                logger.debug("EVENT[{}]: {}".format(self.name,str(event)))
            self.changed.connect(_debugAll)
        
    def emitEvent(self, dataIds=None, contentIds=None):
        """Simple shortcut to emit an event."""
        self.changed.emit(ElementChangedEvent(dataIds,contentIds))
    
    def get(self, param):
        """Return the element determined by *param*. Load it if necessary.
        
        *param* may be either the id or, in case of files, the path.
        """
        if not isinstance(param,int):
            assert isinstance(param, filebackends.BackendURL)
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
        self.parent.loadIntoChild(notFound, self)
        return [self.elements[id] for id in ids]
                
    def getFromUrls(self, urls):
        """Convenience method: load elements for the given urls and return them."""
        ids = [ idFromUrl(url) for url in urls ]
        return self.getFromIds(ids)
    
    def loadIntoChild(self, ids, child):
        """Load all elements given by the list of ids *ids* into the level *child*.
        
        This method does not check whether elements are already loaded in the child. Note that
        elements are *not* loaded into the *self* level if they were not contained there before.
        """
        notFound = []
        for id in ids:
            if id in self.elements:
                child.elements[id] = self.elements[id].copy()
                child.elements[id].level = child
            else: notFound.append(id)
        self.parent.loadIntoChild(notFound, self)
        
    def __contains__(self, arg):
        """Returns if the given element is loaded in this level.
        
        *arg* may be either an ID or a path. Note that if the element could be loaded from the
        parent but is not contained in this level, then *False* is returned.
        """
        if not isinstance(arg, int):
            try:
                arg = idFromUrl(arg, create=False)
            except KeyError:
                #  no id for that path -> element can not be contained
                return False
        return (arg in self.elements)
    
    def children(self, spec):
        """Returns a set of (recursively) all children of one or more elements.
        
        *spec* may be a single element, a list of elements, a single ID or a list of IDs.
        """
        if isinstance(spec, collections.Iterable):
            spec = list(spec)
            if len(spec) == 0:
                return set()
            if isinstance(spec[0], numbers.Integral):
                spec = [self.get(id) for id in spec]
            return set.union(*(self.children(element) for element in spec))
        if isinstance(spec, numbers.Integral):
            spec = self.get(spec)
        if spec.isFile():
            return set( (spec.id, ) )
        else:
            return set.union(set( (spec.id, ) ),
                             *(self.children(childId) for childId in spec.contents.ids))
    
    def files(self):
        """Return a generator of all files in this level."""
        return ( elem for elem in self.elements.values() if elem.isFile() )
 
    def subLevel(self, elements, name):
        """Return a child level of *self* containing copies of the given *elements* and
        named *name*.
        """
        level = Level(name, self)
        level.getFromIds(self.children(elements))
        return level
    
    def createWrappers(self, wrapperString, createFunc=None):
        """Create a wrapper tree containing elements of this level and return its root node.
        
        *wrapperString* must be a string like   "X[A[A1,A2],B[B1,B2]],Z"
        where the identifiers must be names of existing elements of this level. This method does not check
        whether the given structure is valid.
        
        Often it is necessary to have references to some of the wrappers in the tree. For this reason
        this method accepts names of wrappers as optional arguments. It will then return a tuple consisting
        of the usual result (as above) and the wrappers with the given names (do not use this if there is
        more than one wrapper with the same name).
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
            #print("Token: {}".format(token))
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

    # ===========================================================================
    # The following functions provide undo-aware implementations of level changes
    # ===========================================================================
    
    def insertContents(self, parent, index, elements):
        """Undoably insert elements into a parent container.
        
        *parent* is the container in which to insert the elements *elements*. The insert index
        (not position) is given by *index*; the position is automatically determined, and
        subsequent elements' positions are shifted if necessary.
        """
        from . import commands
        self.stack.beginMacro(self.tr("insert"))
        if len(parent.contents) > index:
            #  need to alter positions of subsequent elements
            firstPos = 1 if index == 0 else parent.contents.positions[index-1]+1
            lastPosition = firstPos + len(elements) - 1
            shift = lastPosition - parent.contents.positions[index] + 1
            if shift > 0:
                posCom = commands.ChangePositionsCommand(self, parent,
                                                         parent.contents.positions[index:],
                                                         shift)
                self.stack.push(posCom)
        insertCom = commands.InsertElementsCommand(self, parent, index, elements)
        self.stack.push(insertCom)
        self.stack.endMacro()
        
    def removeContents(self, parent, positions=None, indexes=None):
        """Undoably remove contents under the container *parent*.
        
        The elements to remove may be given either by specifying their *positions* or
        *indexes*.        
        If there are subsequent elements behind the deleted ones, their positions will be
        diminished so that no gap results.
        """
        from . import commands
        if positions is None:
            positions = [ parent.contents.positions[i] for i in indexes ]
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
        self.stack.beginMacro(self.tr("remove"))
        removeCommand = commands.RemoveElementsCommand(self, parent, positions)
        self.stack.push(removeCommand)
        if shiftPositions is not None:
            posCommand = commands.ChangePositionsCommand(self, parent, shiftPositions, shift)
            self.stack.push(posCommand)
        self.stack.endMacro()
    
    def setCovers(self, coverDict):
        """Set the covers for one or more elements.
        
        The action can be undone. *coverDict* must be a dict mapping elements to either
        a cover path or a QPixmap or None.
        """
        from . import covers
        self.stack.push(covers.CoverUndoCommand(self, coverDict))
    
    def commit(self, ids=None):
        """Undoably commit given *ids* (or everything, if not specified) into the parent level."""
        from . import commands
        if ids is None:
            ids = list(self.elements.keys())
        self.stack.push(commands.CommitCommand(self, ids))

    def reload(self, id):
        """Reload the file with *id* from the parent level and return the new version.
        
        This will (by means of an undo command) detach the file from all potential parents;
        afterwards it is reloaded from the parent level (or filesystem, if it is not found
        there).
        """
        assert id in self.elements
        assert self.get(id).isFile()
        from . import commands
        for parentId in self.elements[id].parents:
            parent = self.get(parentId)
            command = commands.RemoveElementsCommand(self,
                                                     parent,
                                                     parent.contents.getPositions(id))
            application.stack.push(command)
        del self.elements[id]
        return self.get(id)

    # ====================================================================================
    # The following functions implement no undo/redo handling and should be used with care
    # ====================================================================================
    
    def _addTagValue(self, tag, value, elements, emitEvent=True):
        """Add a tag of type *tag* and value *value* to the given elements.
        
        If *emitEvent* is False, do not emit the event self.changed."""
        for element in elements:
            element.tags.add(tag, value)
        if emitEvent:
            self.emitEvent([element.id for element in elements])
            
    def _removeTagValue(self, tag, value, elements, emitEvent=True):
        """Remove a tag of type *tag* and *value* value from the given elements.
        
        If *emitEvent* is False, do not emit self.changed."""
        for element in elements:
            element.tags.remove(tag, value)
        if emitEvent:
            self.emitEvent([element.id for element in elements])
            
    def _changeTagValue(self, tag, oldValue, newValue, elements, emitEvent=True):
        """Change a tag of type *tag* in the given elements changing the value from *oldValue* to *newValue*.
        If *emitEvent* is False, do not emit an event."""
        for element in elements:
            element.tags.replace(tag,oldValue,newValue)
        if emitEvent:
            self.emitEvent([element.id for element in elements])
    
    def _addFlag(self, flag, elements, emitEvent=True):
        """Add *flag* to the given elements. If *emitEvent* is False, do not emit an event."""
        for element in elements:
            if flag not in element.flags:
                element.flags.append(flag)
        if emitEvent:
            self.emitEvent([element.id for element in elements])
            
    def _removeFlag(self,flag,elements,emitEvent=True):
        """Remove *flag* from the given elements. If *emitEvent* is False, do not emit an event."""
        for element in elements:
            element.flags.remove(flag)
        if emitEvent:
            self.emitEvent([element.id for element in elements])
    
    def _setData(self,type,elementToData):
        for element,data in elementToData.items():
            if data is not None:
                if isinstance(data,tuple):
                    element.data[type] = data
                else: element.data[type] = tuple(data)
            elif type in element.data:
                del element.data[type]
        self.emitEvent([element.id for element in elementToData])
        
    def _changeId(self, old, new):
        """Change the id of some element from *old* to *new*.
        
        This should only be called from within appropriate UndoCommands, and only if "old in self"
        is True. Takes care of contents and parents, too.
        """
        elem = self.elements[old]
        del self.elements[old]
        elem.id = new
        self.elements[new] = elem
        for parentID in elem.parents:
            parentContents = self.elements[parentID].contents
            parentContents.ids[:] = [ new if id == old else id for id in parentContents.ids ]
        if elem.isContainer():
            for childID in elem.contents.ids:
                if childID in self.elements:
                    self.elements[childID].parents = [ new if id == old else old
                                                      for id in self.elements[childID].parents ]
    
    # TODO: used anywhere?
    def _insertSingle(self, parent, position, element):
        """Insert single child *element* at *position* under *parent*."""
        self._insertContents(parent, ( (position, element), ))
    
    def _insertContents(self, parent, insertions):
        """Insert some elements under *parent*.
        
        The insertions are given by an iterable of (position, element) tuples.
        """
        for pos, element in insertions:
            parent.contents.insert(pos, element.id)
            if parent.id not in element.parents:
                element.parents.append(parent.id)
        
    # TODO: used anywhere?
    def _removeSingle(self, parent, position):
        """Remove element at *position* from container *parent*."""
        self._removeContents(parent, (position,) )
    
    def _removeContents(self, parent, positions):
        childIds = [parent.contents.getId(position) for position in positions]
        for pos in positions:
            parent.contents.remove(pos=pos)
        for id in childIds:
            if id not in parent.contents.ids:
                self.get(id).parents.remove(parent.id)

    def _renameFiles(self, renamings, emitEvent=True):
        """Rename files based on *renamings*, which is a dict from ids to (oldUrl, newUrl) pairs.
        
        On a normal level, this just changes the Url attributes and emits an event.
        """
        for id, (_, newUrl) in renamings.items():
            self.get(id).url = newUrl
        if emitEvent:
            self.emitEvent(list(renamings.keys()))
    
    def __str__(self):
        return 'Level({})'.format(self.name)


class RealLevel(Level):
    """The real level, comprising the state of database and filesystem.
    
    Changes made here do not only change the element objects but also the database and, if
    files are affected, the filesystem state.
    """
    
    def __init__(self):
        super().__init__('REAL', None)
        # This hack makes the inherited implementations of get and load work with the overwritten
        # implementation of loadIntoChild
        self.parent = self
    
    def loadIntoChild(self, ids, child):
        """Loads IDs which are not yet known from database (if positive) or filesystem (else)."""
        notFound = []
        for id in ids:
            if id in self.elements:
                child.elements[id] = self.elements[id].copy()
                child.elements[id].level = child
            else: notFound.append(id)
        if len(notFound) > 0:
            positiveIds = [id for id in notFound if id > 0]
            urls = [ tIdManager(id) for id in notFound if id < 0 ]
            if len(positiveIds) > 0:
                self.loadFromDB(positiveIds, child)
            if len(urls) > 0:
                self.loadURLs(urls, child)
            
    def loadFromDB(self, idList, level):
        """Load elements specified by *idList* from the database into *level*."""
        if len(idList) == 0: # queries will fail otherwise
            return 
        idList = ','.join(str(id) for id in idList)
        #  bare elements
        result = db.query("""
                SELECT el.id, el.file, el.major, f.url, f.length
                FROM {0}elements AS el LEFT JOIN {0}files AS f ON el.id = f.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix, idList))
        for (id, file, major, url, length) in result:
            if file:
                level.elements[id] = File(level, id,
                                          url=filebackends.BackendURL.fromString(url),
                                          length=length)
            else:
                level.elements[id] = Container(level, id, major=major)
        #  contents
        result = db.query("""
                SELECT el.id, c.position, c.element_id
                FROM {0}elements AS el JOIN {0}contents AS c ON el.id = c.container_id
                WHERE el.id IN ({1})
                ORDER BY position
                """.format(db.prefix, idList))
        for (id, pos, contentId) in result:
            level.elements[id].contents.insert(pos, contentId)
        #  parents
        result = db.query("""
                SELECT el.id,c.container_id
                FROM {0}elements AS el JOIN {0}contents AS c ON el.id = c.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix, idList))
        for (id, contentId) in result:
            level.elements[id].parents.append(contentId)
        #  tags
        result = db.query("""
                SELECT el.id,t.tag_id,t.value_id
                FROM {0}elements AS el JOIN {0}tags AS t ON el.id = t.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix, idList))
        for (id,tagId,valueId) in result:
            tag = tags.get(tagId)
            level.elements[id].tags.add(tag, db.valueFromId(tag, valueId))
        # flags
        result = db.query("""
                SELECT el.id,f.flag_id
                FROM {0}elements AS el JOIN {0}flags AS f ON el.id = f.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix, idList))
        for (id, flagId) in result:
            level.elements[id].flags.append(flags.get(flagId))
        # data
        result = db.query("""
                SELECT element_id,type,data
                FROM {}data
                WHERE element_id IN ({})
                ORDER BY element_id,type,sort
                """.format(db.prefix, idList))
        # This is a bit complicated because the data should be stored in tuples, not lists
        # Changing the lists would break undo/redo
        current = None
        buffer = []
        for (id, type, data) in result:
            if current is None:
                current = (id, type)
            elif current != (id, type):
                level.elements[current[0]].data[current[1]] = tuple(buffer)
                current = (id,type)
                buffer = []
            element = level.elements[id]
            if element.data is None:
                element.data = {}
            buffer.append(data)
        if current is not None:
            level.elements[current[0]].data[current[1]] = tuple(buffer)
            
    def loadURLs(self, urls, level):
        """Loads files given by *urls*, into *level*."""
        for url in urls:
            backendFile = url.getBackendFile()
            backendFile.readTags()
            fTags = backendFile.tags
            fLength = backendFile.length
            fPosition = backendFile.position
            id = db.idFromUrl(url)
            if id is None:
                id = tIdManager.tIdFromUrl(url)
                flags = []
            else:
                flags = db.flags(id)
                # TODO: Load private tags!
                logger.warning("loadFromURLs called on '{}', which is in DB. Are you "
                           " sure this is correct?".format(url))
            elem = File(level, id=id, url=url, length=fLength, tags=fTags, flags=flags)
            elem.fileTags = fTags.copy()
            if fPosition is not None:
                elem.filePosition = fPosition            
            level.elements[id] = elem
    
            
    def saveTagsToFileSystem(self, elements):
        """Helper function to store the tags of *elements* on the filesystem."""
        failedElements = []
        for element in elements:
            if not element.isFile():
                continue
            try:
                real = element.url.getBackendFile()
                real.tags = element.tags.withoutPrivateTags()
                real.saveTags()
            except IOError as e:
                logger.error("Could not save tags of '{}'.".format(element.path))
                logger.error("Error was: {}".format(e))
                failedElements.append(elements)
                continue
        return failedElements
    
    # =============================================================
    # Overridden from Level: these methods modify DB and filesystem
    # =============================================================
    
    def _insertContents(self, parent, insertions):
        db.write.addContents([(parent.id, pos, child.id) for pos, child in insertions])
        super()._insertContents(parent, insertions)
        
    def _removeContents(self, parent, positions):
        db.write.removeContents([(parent.id, pos) for pos in positions])
        super()._removeContents(parent, positions)
    
    def _addTagValue(self, tag, value, elements, emitEvent=True):
        super()._addTagValue(tag, value, elements, emitEvent=False)
        failedElements = self.saveTagsToFileSystem(elements)
        #TODO: Correct failedElements
        dbElements = [el.id for el in elements if el.isInDB() and not el in failedElements]
        if len(dbElements):
            dbwrite.addTagValues(dbElements, tag, [value])
        if emitEvent:
            self.emitEvent([element.id for element in elements])
            
    def _removeTagValue(self, tag, value, elements, emitEvent=True):
        super()._removeTagValue(tag, value, elements, emitEvent=False)
        failedElements = self.saveTagsToFileSystem(elements)
        #TODO: Correct failedElements
        dbElements = [el.id for el in elements if el.isInDB() and not el in failedElements]
        if len(dbElements) > 0:
            dbwrite.removeTagValuesById(dbElements, tag, db.idFromValue(tag, value))
        else: assert all(element.id < 0 for element in elements)
        if emitEvent:
            self.emitEvent([element.id for element in elements])

    def _changeTagValue(self, tag, oldValue, newValue, elements, emitEvent=True):
        super()._changeTagValue(tag, oldValue, newValue, elements, emitEvent=False)
        failedElements = self.saveTagsToFileSystem(elements)
        #TODO: Correct failedElements
        dbElements = [el.id for el in elements if el.isInDB() and not el in failedElements]
        if len(dbElements):
            dbwrite.changeTagValueById(dbElements, tag, db.idFromValue(tag, oldValue),
                                       db.idFromValue(tag, newValue, insert=True))
        if emitEvent:
            self.emitEvent([element.id for element in elements])
    
    def _renameFiles(self, renamings, emitEvent=True):
        """on the real level, files are renamed on disk and in DB."""
        super()._renameFiles(renamings, emitEvent)
        for id, (oldUrl, newUrl) in renamings.items():
            oldUrl.getBackendFile().rename(newUrl)
        db.write.changeUrls([ (id, str(newUrl)) for id, (_, newUrl) in renamings.items() ])
        if emitEvent:
            self.changed.emit(FileRenameEvent(list(renamings.items())))
            
    def _addFlag(self, flag, elements, emitEvent=True):
        super()._addFlag(flag, elements, emitEvent=False)
        ids = [element.id for element in elements]
        db.write.addFlag(ids, flag)
        if emitEvent:
            self.emitEvent(ids)
            
    def _removeFlag(self, flag, elements, emitEvent=True):
        super()._removeFlag(flag, elements, emitEvent=False)
        ids = [element.id for element in elements]
        db.write.removeFlag(ids, flag)
        if emitEvent:
            self.emitEvent(ids)
            
    def _setData(self,type, elementToData):
        super()._setData(type, elementToData)
        values = []
        for element, data in elementToData.items():
            if data is not None:
                values.extend((element.id, type, i, d) for i, d in enumerate(data))
        db.transaction()
        db.query("DELETE FROM {}data WHERE type = ? AND element_id IN ({})"
                 .format(db.prefix,db.csIdList(elementToData.keys())),type)
        if len(values) > 0:
            db.multiQuery("INSERT INTO {}data (element_id,type,sort,data) VALUES (?,?,?,?)"
                          .format(db.prefix),values)
        db.commit()
        
        
def idFromUrl(url, create=True):
    """Return the id for the given url.
    
    For elements in the database this is a positive number. Otherwise if the url is known
    under a temporary id, that one is returned. If not and *create* is True, a new temporary
    id is created and returned. Otherwise a KeyError is raised.
    """
    
    id = db.idFromUrl(url)
    if id is not None:
        return id
    else: return tIdManager.tIdFromUrl(url, create)


def urlFromId(id):
    if id < 0:
        return tIdManager(id)
    else:
        return filebackends.BackendURL.fromString(db.url(id))

class TIDManager:
    """Manages temporary IDs and related URLs.
    
    Acts as a bidirectional map tId<->URL where the URL of a file always refers to the REAL level.
    """
    
    def __init__(self):
        self.tIdToUrl = {}
        self.urlToTId = {}
        self.currentTId = 0
        
    def __call__(self, key):
        if isinstance(key, filebackends.BackendURL):
            return self.urlToTId[key]
        return self.tIdToUrl[key]
    
    def tIdFromUrl(self, url, create=True):
        """Return the temporary id for *url*, if it exists.
        
        If it does not exist and *create* is True, a new one is inserted and returned.
        Otherwise, a KeyError is raised.
        """
        try:
            return self.urlToTId[url]
        except KeyError as e:
            if create:
                newId = self.createTId()
                self.urlToTId[url] = newId
                self.tIdToUrl[newId] = url
                return newId
            else:
                raise e
            
    def createTId(self):
        """Create a temporary ID without relating a URL to it. Use for temporary containers."""
        self.currentTId -= 1
        return self.currentTId         

tIdManager = TIDManager()
