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
from ..modify.commands import ElementChangeCommand
from ..modify.treeactions import TreeAction
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
    changed = QtCore.pyqtSignal(list, bool) # list of affected ids, contents
    
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
                child.elements[id] = self.elements[id].copy(child)
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
                # TODO: Load private tags!
            level.elements[id] = File(level,id = id,path=rpath,length=length,tags=fileTags,flags=flags)

class CommitCommand(ElementChangeCommand):
    
    def __init__(self, level, ids, text = None):
        """Sets up a commit command for the given *ids* in *level*."""
        super().__init__(level, text)
        
        allIds = set(ids)
        import itertools
        # recursively load children's IDs
        #TODO: only load nodes that actually changed
        while True:
            withChildren = allIds | set(itertools.chain.from_iterable(self.level.get(id).contents.ids for id in allIds if self.level.get(id).isContainer()))
            if withChildren  == allIds:
                break
            allIds = withChildren
        self.ids = list(allIds)
        self.contents = False
        if level.parent is real:
            self.idMap = None
        self.newElements = []
        self.flagChanges = {}
        self.tagChanges = {}
        self.contentsChanges = {}
        self.majorChanges = {}
        for id in allIds:
            self.recordChanges(id)
    
    def recordChanges(self, id):
        myEl = self.level.get(id)
        if id in self.level.parent.elements:
            oldEl = self.level.parent.get(id)
            oldTags = oldEl.tags
            oldFlags = oldEl.flags
            if oldEl.isContainer():
                oldMajor = oldEl.major
                oldContents = oldEl.contents
        else:
            self.newElements.append(id)
            oldTags = tags.Storage()
            oldFlags = []
            if myEl.isContainer():
                oldMajor = False
                oldContents = ContentList()  
        
        if oldTags != myEl.tags:
            self.tagChanges[id] = tags.TagDifference(oldTags, myEl.tags)
        if oldFlags != myEl.flags:
            self.flagChanges[id] = flags.FlagDifference(oldFlags, myEl.flags)
        if myEl.isContainer():
            if oldContents != myEl.contents:
                self.contents = True
                self.contentsChanges[id] = (oldContents.copy(), myEl.contents.copy())
            if oldMajor != myEl.major:
                self.majorChanges[id] = (oldMajor, myEl.major)
        
            
    def redoChanges(self):
        logger.debug("commit from {} to {}".format(self.level, self.level.parent))
        logger.debug("  {} new elements".format(len(self.newElements)))
        logger.debug("  {} tag changes".format(len(self.tagChanges)))
        logger.debug("  {} flag changes".format(len(self.flagChanges)))
        logger.debug("  {} content changes".format(len(self.contentsChanges)))
        logger.debug("  {} major changes".format(len(self.majorChanges)))
        
        # create new elements in DB to obtain id map, if necessary
        if len(self.newElements) > 0 and self.level.parent is real:
            self.idMap = modify.real.createNewElements(self.level, self.newElements, self.idMap)
        
        # move commited elements to parent level
        for id in self.ids:
            elem = self.level.elements[id]
            del self.level.elements[id]
            newId = self.idMap[id] if id in self.newElements and self.level.parent is real else id
            self.level.parent.elements[newId] = elem
            elem.id = newId
        
        if self.level.parent is real:
            self.newId = lambda id : self.idMap[id]
        else:
            self.newId = lambda id : id    
        
        # apply changes in DB, if level real
        if self.level.parent is real:
            if len(self.majorChanges) > 0:
                db.write.setMajor((id, oldMajor) for id,(oldMajor,newMajor) in self.majorChanges.items())
            if len(self.contentsChanges) > 0:
                modify.real.changeContents(self.contentsChanges, self.idMap)
            if len(self.tagChanges) > 0:
                modify.real.changeTags(self.tagChanges, self.idMap)
                
        
    def undoChanges(self):
        logger.debug("undo commit from {} to {}".format(self.level, self.level.parent))
        newId = self.newId
        for id in self.ids:
            element = self.level.parent.elements[newId(id)]
            del self.level.parent.elements[newId(id)]
            self.level.elements[id] = element
            if id in self.newElements:
                element.id = id
            else:
                # restore old state in parent level
                oldElement = element.copy()
                if id in self.tagChanges:
                    self.tagChanges[id].revert(oldElement)
                if id in self.flagChanges:
                    self.flagChanges[id].revert(oldElement)
                if id in self.majorChanges:
                    oldElement.major = self.majorChanges[id][0]
                if id in self.contentsChanges:
                    oldElement.contents = self.contentsChanges[id].copy()
        


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
