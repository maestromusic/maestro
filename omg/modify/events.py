#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from .. import tags
from . import ModifyEvent


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
