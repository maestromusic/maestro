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
from .elements import File, Container, ContentList
from .. import database as db, realfiles, utils, config, logging, modify
from ..modify import real
from ..database import write as dbwrite
from ..application import ChangeEvent

real = None
editor = None

logger = logging.getLogger(__name__)

def init():
    global real,editor
    real = RealLevel()
    editor = Level("EDITOR",real)
    

class ElementGetError(RuntimeError):
    """Error indicating that an element failed to be loaded by some level."""
    pass


class ConsistencyError(RuntimeError):
    """Error signaling a consistency violation of the element data."""
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
        

class Level(QtCore.QObject):
    #TODO comment
    changed = QtCore.pyqtSignal(ChangeEvent)
    """Signal that is emitted if something changes on this level. The first argument is a list of Ids of elements
    whose tags, flags, major status, ... has changed (things affecting only the element itself). The second list
    contains IDs of containers whose contents have changed."""
    
    def __init__(self,name,parent):
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
    
    def load(self,ids,ignoreUnknownTags=False):
        """Load all elements given by the list of ids *ids* into this level (do nothing for elements which
        are already loaded."""
        notFound = []
        for id in ids:
            if id not in self.elements:
                notFound.append(id)
        self.parent.loadIntoChild(notFound,self,ignoreUnknownTags)
        
    def loadIntoChild(self,ids,child,ignoreUnknownTags=False):
        """Load all elements given by the list of ids *ids* into the level *child*. Do not check whether
        elements are already loaded there."""
        notFound = []
        for id in ids:
            if id in self.elements:
                child.elements[id] = self.elements[id].copy(child)
            else: notFound.append(id)
        self.parent.loadIntoChild(notFound,self,ignoreUnknownTags)
                
    def loadPaths(self,paths,ignoreUnknownTags=False):
        #TODO comment
        ids = [idFromPath(path) for path in paths]
        self.load(ids,ignoreUnknownTags)
        
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
        parent = self.get(parentId)
        parent.contents.insert(position, childId)
        if not parentId in self.get(childId).parents:
            self.get(childId).parents.append(parentId)
        
    def removeChild(self, parentId, position):
        """Remove element at *position* from container with id *parentId*."""
        parent = self.get(parentId)
        childId = parent.contents.getId(position)
        parent.contents.remove(pos = position)
        if childId not in parent.contents.ids:
            self.get(childId).parents.remove(parentId)
        
    
