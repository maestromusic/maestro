#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#

"""
This module will really modify database and filesystem (using database.write and realfiles). It does not
do any Undo-/Redo-stuff.
"""
 
from .. import database as db, tags, realfiles, logging
from ..database import write
from . import dispatcher, events, REAL

logger = logging.getLogger(__name__)


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
    """Commits all elements, given by an id->(oldElement,newElement) dictionary, into the database.
    
    After the commit, the elements in the database will look like those in the argument.
    If an element in changes.values() is a container, the contents must be loaded, but
    do not need to have any loaded data besides position and id."""
    logger.debug("Committing {} elements".format(len(changes)))
    
    # Tags
    changeTags({oldElement.id: (oldElement.tags,newElement.tags)
                    for oldElement,newElement in changes.values()},
               [oldElement for oldElement,newElement in changes.values()],
               emitEvent = False)
    
    # Flags
    changeFlags({oldElement.id: (oldElement.flags, newElement.flags)
                 for oldElement, newElement in changes.values()},
                emitEvent = False)
    
    # Major
    for tup in changes.values():
        setMajor(tup[1], emitEvent = False)
    
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
                    real = realfiles.get(element.path)
                    real.read()
                    real.tags.add(tag,value)
                    real.saveTags()
                except IOError as e:
                    logger.error("Could not add tags to '{}'.".format(element.path))
                    logger.error("Error was: {}".format(e))
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
                    real = realfiles.get(element.path)
                    real.read()
                    real.tags.remove(tag,value)
                    real.saveTags()
                except IOError as e:
                    logger.error("Could not remove tags from '{}'.".format(element.path))
                    logger.error("Error was: {}".format(e))
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
                    real = realfiles.get(element.path)
                    real.read()
                    real.tags.replace(tag,oldValue,newValue)
                    real.saveTags()
                except IOError as e:
                    logger.error("Could not change tag value from '{}'.".format(element.path))
                    logger.error("Error was: {}".format(e))
                    continue
            successful.append(element)
    else: successful = elements
        
    if len(successful) > 0:
        db.write.changeTagValue((element.id for element in successful),tag,oldValue,newValue)
        dispatcher.changes.emit(events.TagValueChangedEvent(REAL,tag,oldValue,newValue,successful))


def _getPathAndFileTags(id,elements):
    for element in elements:
        if element.id == id:
            if element.isFile():
                path = getattr(element,'path',None)
                if path is None:
                    path = db.path(id)
                fileTags = getattr(element,'fileTags',None)
                return path,fileTags
            else: return None,None
    # Arriving here means that no element has the given id
    if db.isFile(element.id):
        return db.path(element.id),None
    else: return None,None

def changeTags(changes,elements=[],emitEvent = True):
    """Change tags arbitrarily: *changes* is a dict mapping element ids to tuples consisting
    of two tags.Storages - the tags before and after the change. *elements* is a list of affected elements
    and is only used to determine whether an element is a file and to get its path. If an element is not
    found in this list, that information is read from the database.
    """
    abort = False
        
    successful = [] # list of element ids whose file was written successfully
    for id,changeTuple in changes.items():
        oldTags,newTags = changeTuple
        if oldTags == newTags:
            continue
        
        path,fileTags = _getPathAndFileTags(id,elements)
              
        if path is not None and (fileTags is None or fileTags != newTags.withoutPrivateTags()):
            try:
                real = realfiles.get(path)
                real.read()
                real.tags = newTags.withoutPrivateTags()
                real.saveTags()
            except IOError as e:
                logger.error("Could not change tags of file '{}'.".format(path))
                logger.error("Error was: {}".format(e))
                # Do not write the database, if writing the file failed
                continue
        successful.append(id)
        
        unchangedTags = [tag for tag in oldTags if tag in newTags and oldTags[tag] == newTags[tag]]
        if len(unchangedTags) < len(oldTags):
            db.write.removeAllTagValues(id,(tag for tag in oldTags if not tag in unchangedTags))
        if len(unchangedTags) < len(newTags):
            for tag in newTags:
                if tag not in unchangedTags:
                    db.write.addTagValues(id,tag,newTags[tag])
  
    if len(successful) > 0 and emitEvent:
        changes = {k: v[1] for k,v in changes.items() if k in successful}
        dispatcher.changes.emit(events.TagChangeEvent(REAL,changes))


def addFlag(flag,elements):
    """Add *flag* to *elements* and emit a FlagAddedEvent."""
    db.write.addFlag((el.id for el in elements),flag)
    dispatcher.changes.emit(events.FlagAddedEvent(REAL,flag,elements))
    

def removeFlag(flag,elements):
    """Remove *flag* from *elements* and emit a FlagRemovedEvent."""
    db.write.removeFlag((el.id for el in elements),flag)
    dispatcher.changes.emit(events.FlagRemovedEvent(REAL,flag,elements))
    

def changeFlags(changes,emitEvent = True):
    """Change flags arbitrarily: *changes* is a dict mapping element ids to tuples consisting
    of two lists of flags - the flags before and after the change."""
    for id,changeTuple in changes.items():
        oldFlags,newFlags = changeTuple
        # Compare the lists forgetting the order
        if any(f not in oldFlags for f in newFlags) or any(f not in newFlags for f in oldFlags):
            db.write.setFlags(id,newFlags)
    if emitEvent:
        changes = {k: v[1] for k,v in changes.items()}
        dispatcher.changes.emit(events.FlagChangeEvent(REAL,changes))


def setMajor(element, emitEvent = True):
    """Set the 'major' flag of the element according to the element's attribute."""
    db.write.setMajor(element.id, element.major)
    if emitEvent:
        dispatcher.changes.emit(events.MajorFlagChangeEvent(REAL, element))
    
def setSortValue(tag,valueId,newValue,oldValue=-1):
    """Change a sortvalue and emit a SortValueChangedEvent. *tag* and *valueId* specify the affected value,
    *newValue* is the new value (None if the sortvalue should be deleted) and *oldValue* is used for the
    event. It may be the oldValue (including None) or -1 (the default) in which case it is fetched from the
    database.
    """
    if oldValue == -1:
        oldValue = db.sortValue(tag,valueId)
    db.write.setSortValue(tag,valueId,newValue)
    dispatcher.changes.emit(events.SortValueChangedEvent(tag,valueId,oldValue,newValue))
