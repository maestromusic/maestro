# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer, Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#

from .. import tags
from .. import logging

logger = logging.getLogger(__name__)

class ChangeEvent:
    """Abstract super class for all changeevents."""
    pass


class ElementChangeEvent(ChangeEvent):
    
    """A generic change event for all sorts of element modifications."""
    def __init__(self, level, changes, contentsChanged=False,tagsChanged=True,flagsChanged=True):
        self.changes = changes
        self.level = level
        self.contentsChanged = contentsChanged
        self.tagsChanged = tagsChanged
        self.flagsChanged = flagsChanged
    
    def ids(self):
        return self.changes.keys()
    
    def getNewContentsCount(self, element):
        return self.changes[element.id].getContentsCount()
    
    def applyTo(self, element):
        element.copyFrom(self.changes[element.id], copyContents = self.contentsChanged)


class ElementsDeletedEvent(ChangeEvent):
    """Special event that is sent when elements are completely deleted from the database."""
    def __init__(self,elids):
        self.elids = elids
        
    def ids(self):
        return self.elids
    
    
class SingleElementChangeEvent(ElementChangeEvent):
    """A specialized modify event if only one element (tags, position, ...) is modified."""
    def __init__(self, level, element):
        self.element = element
        self.level = level
        self.contentsChanged = False
        self.tagsChanged = True
        self.flagsChanged = True
        
    def ids(self):
        return [self.element.id]
    
    def getNewContentsCount(self, element):
        return 0
    
    def applyTo(self, element):
        element.copyFrom(self.element, copyContents = False)


class MajorFlagChangeEvent(SingleElementChangeEvent):
    """A modify event for toggling the major flag of an element."""
    def __init__(self, level, element):
        super().__init__(level, element)
        self.tagsChanged = False
        self.flagsChanged = False
        
    def applyTo(self, element):
        element.major = self.element.major


class PositionChangeEvent(ElementChangeEvent):
    """An event for the case that the position of several elements below the same parent are changed."""
    def __init__(self, level, parentId, positionMap):
        '''Initializes the event. *positionMap* is a dict mapping old to new positions.'''
        self.contentsChanged = True
        self.parentId = parentId
        self.positionMap = positionMap
        self.tagsChanged = False
        self.flagsChanged = False
        self.level = level
        
    def ids(self):
        return [self.parentId]
    
    def getNewContentsCount(self, element):
        return len(element.contents)
    
    def applyTo(self, element):
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
            

class TagChangeEvent(ElementChangeEvent):
    
    contentsChanged = False
    tagsChanged = True
    flagsChanged = False
    
    def __init__(self,level,newTags):
        self.level = level
        self.newTags = newTags
        
    def ids(self):
        return self.newTags.keys()
    
    def applyTo(self,element):
        assert element.id in self.newTags
        if element.tags is not None:
            element.tags = self.newTags[element.id].copy()
    
    def __str__(self):
        return "Change tags of {} elements".format(len(self.newTags))

            
class SingleTagChangeEvent(TagChangeEvent):
    def __init__(self,level,tag,elementIDs):
        assert isinstance(tag,tags.Tag)
        self.level = level
        self.tag = tag
        self.elementIDs = elementIDs
        
    def ids(self):
        return self.elementIDs
    
    
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
    

class FlagChangeEvent(ElementChangeEvent):
    
    contentsChanged = False
    tagsChanged = False
    flagsChanged = True
    
    def __init__(self,level,newFlags):
        self.level = level
        self.newFlags = newFlags    
        
    def ids(self):
        return self.newFlags.keys()
    
    def applyTo(self,element):
        assert element.id in self.newFlags
        if element.flags is not None:
            element.flags = list(self.newFlags[element.id])
            
    def __str__(self):
        return "Modify flags"
    
    
class SingleFlagChangeEvent(FlagChangeEvent):
    """Abstract superclass for events where one flag changes in several elements."""
    def __init__(self,level,flag,elements):
        self.level = level
        self.flag = flag
        self.elements = elements
        
    def ids(self):
        return [element.id for element in self.elements]
        
    
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
