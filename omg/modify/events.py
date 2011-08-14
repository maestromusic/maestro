#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer, Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#

from .. import tags


class ModifyEvent:
    """A generic modify event for all sorts of modifications."""
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


class ModifySingleElementEvent(ModifyEvent):
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


class InsertElementsEvent(ModifyEvent):
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
            

class RemoveElementsEvent(ModifyEvent):
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
            

class TagModifyEvent(ModifyEvent):
    def __init__(self,changes):
        self.changes = changes
        self.contentsChanged = False
        
    def applyTo(self,element):
        assert element in self.changes
        if element.tags is not None:
            element.tags = self.changes[element].copy()
            
    def __str__(self):
        return "Modify tags of [{}]".format(",".join(str(k) for k in self.changes.keys()))

            
class SingleTagModifyEvent(TagModifyEvent):
    def __init__(self,tag,elements):
        assert isinstance(tag,tags.Tag)
        self.tag = tag
        self.elements = elements
        self.contentsChanged = False
        
    def ids(self):
        return [element.id for element in self.elements]
    
    
class TagValueAddedEvent(SingleTagModifyEvent):
    def __init__(self,tag,value,elements):
        SingleTagModifyEvent.__init__(self,tag,elements)
        self.value = value

    def applyTo(self,element):
        assert element.id in self.ids()
        if element.tags is not None:
            element.tags.add(self.tag,self.value)
            
    def __str__(self):
        return "Add: {} {} {}".format(self.tag,self.value,self.elements)
    
    
class TagValueRemovedEvent(SingleTagModifyEvent):
    def __init__(self,tag,value,elements):
        SingleTagModifyEvent.__init__(self,tag,elements)
        self.value = value

    def applyTo(self,element):
        assert element.id in self.ids()
        if element.tags is not None:
            element.tags.remove(self.tag,self.value)
        
    def __str__(self):
        return "Remove: {} {} {}".format(self.tag,self.value,self.elements)


class TagValueChangedEvent(SingleTagModifyEvent):
    def __init__(self,tag,oldValue,newValue,elements):
        SingleTagModifyEvent.__init__(self,tag,elements)
        self.oldValue = oldValue
        self.newValue = newValue

    def applyTo(self,element):
        assert element.id in self.ids()
        if element.tags is not None:
            element.tags.replace(self.tag,self.oldValue,self.newValue)
            
    def __str__(self):
        return "Change: {} {}->{} {}".format(self.tag,self.oldValue,self.newValue,self.elements)


class TagTypeChangedEvent:
    """TagTypeChangedEvent are used when a tagtype (like artist, composer...) is added, changed or deleted.
    Contrary to ModifyEvents these events are sent over the tagTypeChanged-signal of the dispatcher.
    """
    ADDED,CHANGED,DELETED = range(1,4)
    
    def __init__(self,action,tagtype):
        assert action in range(1,4)
        self.action = action
        self.tagtype = tagtype