class RealLevel(Level):
    def __init__(self):
        super().__init__('REAL',None)
        # This hack makes the inherited implementations of get and load work with the overwritten
        # implementation of loadIntoChild
        self.parent = self
    
    def loadIntoChild(self,ids,child, askOnNewTags = True):
        notFound = []
        for id in ids:
            if id in self.elements:
                child.elements[id] = self.elements[id].copy()
            else: notFound.append(id)
        if len(notFound) > 0:
            positiveIds = [id for id in notFound if id > 0]
            paths = [pathFromTId(id) for id in notFound if id < 0]
            if len(positiveIds) > 0:
                self.loadFromDB(positiveIds,child)
            if len(paths) > 0:
                self.loadFromFileSystem(paths,child,askOnNewTags)
            
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
    
    def loadFromFileSystem(self,paths,level, askOnNewTags = True):
        #TODO: comment
        for path in paths:
            rpath = utils.relPath(path)
            logger.debug("reading file {} from filesystem".format(rpath))
            try:
                readOk = False
                while not readOk:
                    try:
                        real = realfiles.get(path)
                        real.read()
                        readOk = True
                    except tags.UnknownTagError as e:
                        # TODO: respect askOnNEwTags parameter (or remove it)
                        # TODO: wrap this up as a separate function stored somewhere else
                        from ..gui.tagwidgets import NewTagTypeDialog
                        QtGui.QApplication.changeOverrideCursor(Qt.ArrowCursor)
                        text = self.tr('Unknown tag\n{1}={2}\n found in \n{0}.\n What should its type be?')\
                                           .format(rpath,e.tagname,e.values)
                        dialog = NewTagTypeDialog(e.tagname, text = text, includeDeleteOption = True)
                        ret = dialog.exec_()
                        if ret == dialog.Accepted:
                            pass
                        elif ret == dialog.Delete or ret == dialog.DeleteAlways:
                            if ret == dialog.DeleteAlways:
                                config.options.tags.always_delete = config.options.tags.always_delete + [e.tagname]
                            logger.info('REMOVE TAG {0} from {1}'.format(e.tagname, rpath))
                            re = realfiles.get(path)
                            re.remove(e.tagname)
                        else:
                            raise ElementGetError('User aborted "new tag" dialog')
                fileTags = real.tags
                length = real.length
                fileTags.position = real.position
            except OSError:
                raise ElementGetError('could not open file: "{}"'.format(rpath))
            
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
            level.elements[id] = elem
    
    def addTagValue(self,tag,value,elements,emitEvent=True):
        super().addTagValue(tag,value,elements,emitEvent=False)
        failedElements = self.saveTagsToFileSystem(elements)
        #TODO: Correct failedElements
        dbwrite.addTagValues([el.id for el in elements if el.isInDB() and not el in failedElements],
                             tag,[value])
        if emitEvent:
            self.emitEvent([element.id for element in elements])
            
    def removeTagValue(self,tag,value,elements,emitEvent=True):
        super().removeTagValue(tag,value,elements,emitEvent=False)
        failedElements = self.saveTagsToFileSystem(elements)
        #TODO: Correct failedElements
        dbwrite.removeTagValuesById([el.id for el in elements if el.isInDB() and not el in failedElements],
                                 tag,db.idFromValue(tag,value))
        if emitEvent:
            self.emitEvent([element.id for element in elements])
            
    def changeTagValue(self,tag,oldValue,newValue,elements,emitEvent=True):
        super().changeTagValue(tag,oldValue,newValue,elements,emitEvent=False)
        failedElements = self.saveTagsToFileSystem(elements)
        #TODO: Correct failedElements
        dbwrite.changeTagValueById([el.id for el in elements if el.isInDB() and not el in failedElements],
                                 tag,db.idFromValue(tag,oldValue),db.idFromValue(tag,newValue,insert=True))
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
            
