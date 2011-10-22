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

from .. import tags
from .. import logging

logger = logging.getLogger(__name__)

class ChangeEvent:
    """Abstract super class for all changeevents."""
    pass


class ElementChangeEvent(ChangeEvent):
    """A generic change event for all sorts of element modifications. To handle events generically you will
    usually first check whether the event affects your particular component using the type, ''ids'' or the
    attributes ''contentsChanged'', ''tagsChanged'' and ''flagsChanged'' and then use ''applyTo''.
    
    Parameters:
    
        - level: either ''modify.REAL'' or ''modify.EDITOR''
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
    
    def __init__(self, level, element):
        super().__init__(level, element)
        
    def applyTo(self, element):
        element.major = self.element.major


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
        logger.warning('this function is crappy and should not be used.')
        assert element.id == self.parentId
        for elem in element.contents:
            if elem.position in self.positionMap:
                elem.position = self.positionMap[elem.position]
        if hasattr(element, 'sortContents'):
            element.sortContents()

        
    
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
        elem.contents = [ child for child in elem.contents if child.position not in self.removals[element.id] ]
            

class TagFlagChangeEvent(ElementChangeEvent):
    """This event is emitted when tags and/or flags of an arbitrary number of elements changes. *newData* is
    a dict mapping elements ids to tuples containing first the new tags and secondly the new flags. Either
    part may be None, indicating that tags or flags did not change."""
    
    contentsChanged = False
    
    def __init__(self,level,newData):
        self.level = level
        self.newData = newData
        self.tagsChanged = any(new[0] is not None for new in newData.values())
        self.flagsChanged = any(new[1] is not None for new in newData.values())
        
    def ids(self):
        return self.newData.keys()
    
    def applyTo(self,element):
        newTags,newFlags = self.newData[element.id]
        if element.tags is not None and newTags is not None:
            element.tags = newTags.copy()
        if element.flags is not None and newFlags is not None:
            element.flags = list(newFlags)
        
    def __str__(self):
        return "Modify tags/flags"
    
    def getTags(self,id):
        return self.newData[id][0]

    def getFlags(self,id):
        return self.newData[id][1]
    
            
class SingleTagChangeEvent(TagFlagChangeEvent):
    """Abstract superclass for events in which one tag changes in several elements."""
    tagsChanged = True
    flagsChanged = False
    
    def __init__(self,level,tag,elementIDs):
        assert isinstance(tag,tags.Tag)
        self.level = level
        self.tag = tag
        self.elementIDs = elementIDs
        
    def ids(self):
        return self.elementIDs
    
    def getTags(self,id):
        raise NotImplementedError() # This is currently not used
        
    
class TagValueAddedEvent(SingleTagChangeEvent):
    def __init__(self,level,tag,value,elementIDs):
        super().__init__(level,tag,elementIDs)
        self.value = value

    def applyTo(self,element):
        if element.tags is not None:
            element.tags.add(self.tag,self.value)
            
    def __str__(self):
        return "Add: {} {} {}".format(self.tag,self.value,self.elementIDs)
    
    
class TagValueRemovedEvent(SingleTagChangeEvent):
    def __init__(self,level,tag,value,elementIDs):
        super().__init__(level,tag,elementIDs)
        self.value = value

    def applyTo(self,element):
        if element.tags is not None:
            element.tags.remove(self.tag,self.value)
        
    def __str__(self):
        return "Remove: {} {} {}".format(self.tag,self.value,self.elementIDs)
    

class TagValueChangedEvent(SingleTagChangeEvent):
    def __init__(self,level,tag,oldValue,newValue,elementIDs):
        super().__init__(level,tag,elementIDs)
        self.oldValue = oldValue
        self.newValue = newValue

    def applyTo(self,element):
        if element.tags is not None:
            element.tags.replace(self.tag,self.oldValue,self.newValue)

    def __str__(self):
        return "Change: {} {}->{} {}".format(self.tag,self.oldValue,self.newValue,self.elementIDs)


class SingleFlagChangeEvent(TagFlagChangeEvent):
    """Abstract superclass for events in which one flag changes in several elements."""
    tagsChanged = False
    flagsChanged = True
    
    def __init__(self,level,flag,elements):
        self.level = level
        self.flag = flag
        self.elements = elements
        
    def ids(self):
        return [element.id for element in self.elements]

    def getFlags(self,id):
        raise NotImplementedError() # This is currently not used        
        
    
class FlagAddedEvent(SingleFlagChangeEvent):
    """FlagAddedEvents are used when a flag is added to one or more elements."""
    def applyTo(self,element):
        if element.flags is not None:
            if self.flag not in element.flags:
                element.flags.append(self.flag)
                return True
            else: return False
        

class FlagRemovedEvent(SingleFlagChangeEvent):
    """FlagRemovedEvent are used when a flag is remove from one or more elements."""
    def applyTo(self,element):
        if element.flags is not None:
            if self.flag in element.flags:
                element.flags.remove(self.flag)
                return True
            else: return False


class TagTypeChangedEvent(ChangeEvent):
    """TagTypeChangedEvents are used when a tagtype (like artist, composer...) is added, changed or deleted.
    Contrary to ModifyEvents these events are sent over the tagTypeChanged-signal of the dispatcher.
    """
    def __init__(self,action,tagType):
        assert action in range(1,4) # ADDED,CHANGED or DELETED
        self.action = action
        self.tagType = tagType


class FlagTypeChangedEvent(ChangeEvent):
    """TagTypeChangedEvents are used when a flagtype is added, changed or deleted. Contrary to ModifyEvents
    these events are sent over the tagTypeChanged-signal of the dispatcher.
    """
    def __init__(self,action,flagType):
        assert action in range(1,4) # ADDED,CHANGED or DELETED
        self.action = action
        self.flagType = flagType
        
        
class SortValueChangedEvent(ChangeEvent):
    """This event is emitted when a sortvalue changes."""
    def __init__(self,tag,valueId,oldValue,newValue):
        self.tag,self.valueId,self.oldValue,self.newValue = tag,valueId,oldValue,newValue
        
class HiddenAttributeChangedEvent(ChangeEvent):
    """This event is emitted when the "hidden" attribute of a tag value changes."""
    def __init__(self, tag, valueId, newState):
        self.tag, self.valueId, self.newState = tag, valueId, newState
