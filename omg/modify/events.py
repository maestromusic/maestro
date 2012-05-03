# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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
assert False
from .. import tags
from .. import logging
from ..application import ChangeEvent

logger = logging.getLogger(__name__)


class ElementChangeEvent(ChangeEvent):
    """A generic change event for all sorts of element modifications. To handle events generically you will
    usually first check whether the event affects your particular component using the type, ''ids'' or the
    attributes ''contentsChanged'', ''tagsChanged'' and ''flagsChanged'' and then use ''applyTo''.
    
    Parameters:
    
        - level: either ''REAL'' or ''EDITOR''
        - changes: dict mapping element ids to tuples containing the element before and after the change
        - contentsChanged,tagsChanged,flagsChanged: If one of these parameters is True the corresponding data
          may have changed. If it is false, you are save to assume that it did not change.
          
    \ """
    def __init__(self, level, changes, contentsChanged=False,tagsChanged=True,flagsChanged=True):
        self.changes = changes
        self.level = level
        self.contentsChanged = contentsChanged
        self.tagsChanged = tagsChanged
        self.flagsChanged = flagsChanged
    
    def ids(self):
        """Return a list of the ids of the elements changed by this event."""
        return self.changes.keys()
    
    def getNewContentsCount(self, element):
        return self.changes[element.id].getContentsCount()
    
    def applyTo(self, element):
        """Apply the changes stored in this event to *element*."""
        element.copyFrom(self.changes[element.id], copyContents = self.contentsChanged)
        
    def getTags(self,id):
        """Return the new tags of the element with the given id. This may only be called if ''tagsChanged''
        is True and *id* is in ''ids''."""
        # Note that many subclasses that do not change tags and have no changes attribute
        # do not reimplement this method.
        assert self.tagsChanged
        return self.changes[id].tags
    
    def getFlags(self,id):
        """Return the new flags of the element with the given id. This may only be called if ''flagsChanged''
        is True and *id* is in ''ids''."""
        # Note that many subclasses that do not change flags and have no changes attribute
        # do not reimplement this method.
        assert self.flagsChanged
        return self.changes[id].flags
    
    def __str__(self):
        return type(self).__name__ + '(level={}, contentsChanged={}, tagsChanged = {}, flagsChanged = {})'.format(
                self.level, self.contentsChanged, self.tagsChanged, self.flagsChanged)


class FilesAddedEvent(ChangeEvent):
    """An event notifying that files have been added to the database."""
    
    def __init__(self, paths):
        """Create the event. *paths* is a list of file paths created."""         
        super().__init__()
        self.paths = paths
        
class FilesRemovedEvent(ChangeEvent):
    """An event notifying that files have been removed from the database."""
    
    def __init__(self, paths, disk = False):
        """Create the event. *paths* is a list of paths. If *disk = True*,
        the files have also been deleted from disk (not only from the database)."""
        super().__init__()
        self.paths = paths
        self.disk = disk
    
class ElementsDeletedEvent(ChangeEvent):
    """Special event that is sent when elements are completely deleted from the database."""
    def __init__(self,elids):
        self.elids = elids
        
    def ids(self):
        return self.elids
    
    
class SingleElementChangeEvent(ElementChangeEvent):
    """A specialized modify event if only one element (tags, position, ...) is modified."""
    
    tagsChanged = True
    flagsChanged = True
    contentsChanged = False
    
    def __init__(self, level, element):
        self.element = element
        self.level = level
        
    def ids(self):
        return [self.element.id]
    
    def getNewContentsCount(self, element):
        return 0
    
    def applyTo(self, element):
        element.copyFrom(self.element, copyContents = False)
    
    def getTags(self,id):
        if id == self.element.id:
            return self.element.tags
        else: return None
        
    def getFlags(self,id):
        if id == self.element.id:
            return self.element.flags
        else: return None
        
        
