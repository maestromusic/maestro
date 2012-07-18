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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import tags, flags
from .elements import File, Container
from .nodes import Wrapper
from .. import database as db, realfiles, utils, config, logging
from ..database import write as dbwrite
from ..application import ChangeEvent

import os.path, collections

real = None
editor = None

logger = logging.getLogger(__name__)

def init():
    global real,editor
    real = RealLevel()
    from ..models import leveltreemodel
    editor = Level("EDITOR",real, cleanupModelClass=leveltreemodel.LevelTreeModel)
    

class ElementGetError(RuntimeError):
    """Error indicating that an element failed to be loaded by some level."""
    pass


class ConsistencyError(RuntimeError):
    """Error signaling a consistency violation of element data."""
    pass


class ElementChangedEvent(ChangeEvent):
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
    #TODO comment
    changed = QtCore.pyqtSignal(ChangeEvent)
    """Signal that is emitted if something changes on this level. The first argument is a list of Ids of elements
    whose tags, flags, major status, ... has changed (things affecting only the element itself). The second list
    contains IDs of containers whose contents have changed."""
    
    def __init__(self, name, parent):
        super().__init__()
        self.name = name
        self.parent = parent
        self.elements = {}
        if config.options.misc.debug_events:
            def _debugAll(event):
                logger.debug("EVENT[{}]: {}".format(self.name,str(event)))
            self.changed.connect(_debugAll)
        
    def get(self,param):
        """Return the element determined by *param* from this level. Load the element, if it is not already
        present on the level. Currently, *param* may be either the id or the path."""
        if not isinstance(param,int):
            param = idFromPath(utils.relPath(param))
        if param not in self.elements:
            self.parent.loadIntoChild([param],self)
        return self.elements[param]
    
    def getFromIds(self,ids):
        """Load all elements given by the list of ids *ids* into this level and return them."""
        notFound = []
        for id in ids:
            if id not in self.elements:
                notFound.append(id)
        self.parent.loadIntoChild(notFound,self)
        return [self.elements[id] for id in ids]
                
    def getFromPaths(self,paths):
        """Load elements for the given paths and return them."""
        ids = [idFromPath(path) for path in paths]
        return self.getFromIds(ids)
        
    def loadIntoChild(self,ids,child):
        """Load all elements given by the list of ids *ids* into the level *child*. Do not check whether
        elements are already loaded there."""
        notFound = []
        for id in ids:
            if id in self.elements:
                child.elements[id] = self.elements[id].copy()
                child.elements[id].level = child
            else: notFound.append(id)
        self.parent.loadIntoChild(notFound,self)
        
    def __contains__(self, id):
        """Returns if the given id is loaded in this level. Note that if the id could be loaded from the
        parent but is not contained in this level, then *False* is returned."""
        return self.elements.__contains__(id)
    
    def __str__(self):
        return 'Level({})'.format(self.name)
    
    def emitEvent(self,dataIds=None,contentIds=None):
        """Simple shortcut to emit an event."""
        self.changed.emit(ElementChangedEvent(dataIds,contentIds))
  
    def addTagValue(self,tag,value,elements,emitEvent=True):
        """Add a tag of type *tag* and value *value* to the given elements. If *emitEvent* is False, do not
        emit an event."""
        for element in elements:
            element.tags.add(tag,value)
        if emitEvent:
            self.emitEvent([element.id for element in elements])
            
    def removeTagValue(self,tag,value,elements,emitEvent=True):
        """Remove a tag of type *tag* and *value* value from the given elements. If *emitEvent* is False,
        do not emit an event."""
        for element in elements:
            element.tags.remove(tag,value)
        if emitEvent:
            self.emitEvent([element.id for element in elements])
            
    def changeTagValue(self,tag,oldValue,newValue,elements,emitEvent=True):
        """Change a tag of type *tag* in the given elements changing the value from *oldValue* to *newValue*.
        If *emitEvent* is False, do not emit an event."""
        for element in elements:
            element.tags.replace(tag,oldValue,newValue)
        if emitEvent:
            self.emitEvent([element.id for element in elements])
    
    def addFlag(self,flag,elements,emitEvent=True):
        """Add *flag* to the given elements. If *emitEvent* is False, do not emit an event."""
        for element in elements:
            if flag not in element.flags:
                element.flags.append(flag)
        if emitEvent:
            self.emitEvent([element.id for element in elements])
            
    def removeFlag(self,flag,elements,emitEvent=True):
        """Remove *flag* from the given elements. If *emitEvent* is False, do not emit an event."""
        for element in elements:
            element.flags.remove(flag)
        if emitEvent:
            self.emitEvent([element.id for element in elements])
        
    def setCovers(self,stack,coverDict):
        """Set the covers for one or more elements. Add a command for doing this to *stack*.
        *coverDict* must be a dict mapping elements to either a cover path or a QPixmap or None.
        """
        from . import covers
        stack.push(covers.CoverUndoCommand(self,coverDict))
    
    def _setData(self,type,elementToData):
        for element,data in elementToData.items():
            if data is not None:
                if isinstance(data,tuple):
                    element.data[type] = data
                else: element.data[type] = tuple(data)
            elif type in element.data:
                del element.data[type]
        self.emitEvent([element.id for element in elementToData])
        
    def changeId(self, old, new):
        """Change the id of some element from *old* to *new*. This should only be called from within
        appropriate UndoCommands, and only if (old in self) is True. Takes care of contents and parents, too.
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
    
    def insertChild(self, parentId, position, childId):
        """Insert element with id *childId* at *position* under *parentId*."""
        self.insertChildren(parentId, ( (position, childId), ))
    
    def insertChildren(self, parentId, insertions):
        """Insert elements under *parentId*, which are given by an iterable of (position, id)
        tuples."""
        parent = self.get(parentId)
        for pos, id in insertions:
            parent.contents.insert(pos, id)
            if not parentId in self.get(id).parents:
                self.get(id).parents.append(parentId)
        
    def removeChild(self, parentId, position):
        """Remove element at *position* from container with id *parentId*."""
        self.removeChildren(parentId, (position,) )
    
    def removeChildren(self, parentId, positions):
        parent = self.get(parentId)
        childIds = [parent.contents.getId(position) for position in positions]
        for pos in positions:
            parent.contents.remove(pos = pos)
        for id in childIds:
            if id not in parent.contents.ids:
                self.get(id).parents.remove(parentId)
                
    def renameFiles(self, map, emitEvent = True):
        """Rename files based on *map*, which is a dict from ids to new paths.
        
        On a normal level, this just changes the path attributes and emits an event."""
        #TODO: this contradicts the docstring
        for id, (_, newPath) in map.items():
            self.get(id).path = newPath
        if emitEvent:
            self.emitEvent(list(map.keys()))
    
    def children(self, id):
        """Returns a set of (recursively) all children of the element with *id*. *id* may also be an
        iterable of ids."""
        if isinstance(id, collections.Iterable):
            if len(id) == 0:
                return set()
            return set.union(*(self.children(i) for i in id))
        if self.get(id).isFile():
            return set((id,))
        else:
            return set.union(set((id,)), *(self.children(cid) for cid in self.get(id).contents.ids))
    
    def subLevel(self, ids, name):
        """Return a new level containing copies of the elements with the given *ids* and named *name*."""
        level = Level(name, self)
        for id in ids:
            level.getFromIds(self.children(id))
        return level
        
    def createWrappers(self,wrapperString,createFunc=None):
        """Create a wrapper tree containing elements of this level and return its root node.
        *s* must be a string like   "X[A[A1,A2],B[B1,B2]],Z"
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

