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

from .. import database as db, tags, flags, realfiles, utils, config, logging
from . import File, Container
    
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
            level.elements[id].contents[pos] = contentId
        
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
