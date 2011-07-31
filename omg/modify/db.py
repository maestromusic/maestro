#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#

from .. import database as db, tags, realfiles2
from . import dispatcher, events

# Use these methods only from an UndoCommand that knows how to undo them.
def addTagValue(tag,value,elements): 
    assert isinstance(tag,tags.Tag) and len(elements) > 0
    dispatcher.realChanges.emit(events.TagValueAddedEvent(tag,value,elements))
    return #TODO Reenable the parte below when cutags is fixed.

    valueId = db.idFromValue(tag,value,insert=True)
    db.multiQuery("INSERT INTO {}tags (element_id,tag_id,value_id) VALUES (?,{},{})"
                        .format(db.prefix,tag.id,valueId),
                  [(element.id,) for element in elements])
    for element in elements:
        if element.isFile():
            if element.path is None:
                path = db.path(element.id)
            else: path = element.path
            real = realfiles2.get(path)
            real.read()
            real.tags.add(tag,value)
            real.saveTags()
        
    dispatcher.realChanges.emit(events.TagValueAddedEvent(tag,value,elements))
    
def removeTagValue(tag,value,elements):
    assert isinstance(tag,tags.Tag) and len(elements) > 0
    dispatcher.realChanges.emit(events.TagValueRemovedEvent(tag,value,elements))
    return #TODO Reenable the parte below when cutags is fixed.
    valueId = db.idFromValue(tag,value)
    db.query("DELETE FROM {}tags WHERE tag_id = {} AND value_id = {} AND element_id IN ({})"
                    .format(db.prefix,tag.id,valueId,','.join(str(element.id) for element in elements)))
    for element in elements:
        if element.isFile():
            if element.path is None:
                path = db.path(element.id)
            else: path = element.path
            real = realfiles2.get(path)
            real.read()
            real.tags.remove(tag,value)
            real.saveTags()
            
    dispatcher.realChanges.emit(events.TagValueRemovedEvent(tag,value,elements))
    
def changeTagValue(tag,oldValue,newValue,elements):
    assert isinstance(tag,tags.Tag) and len(elements) > 0
    dispatcher.realChanges.emit(events.TagValueChangedEvent(tag,oldValue,newValue,elements))
    return #TODO Reenable the parte below when cutags is fixed.
    oldValueId = db.idFromValue(tag,value)
    newValueId = db.idFromValue(tag,value,insert=True)
    db.query("UPDATE {}tags SET value_id = {} WHERE tag_id = {} AND value_id = {} AND element_id IN ({})"
               .format(db.prefix,newValueId,tag.id,oldValueId,','.join(str(el.id) for el in elements)))
    for element in elements:
        if element.isFile():
            if element.path is None:
                path = db.path(element.id)
            else: path = element.path
            real = realfiles2.get(path)
            real.read()
            real.tags.replace(tag,oldValue,newValue)
            real.saveTags()
    dispatcher.realChanges.emit(events.TagValueChangedEvent(tag,oldValue,newValue,elements))
    