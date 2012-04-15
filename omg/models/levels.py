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
from .. import database as db, tags, flags, realfiles, utils, config, logging, modify
from . import File, Container, ContentList
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

class Level(QtCore.QObject):
    changed = QtCore.pyqtSignal(list, list)
    """Signal that is emitted if something changes on this level. The first argument is a list of Ids of elements
    whose tags, flags, major status, ... has changed (things affecting only the element itself). The second list
    contains IDs of containers whose contents have changed."""
    
    def __init__(self,name,parent):
        super().__init__()
        self.name = name
        self.parent = parent
        self.elements = {}
        
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
                
    def loadPaths(self,paths,aDict,ignoreUnknownTags=False):
        ids = [idFromPath(path) for path in paths]
        self.load(ids,aDict,ignoreUnknownTags)
  
    def changeId(self, old, new):
        """Change the id of some element from *old* to *new*. This should only be called from within appropriate
        UndoCommands, and only if (old in self) is True. Takes care of contents and parents, too."""
        elem = self.elements[old]
        del self.elements[old]
        elem.id = new
        self.elements[new] = elem
        for parentID in elem.parents:
            parentContents = self.elements[parentID].contents
            parentContents.ids = [ new if id == old else id for id in parentContents.ids ]
        if elem.isContainer():
            for childID in elem.contents.ids:
                if childID in self.elements:
                    self.elements[childID].parents = [ new if id == old else old for id in self.elements[childID].parents ]
        
        
    def __contains__(self, id):
        """Returns if the given id is loaded in this level. Note that if the id could be loaded from the
        parent but is not contained in this level, then *False* is returned."""
        return self.elements.__contains__(id)
    
    def __str__(self):
        return 'Level({})'.format(self.name)
    
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
                        # TODO: wrap this up as a separate function stored somewhere else
                        from ..gui.tagwidgets import NewTagTypeDialog
                        QtGui.QApplication.changeOverrideCursor(Qt.ArrowCursor)
                        text = self.tr('Unknown tag\n{1}={2}\n found in \n{0}.\n What should its type be?').format(rpath,
                                                                                                                   e.tagname,
                                                                                                                   e.values)
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

class CommitCommand(modify.ElementChangeCommand):
    """The CommitCommand is used to "commit" the state of some elements in one level to its parent level.
    If the parent level is *real*, then also the database and, if needed, files on disk are updated
    accordingly."""
    
    def __init__(self, level, ids, text = None):
        """Sets up a commit command for the given *ids* in *level*."""
        super().__init__(level, text)
        
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
            self.newId = self.oldId = lambda x : x
            
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
        # create new elements in DB to obtain id map, if necessary
        if self.real and len(self.newInDatabase) > 0: 
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
        # nothing else to be changed in the current (child) level. Update elements in parent
        
        for id in set(self.ids + self.contents):
            elem = self.level.elements[self.newId(id)]
            nid = self.newId(id)
            if id in self.newElements:
                copy = elem.copy()
                copy.level = self.level.parent
                self.level.parent.elements[nid] = copy
            else:
                pElem = self.parent.level.elements[nid]
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
        self.level.parent.changed.emit([self.newId(id) for id in self.ids], [self.newId(id) for id in self.contents])
        self.level.changed.emit([self.newId(id) for id in self.ids], []) # no contents changed in current level!
        
    def undo(self):
        if self.real:
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
        self.level.parent.changed.emit(self.ids, self.contents)
        self.level.changed.emit(self.ids, []) # no contents changed in current level!
                
            

            

def idFromPath(path):
    id = db.idFromPath(path)
    if id is not None:
        return id
    else: return tIdFromPath(path)

_currentTId = 0
_tIds = {}
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