def _getTokens(s):
    """Helper for Level.getWrappers: Yield each token of *s*."""
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


class RealLevel(Level):
    def __init__(self):
        super().__init__('REAL',None)
        # This hack makes the inherited implementations of get and load work with the overwritten
        # implementation of loadIntoChild
        self.parent = self
    
    def loadIntoChild(self,ids,child):
        notFound = []
        for id in ids:
            if id in self.elements:
                child.elements[id] = self.elements[id].copy()
                child.elements[id].level = child
            else: notFound.append(id)
        if len(notFound) > 0:
            positiveIds = [id for id in notFound if id > 0]
            paths = [pathFromTId(id) for id in notFound if id < 0]
            if len(positiveIds) > 0:
                self.loadFromDB(positiveIds,child)
            if len(paths) > 0:
                self.loadFromFileSystem(paths,child)
            
    def loadFromDB(self,idList,level):
        #TODO: comment
        if len(idList) == 0: # queries will fail otherwise
            return 
        idList = ','.join(str(id) for id in idList)
        result = db.query("""
                SELECT el.id,el.file,el.major,f.path,f.length
                FROM {0}elements AS el LEFT JOIN {0}files AS f ON el.id = f.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix,idList))
        
        for row in result:
            id,file,major,path,length = row
            if file:
                level.elements[id] = File(level,id,path=path,length=length)
            else:
                level.elements[id] = Container(level,id,major=major)
        
        # contents
        result = db.query("""
                SELECT el.id,c.position,c.element_id
                FROM {0}elements AS el JOIN {0}contents AS c ON el.id = c.container_id
                WHERE el.id IN ({1})
                ORDER BY position
                """.format(db.prefix,idList))
        
        for row in result:
            id,pos,contentId = row
            level.elements[id].contents.insert(pos, contentId)
        
        # parents
        result = db.query("""
                SELECT el.id,c.container_id
                FROM {0}elements AS el JOIN {0}contents AS c ON el.id = c.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix,idList))
        
        for row in result:
            id,contentId = row
            level.elements[id].parents.append(contentId)
        
        # tags
        result = db.query("""
                SELECT el.id,t.tag_id,t.value_id
                FROM {0}elements AS el JOIN {0}tags AS t ON el.id = t.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix,idList))
        
        for row in result:
            id,tagId,valueId = row
            tag = tags.get(tagId)
            level.elements[id].tags.add(tag,db.valueFromId(tag,valueId))
            
        # flags
        result = db.query("""
                SELECT el.id,f.flag_id
                FROM {0}elements AS el JOIN {0}flags AS f ON el.id = f.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix,idList))
        
        for row in result:
            id,flagId = row
            level.elements[id].flags.append(flags.get(flagId))
        
        # data
        result = db.query("""
                SELECT element_id,type,data
                FROM {}data
                WHERE element_id IN ({})
                ORDER BY element_id,type,sort
                """.format(db.prefix,idList))
        
        # This is a bit complicated because the data should be stored in tuples, not lists
        # Changing the lists would break undo/redo
        current = None
        buffer = []
        for id,type,data in result:
            if current is None:
                current = (id,type)
            elif current != (id,type):
                level.elements[current[0]].data[current[1]] = tuple(buffer)
                current = (id,type)
                buffer = []
                
            element = level.elements[id]
            if element.data is None:
                element.data = {}
            buffer.append(data)
        if current is not None:
            level.elements[current[0]].data[current[1]] = tuple(buffer)
            
    
    def loadFromFileSystem(self,paths,level):
        #TODO: comment
        for path in paths:
            rpath = utils.relPath(path)
            try:
                real = realfiles.get(path)
                real.read()
                fileTags = real.tags
                length = real.length
                filePosition = real.position
            except OSError as e:
                if not os.path.exists(path):
                    fileTags = tags.Storage()
                    filePosition = None
                    length = 0
                    fileTags[tags.TITLE] = ["[NOT FOUND] {}".format(os.path.basename(rpath))]
                else:
                    raise ElementGetError('could not open file "{}":\n{}'.format(rpath, e))
            
            id = db.idFromPath(rpath)
            if id is None:
                id = tIdFromPath(rpath)
                flags = []
            else:
                flags = db.flags(id)
                logger.warning("loadFromFilesystem called on '{}', which is in DB. Are you sure "
                               "this is correct?".format(rpath))
                # TODO: Load private tags!
            elem = File(level,id = id,path=rpath,length=length,tags=fileTags,flags=flags)
            elem.fileTags = fileTags.copy()
            if filePosition is not None:
                elem.filePosition = filePosition
            level.elements[id] = elem
    
    def insertChildren(self, parentId, insertions):
        db.write.addContents([(parentId, pos, id) for pos,id in insertions])
        super().removeChildren(parentId, insertions)
        
    def removeChildren(self, parentId, positions):
        db.write.removeContents([(parentId, pos) for pos in positions])
        super().removeChildren(parentId, positions)
    
    def addTagValue(self,tag,value,elements,emitEvent=True):
        super().addTagValue(tag,value,elements,emitEvent=False)
        failedElements = self.saveTagsToFileSystem(elements)
        #TODO: Correct failedElements
        dbElements = [el.id for el in elements if el.isInDB() and not el in failedElements]
        if len(dbElements):
            dbwrite.addTagValues(dbElements,tag,[value])
        
        if emitEvent:
            self.emitEvent([element.id for element in elements])
            
    def removeTagValue(self,tag,value,elements,emitEvent=True):
        super().removeTagValue(tag,value,elements,emitEvent=False)
        failedElements = self.saveTagsToFileSystem(elements)
        #TODO: Correct failedElements
        dbElements = [el.id for el in elements if el.isInDB() and not el in failedElements]
        if len(dbElements):
            dbwrite.removeTagValuesById(dbElements,tag,db.idFromValue(tag,value))
        else: assert all(element.id < 0 for element in elements)
        
        if emitEvent:
            self.emitEvent([element.id for element in elements])
            
    def changeTagValue(self,tag,oldValue,newValue,elements,emitEvent=True):
        super().changeTagValue(tag,oldValue,newValue,elements,emitEvent=False)
        failedElements = self.saveTagsToFileSystem(elements)
        #TODO: Correct failedElements
        dbElements = [el.id for el in elements if el.isInDB() and not el in failedElements]
        if len(dbElements):
            dbwrite.changeTagValueById(dbElements,tag,db.idFromValue(tag,oldValue),
                                       db.idFromValue(tag,newValue,insert=True))
        if emitEvent:
            self.emitEvent([element.id for element in elements])
        
    def saveTagsToFileSystem(self,elements):
        failedElements = []
        for element in elements:
            if not element.isFile():
                continue
            try:
                real = realfiles.get(element.path)
                real.read()
                real.tags = element.tags.withoutPrivateTags()
                real.saveTags()
            except IOError as e:
                logger.error("Could not save tags of '{}'.".format(element.path))
                logger.error("Error was: {}".format(e))
                failedElements.append(elements)
                continue
        return failedElements
    
    def renameFiles(self, map, emitEvent = True):
        """on the real level, files are renamed on disk and in DB."""
        super().renameFiles(map, emitEvent)
        import os
        for id, (oldPath, newPath) in map.items():
            os.renames(utils.absPath(oldPath), utils.absPath(newPath))
        db.write.changeFilePaths([ (id, newPath) for id, (_, newPath) in map.items()])
        if emitEvent:
            self.changed.emit(FileRenameEvent(list(map.items())))
            
    def addFlag(self,flag,elements,emitEvent=True):
        super().addFlag(flag,elements,emitEvent=False)
        ids = [element.id for element in elements]
        db.write.addFlag(ids,flag)
        if emitEvent:
            self.emitEvent(ids)
            
    def removeFlag(self,flag,elements,emitEvent=True):
        super().removeFlag(flag,elements,emitEvent=False)
        ids = [element.id for element in elements]
        db.write.removeFlag(ids,flag)
        if emitEvent:
            self.emitEvent(ids)
            
    def _setData(self,type,elementToData):
        super()._setData(type,elementToData)
        values = []
        for element,data in elementToData.items():
            if data is not None:
                values.extend((element.id,type,i,d) for i,d in enumerate(data))
        db.transaction()
        db.query("DELETE FROM {}data WHERE type = ? AND element_id IN ({})"
                 .format(db.prefix,db.csIdList(elementToData.keys())),type)
        if len(values) > 0:
            db.multiQuery("INSERT INTO {}data (element_id,type,sort,data) VALUES (?,?,?,?)"
                          .format(db.prefix),values)
        db.commit()
        
def idFromPath(path):
    """Return the id for the given path. For elements in the database this is a positive number. Otherwise
    the temporary id is returned or a new one is created."""
    id = db.idFromPath(path)
    if id is not None:
        return id
    else: return tIdFromPath(path)

def pathFromId(id):
    if id < 0:
        return pathFromTId(id)
    else:
        return db.path(id)

_currentTId = 0 # Will be decreased by one every time a new TID is assigned
_tIds = {} # TODO: Is there any chance that items will be removed from here?
_paths = {}

def tIdFromPath(path):
    if path in _tIds:
        return _tIds[path]
    else:
        global _currentTId
        _currentTId -= 1
        _paths[_currentTId] = path
        _tIds[path] = _currentTId
        return _currentTId

def createTId():
    global _currentTId
    _currentTId -= 1
    return _currentTId

def pathFromTId(tid):
    return _paths[tid]
