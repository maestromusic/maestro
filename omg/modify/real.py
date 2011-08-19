#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#

"""
This module will really modify database and filesystem (using database.write and realfiles2). It does not
do any Undo-/Redo-stuff.
"""
 
from .. import database as db, tags, realfiles2, logging
from ..database import write
from . import dispatcher, events

logger = logging.getLogger("omg.modify")


def createNewElements(elements):
    result = {}
    changedElements = {}
    for element in elements:
        assert element.id < 0
        oldId = element.id
        newId = db.write.createNewElement(element.isFile(),element.major).insertId()
        result[element.id] = newId
        copy = element.copy()
        copy.id = newId
        changedElements[oldId] = copy
    dispatcher.emit(events.NewElementChangeEvent(changedElements))
    return result


def deleteElements(elids):
    db.write.deleteElements(elids)
    dispatcher.emit(events.ElementsDeletedEvent(elids))


def commit(changes):
    """Commits all elements, given by an id->element dictionary, into the database.
    
    After the commit, the elements in the database will look like those in the argument.
    If an element in changes.values() is a container, the contents must be loaded, but
    do not need to have any loaded data besides position and id."""
    raise ResourceWarning('maddiiiiiin')

def addTagValue(tag,value,elements): 
    """Add a tag of type *tag* and value *value* to each element in *elements*."""
    assert isinstance(tag,tags.Tag) and len(elements) > 0
    
    if not tag.private:
        successful = [] # list of elements where the file was written successfully
        for element in elements:
            if element.isFile():
                try:
                    real = realfiles2.get(element.path)
                    real.read()
                    real.tags.add(tag,value)
                    real.saveTags()
                except:
                    logger.error("Could not add tags to '{}'.".format(element.path))
                    continue
            successful.append(element)
    else: successful = elements

    if len(successful) > 0:
        db.write.addTagValues((element.id for element in successful),tag,[value])
        dispatcher.realChanges.emit(events.TagValueAddedEvent(tag,value,successful))


def removeTagValue(tag,value,elements):
    """Remove the given value of tag *tag* from each element in *elements*."""
    assert isinstance(tag,tags.Tag) and len(elements) > 0
    
    if not tag.private:
        successful = [] # list of elements where the file was written successfully
        for element in elements:
            if element.isFile():
                try:
                    real = realfiles2.get(element.path)
                    real.read()
                    real.tags.remove(tag,value)
                    real.saveTags()
                except:
                    logger.error("Could not remove tags from '{}'.".format(element.path))
                    continue
            successful.append(element)
    else: successful = elements
    
    if len(successful) > 0:                
        db.write.removeTagValues((element.id for element in successful),tag,[value])
        dispatcher.realChanges.emit(events.TagValueRemovedEvent(tag,value,successful))


def changeTagValue(tag,oldValue,newValue,elements):
    """For each element in *elements*: If element has a tag of type *tag* and value *oldValue* then remove
    it. In any case add *newValue*."""
    assert isinstance(tag,tags.Tag) and len(elements) > 0

    if not tag.private:
        successful = [] # list of elements where the file was written successfully
        for element in elements:
            if element.isFile():
                try:
                    real = realfiles2.get(element.path)
                    real.read()
                    real.tags.replace(tag,oldValue,newValue)
                    real.saveTags()
                except e:
                    logger.error("Could not change tag value from '{}'.".format(element.path))
                    continue
            successful.append(element)
    else: successful = elements
        
    if len(successful) > 0:
        db.write.changeTagValue((element.id for element in successful),tag,oldValue,newValue)
        dispatcher.realChanges.emit(events.TagValueChangedEvent(tag,oldValue,newValue,successful))


def changeTags(changes):
    """Change tags arbitrarily: *changes* is a dict mapping elements (not element-ids!) to tuples consisting
    of two tags.Storages - the tags before and after the change."""
    successful = [] # list of elements where the file was written successfully
    for element,changeTuple in changes.items():
        oldTags,newTags = changeTuple
        if oldTags == newTags:
            continue
        
        if element.isFile():
            try:
                real = realfiles2.get(element.path)
                real.read()
                real.tags = newTags.withoutPrivateTags()
                real.saveTags()
            except:
                logger.error("Could not change tags of file '{}'.".format(element.path))
                continue
        successful.append(element)
        
        # First remove old values
        for tag in oldTags:
            if tag not in newTags:
                db.write.removeAllTagValues(element.id,tag)
            else:
                valuesToRemove = [value for value in oldTags[tag] if value not in newTags[tag]]
                if len(valuesToRemove) > 0:
                    db.write.removeTagValues(element.id,tag,valuesToRemove)                 
        
        # Then add new value
        for tag in newTags:
            if tag not in oldTags:
                valuesToAdd = newTags[tag]
            else:
                valuesToAdd = [value for value in newTags[tag] if value not in oldTags[tag]]
            if len(valuesToAdd) > 0:
                db.write.addTagValues(element.id,tag,valuesToAdd)
            
    if len(successful) > 0:
        if len(successful) < len(changes):
            changes = {element: changes for element,changes in changes.items() if element in successful}
        dispatcher.realChanges.emit(events.TagModifyEvent(changes))
        