class MajorFlagChangeEvent(SingleElementChangeEvent):
    """A modify event for toggling the major flag of an element."""
    
    tagsChanged = False
    flagsChanged = False
    
    def __init__(self, level, id, flag):
        self.level = level
        self.id = id
        self.flag = flag
        
    def ids(self):
        return [self.id]
    
    def applyTo(self, element):
        element.major = self.flag
    
    def __str__(self):
        return "MajorFlagChangeEvent({}, id={}, flag={})".format(self.level, self.id, self.flag)


class PositionChangeEvent(ElementChangeEvent):
    """An event for the case that the position of several elements below the same parent are changed."""
    
    contentsChanged = True
    tagsChanged = False
    flagsChanged = False
    
    def __init__(self, level, parentId, positionMap):
        '''Initializes the event. *positionMap* is a dict mapping old to new positions.'''
        self.parentId = parentId
        self.positionMap = positionMap
        self.level = level
        
    def ids(self):
        return [self.parentId]
    
    def getNewContentsCount(self, element):
        return len(element.contents)
    
    def applyTo(self, element):
        raise NotImplementedError("PositionChangeEvent to complicated for applyTo -- use RootedTreeModel.changePositions!")
    
    def __str__(self):
        return "PositionChangeEvent(level={}, {}, {})".format(self.level, self.parentId, self.positionMap)

        
    
class InsertContentsEvent(ElementChangeEvent):
    """A specialized modify event for the insertion of elements into a container."""
    
    contentsChanged = True
    tagsChanged = False
    flagsChanged = False
    
    def __init__(self, level, insertions):
        """Create the event. *insertions* is a dict mapping parentId to a list of (position,element)
        pairs."""
        self.insertions = insertions
        self.level = level
        
    def ids(self):
        return self.insertions.keys()
    
    def getNewContentsCount(self, element):
        return element.getContentsCount() + len(self.insertions[element.id])
    
    def applyTo(self, element):
        logger.warning('this function is crappy and should not be used.')
        for pos, ins in self.insertions[element.id]:
            insertedElem = ins.copy()
            insertedElem.parent = element
            inserted = False
            for i, elem in enumerate(element.contents):
                if elem.position > pos:
                    element.contents[i:i] = [insertedElem]
                    inserted = True
                    break
            if not inserted:
                elem.contents.append(insertedElem)
    def __str__(self):
        return 'InsertContentsEvent({}, insertions={})'.format(self.level, self.insertions)

class RemoveContentsEvent(ElementChangeEvent):
    """A specialized modify event for the removal of contents of containers."""
    
    contentsChanged = True
    tagsChanged = False
    flagsChanged = False
    
    def __init__(self, level, removals):
        """Initialize the event. *removals* is a dict mapping parent ids to a list of positions at which
        elements are removed."""
        self.removals = removals
        self.level = level
        
    def ids(self):
        return self.removals.keys()
    
    def getNewContentsCount(self, element):
        return element.getContentsCount() - len(self.removals[element.id])
    
    def applyTo(self, element):
        element.contents = [ child for child in element.contents if child.position not in self.removals[element.id] ]
        
    def __str__(self):
        return 'RemoveContentsEvent({}, removals={})'.format(self.level, self.removals)
            


 
class SortValueChangedEvent(ChangeEvent):
    """This event is emitted when a sortvalue changes."""
    def __init__(self,tag,valueId,oldValue,newValue):
        self.tag,self.valueId,self.oldValue,self.newValue = tag,valueId,oldValue,newValue
        
        
class HiddenAttributeChangedEvent(ChangeEvent):
    """This event is emitted when the "hidden" attribute of a tag value changes."""
    def __init__(self, tag, valueId, newState):
        self.tag, self.valueId, self.newState = tag, valueId, newState


class CoverChangeEvent(ElementChangeEvent):
    """Emit this event when the cover of the element with the given id has changed."""
    def __init__(self,id):
        from . import REAL
        super().__init__(REAL,None)
        self.tagsChanged = False
        self.flagsChanged = False
        self.id = id
        
    def applyTo(self,element):
        element.deleteCoverCache()
    
    def ids(self):
        return (self.id,)
    
