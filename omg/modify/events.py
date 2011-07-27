#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from . import ModifyEvent

class TagModifyEvent(ModifyEvent):
    def __init__(self,tag,elements):
        self.tag = tag
        self.elements = elements
        self.contentsChanged = False
        
    def ids(self):
        return [element.id for element in self.elements]
    
    
class TagValueAddedEvent(TagModifyEvent):
    def __init__(self,tag,value,elements):
        TagModifyEvent.__init__(self,tag,elements)
        self.value = value

    def applyTo(self,element):
        assert element.id in self.ids()
        if element.tags is not None:
            element.tags.add(self.tag,self.value)
    
    
class TagValueRemovedEvent(TagModifyEvent):
    def __init__(self,tag,value,elements):
        TagModifyEvent.__init__(self,tag,elements)
        self.value = value

    def applyTo(self,element):
        assert element.id in self.ids()
        if element.tags is not None:
            element.tags.remove(self.tag,self.value)
        
        
class TagValueChangedEvent(TagModifyEvent):
    def __init__(self,tag,oldValue,newValue,elements):
        TagModifyEvent.__init__(self,tag,elements)
        self.oldValue = oldValue
        self.newValue = newValue

    def applyTo(self,element):
        assert element.id in self.ids()
        if element.tags is not None:
            element.tags.replace(self.tag,self.oldValue,self.newValue)

