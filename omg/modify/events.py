# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer, Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#

from .. import tags

class ChangeEvent:
    pass

class ElementChangeEvent(ChangeEvent):
    """A generic change event for all sorts of element modifications."""
    def __init__(self, level, changes, contentsChanged = False):
        self.changes = changes
        self.level = level
        self.contentsChanged = contentsChanged
    
    def ids(self):
        return self.changes.keys()
    
    def getNewContentsCount(self, element):
        return self.changes[element.id].getContentsCount()
    
    def applyTo(self, element):
        element.copyFrom(self.changes[element.id], copyContents = self.contentsChanged)


class NewElementChangeEvent(ElementChangeEvent):
    """This special event is used when new elements are added to the database. Its changes map ids to new
    elements."""
    def __init__(self,changes):
        from .. import REAL
        super().__init__(REAL,changes)
    
    def applyTo(self,element):
        assert element.id in self.changes
        element.id = self.changes[element.id].id


class ElementsDeletedEvent(ChangeEvent):
    """Special event that is sent when elements are completely deleted from the database."""
    def __init__(self,elements):
        self.elements = elements
    
class SingleElementChangeEvent(ElementChangeEvent):
    """A specialized modify event if only one element (tags, position, ...) is modified."""
    def __init__(self, level, element):
        self.element = element
        self.level = level
        self.contentsChanged = False
        
    def ids(self):
        return self.element.id,
    
    def getNewContentsCount(self, element):
        return 0
    
    def applyTo(self, element):
        element.copyFrom(self.element, copyContents = False)


class InsertElementsEvent(ElementChangeEvent):
    """A specialized modify event for the insertion of elements. <insertions> is a dict mapping parentId -> iterable of
    (position, elementList) tuples."""
    def __init__(self, level, insertions):
        self.insertions = insertions
        self.level = level
        self.contentsChanged = True
        
    def ids(self):
        return self.insertions.keys()
    
    def getNewContentsCount(self, element):
        return element.getContentsCount() + sum(map(len, tup[1]) for tup in self.insertions[element.id])
    
    def applyTo(self, element):
        for i, elems in self.insertions[element.id]:
            element.insertContents(i, [e.copy() for e in elems])
            

class RemoveElementsEvent(ElementChangeEvent):
    """A specialized modify event for the removal of elements. Removals is a dict mapping parent ids to an iterable of
    (position, number) tuples, meaning that parent.contents[position,position+number] will be removed. The caller must
    make sure that it is feasable to remove elements in the order they appear in the iterable – i.e. they should be sorted
    decreasing."""
    def __init__(self, level, removals):
        self.removals = removals
        self.level = level
        self.contentsChanged = True
        
    def ids(self):
        return self.removals.keys()
    
    def getNewContentsCount(self, element):
        return element.getContentsCount() - sum(tup[1] for tup in self.removals[element.id])
    
    def applyTo(self, element):
        for index, count in self.removals[element.id]:
            del element.contents[index:index+count]
            

class TagChangeEvent(ElementChangeEvent):
    def __init__(self,changes):
        self.changes = changes
        self.contentsChanged = False
        
    def applyTo(self,element):
        assert element in self.changes
        if element.tags is not None:
            element.tags = self.changes[element].copy()
            
    def __str__(self):
        return "Modify tags of [{}]".format(",".join(str(k) for k in self.changes.keys()))

            
class SingleTagChangeEvent(TagChangeEvent):
    def __init__(self,level,tag,elements):
        assert isinstance(tag,tags.Tag)
        self.level = level
        self.tag = tag
        self.elements = elements
        self.contentsChanged = False
        
    def ids(self):
        return [element.id for element in self.elements]
    
    
class TagValueAddedEvent(SingleTagChangeEvent):
    def __init__(self,level,tag,value,elements):
        super().__init__(level,tag,elements)
        self.value = value

    def applyTo(self,element):
        assert element.id in self.ids()
        if element.tags is not None:
            element.tags.add(self.tag,self.value)
            
    def __str__(self):
        return "Add: {} {} {}".format(self.tag,self.value,self.elements)
    
    
class TagValueRemovedEvent(SingleTagChangeEvent):
    def __init__(self,level,tag,value,elements):
        super().__init__(level,tag,elements)
        self.value = value

    def applyTo(self,element):
        assert element.id in self.ids()
        if element.tags is not None:
            element.tags.remove(self.tag,self.value)
        
    def __str__(self):
        return "Remove: {} {} {}".format(self.tag,self.value,self.elements)


class TagValueChangedEvent(SingleTagChangeEvent):
    def __init__(self,level,tag,oldValue,newValue,elements):
        super().__init__(level,tag,elements)
        self.oldValue = oldValue
        self.newValue = newValue

    def applyTo(self,element):
        assert element.id in self.ids()
        if element.tags is not None:
            element.tags.replace(self.tag,self.oldValue,self.newValue)
            
    def __str__(self):
        return "Change: {} {}->{} {}".format(self.tag,self.oldValue,self.newValue,self.elements)
    

class SortValueChangedEvent(ChangeEvent):
    def __init__(self, tag, valueId, oldValue, newValue):
        self.tag, self.valueId, self.oldValue, self.newValue = tag, valueId, oldValue, newValue

class TagTypeChangedEvent(ChangeEvent):
    """TagTypeChangedEvent are used when a tagtype (like artist, composer...) is added, changed or deleted.
    Contrary to ModifyEvents these events are sent over the tagTypeChanged-signal of the dispatcher.
    """
    def __init__(self,action,tagType):
        assert action in range(1,4) # ADDED,CHANGED or DELETED
        self.action = action
        self.tagType = tagType


class FlagTypeChangedEvent(ChangeEvent):
    """TagTypeChangedEvent are used when a flagtype is added, changed or deleted. Contrary to ModifyEvents
    these events are sent over the tagTypeChanged-signal of the dispatcher.
    """
    def __init__(self,action,flagType):
        assert action in range(1,4) # ADDED,CHANGED or DELETED
        self.action = action
        self.flagType = flagType