#TODO: move into its own file
class CommitCommand(QtGui.QUndoCommand):
    """The CommitCommand is used to "commit" the state of some elements in one level to its parent level.
    If the parent level is *real*, then also the database and, if needed, files on disk are updated
    accordingly."""
    
    def __init__(self, level, ids, text = None):
        """Sets up a commit command for the given *ids* in *level*."""
        super().__init__(text)
        self.level = level
        
        allIds = set(ids)
        # add children's IDs to ensure consistent commit
        def addChildren(ids):
            if len(ids) == 0:
                return set()
            newIds = set()
            for id in ids:
                elem = self.level.get(id)
                if elem.isContainer():
                    newIds.update(childId for childId in elem.contents.ids if childId in self.level and childId not in allIds)
            allIds.update(newIds)
            addChildren(newIds)                    
        addChildren(allIds)
        
        self.real = level.parent is real # a handy shortcut
        if self.real:
            self.newInDatabase = [ id for id in allIds if id < 0 ]
            self.realFileChanges = {}
            self.idMap = None
        else:
            self.newId = self.oldId = lambda x : x  #TODO wtf?
            
        self.newElements = []
        self.flagChanges, self.tagChanges, self.contentsChanges, self.majorChanges = {}, {}, {}, {}
        self.ids, self.contents = [], []
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
            changeElement = True
            self.newElements.append(id)
            oldTags = None
            oldFlags = []
            if myEl.isContainer():
                oldMajor = None
                oldContents = ContentList()  
        
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
                    fileTags = myEl.fileTags
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
        return changeElement, changeContents
            
    def redo(self):
        if self.real:
            # create new elements in DB to obtain id map, and change IDs in current level 
            db.transaction()
            if self.idMap is None:
                # first redo -> prepare id mapping
                self.idMap = modify.real.createNewElements(self.level, self.newInDatabase)
                self.newId = utils.dictOrIdentity(self.idMap)
                self.oldId = utils.dictOrIdentity({b:a for a,b in self.idMap.items() })
                # update contentsChanges to use the new ids
                for _, newContents in self.contentsChanges.values():
                    newContents.ids[:] = map(self.newId, newContents.ids)
            else:
                modify.real.createNewElements(self.level, self.newInDatabase, self.idMap)
            # change IDs for new elements
            for id in self.newInDatabase:
                self.level.changeId(id, self.newId(id))
                if id in self.level.parent:
                    # happens if the element is loaded in some playlist
                    self.level.parent.changeId(id, self.newId(id))
                    
        # Add/update elements in parent level
        newFilesPaths = []
        for id in set(self.ids + self.contents):
            elem = self.level.elements[self.newId(id)]
            nid = self.newId(id)
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
                    self.tagChanges[id].apply(pElem)
                if id in self.flagChanges:
                    self.flagChanges[id].apply(pElem)
                if id in self.contentsChanges:
                    pElem.contents = self.contentsChanges[id][1].copy()
                        
        # apply changes in DB, if parent level is real
        if self.real:
            if len(self.majorChanges) > 0:
                db.write.setMajor((self.newId(id), newMajor) for id,(_,newMajor) in self.majorChanges.items())
            if len(self.contentsChanges) > 0:
                modify.real.changeContents({self.newId(id):changes for id, changes in self.contentsChanges.items()})
            if len(self.tagChanges) > 0:
                # although the difference from our level to the parent might affect only a subset of the tags,
                # for elements new to the database the complete tags must be written (happens if a non-db file is
                # loaded in real)
                def dbDiff(id):
                    if id in self.newInDatabase:
                        return tags.TagDifference(None, self.level.get(self.newId(id)).tags)
                    else:
                        return self.tagChanges[id]
                modify.real.changeTags({self.newId(id):dbDiff(id) for id in self.tagChanges.keys()})
            if len(self.flagChanges) > 0:
                modify.real.changeFlags({self.newId(id):diff for id,diff in self.flagChanges.items()})
            db.commit()
            for path,changes in self.realFileChanges.items():
                logger.debug("changing file tags: {0}-->{1}".format(path, changes))
                modify.real.changeFileTags(path, changes)
        self.level.parent.emitEvent([self.newId(id) for id in self.ids], [self.newId(id) for id in self.contents])
        self.level.emitEvent([self.newId(id) for id in self.ids], []) # no contents changed in current level!
        
        if len(newFilesPaths) > 0:
            self.level.parent.changed.emit(FileCreateDeleteEvent(newFilesPaths))
        self.newFilesPaths = newFilesPaths # store for undo
        
    def undo(self):
        if self.real:
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
                modify.real.changeContents(contentsChangesExisting)
            tagChangesExisting = {self.newId(id):diff for id,diff in self.tagChanges.items()
                                    if id not in self.newInDatabase}
            if len(tagChangesExisting) > 0:
                modify.real.changeTags(tagChangesExisting, reverse = True)
            flagChangesExisting = {self.newId(id):diff for id,diff in self.tagChanges.items()
                                    if id not in self.newInDatabase}
            if len(flagChangesExisting) > 0:
                modify.real.changeFlags(flagChangesExisting, reverse = True)
            db.commit()
        
        for id in set(self.ids + self.contents):
            if id in self.newElements:
                del self.level.parent.elements[self.newId(id)]
            else:
                pElem = self.level.parent.elements[self.newId(id)]
                if id in self.majorChanges:
                    pElem.major = self.majorChanges[id][0]
                if id in self.tagChanges:
                    self.tagChanges[id].revert(pElem)
                if id in self.flagChanges:
                    self.flagChanges[id].revert(pElem)
                if id in self.contentsChanges:
                    pElem.contents = self.contentsChanges[id][0].copy()
        
        if self.real:
            for id in self.newInDatabase:
                self.level.changeId(self.newId(id), id)
                if self.newId(id) in self.level.parent:
                    self.level.parent.changeId(self.newId(id), id)
            db.commit()
            for path, changes in self.realFileChanges.items():
                logger.debug("reverting file tags: {0}<--{1}".format(path, changes))
                modify.real.changeFileTags(path, changes, reverse = True)
        self.level.parent.emitEvent(self.ids, self.contents)
        self.level.emitEvent(self.ids, []) # no contents changed in current level!
        if len(self.newFilesPaths) > 0:
            self.level.parent.changed.emit(FileCreateDeleteEvent(None, self.newFilesPaths))
                
            

            

def idFromPath(path):
    """Return the id for the given path. For elements in the database this is a positive number. Otherwise
    the temporary id is returned or a new one is created."""
    id = db.idFromPath(path)
    if id is not None:
        return id
    else: return tIdFromPath(path)

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
