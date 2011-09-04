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
from . import dispatcher, events, REAL

logger = logging.getLogger("omg.modify")


def createNewElements(elements):
    """Create new elements. *elements* is a list of preliminary elements (i.e. element instances with
    negative ids). This method will insert new entries in the elements and file table. It won't save
    any contents, tags or flags though.
    
    This method will return a dict mapping old to new ids.
    """
    result = {}
    for element in elements:
        assert element.id < 0
        oldId = element.id
        newId = db.write.createNewElement(element.isFile(),element.major if element.isContainer() else False)
        if element.isFile():
            db.write.addFile(newId,element.path,None,element.length)
        
        result[element.id] = newId
    return result


def deleteElements(elids):
    """Delete the elements with the given ids from the database. This will delete from the elements table
    and due to foreign keys also from files, tags, flags and contents and emit an ElementsDeletedEvent."""
    db.write.deleteElements(elids)
    dispatcher.changes.emit(events.ElementsDeletedEvent(elids))


def commit(changes):
    """Commits all elements, given by an id->element dictionary, into the database.
    
    After the commit, the elements in the database will look like those in the argument.
    If an element in changes.values() is a container, the contents must be loaded, but
    do not need to have any loaded data besides position and id."""
    logger.debug("Committing {} elements".format(len(changes)))
    
    # Tags
    changeTags({oldElement: (oldElement.tags,newElement.tags)
                    for oldElement,newElement in changes.values()},emitEvent=False)
                    
    # Contents (including position)
    contents = {}
    for id,changesTuple in changes.items():
        oldElement,newElement = changesTuple
        cOld = oldElement.getContents()
        cNew = newElement.getContents()
        if len(cOld) != len(cNew) or \
                any(old.id != new.id or old.position != new.position for old,new in zip(cOld,cNew)):
            contents[oldElement.id] = cNew
            
    if len(contents) > 0:
        db.write.setContents(contents)
    
    dispatcher.changes.emit(events.ElementChangeEvent(REAL,{id: tuple[1] for id,tuple in changes.items()}, True))


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
        dispatcher.changes.emit(events.TagValueAddedEvent(REAL,tag,value,successful))


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
        dispatcher.changes.emit(events.TagValueRemovedEvent(REAL,tag,value,successful))


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
        dispatcher.changes.emit(events.TagValueChangedEvent(REAL,tag,oldValue,newValue,successful))


def changeTags(changes, emitEvent = True):
    """Change tags arbitrarily: *changes* is a dict mapping elements (not element-ids!) to tuples consisting
    of two tags.Storages - the tags before and after the change."""
    abort = False
        
    successful = [] # list of elements where the file was written successfully
    for element,changeTuple in changes.items():
        oldTags,newTags = changeTuple
        if oldTags == newTags:
            continue
        
        if element.isFile() and element.fileTags != newTags.withoutPrivateTags():
            try:
                real = realfiles2.get(element.path)
                real.read()
                real.tags = newTags.withoutPrivateTags()
                real.saveTags()
            except:
                logger.error("Could not change tags of file '{}'.".format(element.path))
                continue
        successful.append(element)
        
        unchangedTags = [tag for tag in oldTags if tag in newTags and oldTags[tag] == newTags[tag]]
        if len(unchangedTags) < len(oldTags):
            db.write.removeAllTagValues(element.id,(tag for tag in oldTags if not tag in unchangedTags))
        if len(unchangedTags) < len(newTags):
            for tag in newTags:
                if tag not in unchangedTags:
                    db.write.addTagValues(element.id,tag,newTags[tag])
  
    if len(successful) > 0 and emitEvent:
        if len(successful) < len(changes):
            changes = {element: changes for element,changes in changes.items() if element in successful}
        dispatcher.changes.emit(events.TagChangeEvent(REAL,changes))


def addFlag(flag,elements):
    """Add *flag* to *elements* and emit a FlagAddedEvent."""
    db.write.addFlag((el.id for el in elements),flag)
    dispatcher.changes.emit(events.FlagAddedEvent(REAL,flag,elements))
    

def removeFlag(flag,elements):
    """Remove *flag* from *elements* and emit a FlagRemovedEvent."""
    db.write.removeFlag((el.id for el in elements),flag)
    dispatcher.changes.emit(events.FlagRemovedEvent(REAL,flag,elements))
    

def changeFlags(changes):
    """Change flags arbitrarily: *changes* is a dict mapping elements (not element-ids!) to tuples consisting
    of two lists of flags - the flags before and after the change."""
    for element,changeTuple in changes.items():
        oldFlags,newFlags = changeTuple
        # Compare the lists forgetting the order
        if any(f not in oldFlags for f in newFlags) or any(f not in newFlags for f in oldFlags):
            db.write.setFlags(element.id,newFlags)
    dispatcher.changes.emit(events.FlagChangeEvent(changes))
    
