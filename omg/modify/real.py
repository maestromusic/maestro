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
 
from .. import database as db, tags as tagsModule, realfiles, logging, utils
from ..database import write
from . import dispatcher, events
from ..constants import REAL
import os

logger = logging.getLogger(__name__)


def createNewElements(elements, setData = False):
    """Create new elements. *elements* is a list of preliminary elements. If they have negative IDs, new IDs for
    them are created automatically. Otherwise, they are inserted with the IDs as given in the element.
    This method will insert new entries in the elements and file table. It won't save
    any contents. Tags and flags are saved only if *setData* is True.
    
    This method will return a dict mapping old to new ids.
    """
    result = {}
    if setData:
        tagChanges = {}
        flagChanges = {}
        emptyTags = tagsModule.Storage()
        emptyFlags = [] 
    for element in elements:
        newId = db.write.createNewElement(element.isFile(),
                                          element.major if element.isContainer() else False,
                                          id = None if element.id < 0 else element.id)
        if element.isFile():
            db.write.addFile(newId,element.path,None,element.length)
        if setData:
            tagChanges[newId] = (emptyTags, element.tags)
            flagChanges[newId] = (emptyFlags, element.flags)
        
        result[element.id] = newId
    if setData:
        changeTags(tagChanges, elements, emitEvent = False)
        changeFlags(flagChanges,  emitEvent = False)
    return result

def newContainer(tags, flags, major, id = None):
    """Creates a new container in the database with the given attributes. Returns its id.
    This function does not emit any events."""
    id = db.write.createNewElement(False, major, id)
    oldTags = tagsModule.Storage()
    oldFlags = []
    changeTags({id:(oldTags,tags)}, emitEvent = False)
    changeFlags({id:(oldFlags,flags)}, emitEvent = False)
    return id    

def deleteElements(elids):
    """Delete the elements with the given ids from the database. This will delete from the elements table
    and due to foreign keys also from files, tags, flags and contents and emit an ElementsDeletedEvent."""
    db.write.deleteElements(elids)
    dispatcher.changes.emit(events.ElementsDeletedEvent(elids))

def deleteFilesFromDisk(paths):
    """Delete the given files from the filesystem. *paths* is a list of paths."""
    for path in paths:
        logger.warning('permanently removing file "{}"'.format(path))
        os.remove(utils.absPath(path))
def addContents(changes, emitEvent = True):
    """Add the given content relations to the database and emit a corresponding event.
    
    *changes* is a dict mapping parent IDs to a list of (position, element) tuples."""
    db.write.addContents( [ (parentID,pair[0],pair[1].id) for parentID,pairs in changes.items() for pair in pairs ] )
    dispatcher.changes.emit(events.InsertContentsEvent(REAL, changes))
    
def removeContents(changes):
    """Remove the given content relations from the database and emit a corresponding event.
    
    *changes* should be a dict mapping parent IDs to lists of positions to remove."""
    db.write.removeContents([ (parentID,p) for parentID,positions in changes.items() for p in positions ])
    dispatcher.changes.emit(events.RemoveContentsEvent(REAL, changes))

def changePositions(parentID, changes):
    """Change positions of children of *parentID* according to *changes*, which is a list of tuples
    (oldPosition, newPosition)."""
    db.write.changePositions(parentID, changes)
    dispatcher.changes.emit(events.PositionChangeEvent(REAL, parentID, dict(changes)))
    
def commit(changes, emitEvent = True):
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
    
    if emitEvent:
        dispatcher.changes.emit(events.ElementChangeEvent(REAL,{id: tuple[1] for id,tuple in changes.items()}, True))


def addTagValue(tag,value,elements): 
    """Add a tag of type *tag* and value *value* to each element in *elements*, which is a list of either
    elements or element IDs."""
    assert isinstance(tag,tagsModule.Tag) and len(elements) > 0
    
    if not tag.private:
        successful = [] # list of element IDs where the file was written successfully
        for element in elements:
            isID = isinstance(element, int)
            if (isID and db.isFile(element)) or element.isFile():
                try:
                    real = realfiles.get(db.path(element) if isID else element.path)
                    real.read()
                    real.tags.add(tag,value)
                    real.saveTags()
                except IOError as e:
                    logger.error("Could not add tags to '{}'.".format(element.path))
                    logger.error("Error was: {}".format(e))
                    continue
            successful.append(element if isID else element.id)
    else: successful = [el if isinstance(el, int) else el.id for el in elements]

    if len(successful) > 0:
        db.write.addTagValues(successful, tag,[value])
        dispatcher.changes.emit(events.TagValueAddedEvent(REAL,tag,value, successful))


def removeTagValue(tag,value,elements):
    """Remove the given value of tag *tag* from each element in *elements*."""
    assert isinstance(tag,tagsModule.Tag) and len(elements) > 0
    
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
    """For each element in *elements*, which is a list of either elements or element IDs:
    If element has a tag of type *tag* and value *oldValue* then remove it.
    In any case add *newValue*."""
    assert isinstance(tag,tagsModule.Tag) and len(elements) > 0
    if not tag.private:
        successful = [] # list of element IDs where the file was written successfully
        for element in elements:
            isID = isinstance(element, int)
            if (isID and db.isFile(element)) or element.isFile():
                try:
                    real = realfiles.get(db.path(element) if isID else element.path)
                    real.read()
                    real.tags.replace(tag,oldValue,newValue)
                    real.saveTags()
                except IOError as e:
                    logger.error("Could not change tag value from '{}'.".format(element.path))
                    logger.error("Error was: {}".format(e))
                    continue
            successful.append(element if isID else element.id)
    else: successful = [el if isinstance(el, int) else el.id for el in elements]
        
    if len(successful) > 0:
        db.write.changeTagValue(successful,tag,oldValue,newValue)
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
    if db.isFile(id):
        return db.path(id),None
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

def setHidden(tag, valueId, newState):
    """Set the "hidden" attribute of the given tag value to *newState* which must be a bool."""
    db.write.setHidden(tag, valueId, newState)
    dispatcher.changes.emit(events.HiddenAttributeChangedEvent(tag, valueId, newState))