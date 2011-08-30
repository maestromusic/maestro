# -*- coding: utf-8 -*-
# Copyright 2011 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from ..gui import mainwindow
from .. import logging
from .. import modify, realfiles2
from ..models import Container, Element
logger = logging.getLogger(__name__)
def commitEditors():
    """commits all open editors"""
    logger.debug("Start commit")
    models = [dock.editor.model() for dock in mainwindow.mainWindow.getWidgets('editor')]
    if len(models) == 0:
        # nothing to commit – no open editors!
        return
    try:
        modify.beginMacro(modify.REAL, 'commit')
    except modify.StackChangeRejectedException:
        logger.info('stack change rejected - not commiting')
        return
    logger.debug("Copying nodes...")
    myRoot = models[0].root.copy()
    for model in models[1:]:
        myRoot.insertContents(0, [e.copy() for e in model.root.contents])
    # now we have a single root node containing the contents of all editors
   
    logger.debug("Filtering elements...")
    newElements = dict()
    dbElements = dict()
    for element in myRoot.getAllNodes(skipSelf = True):
        if element.isInDB():
            if not element.id in dbElements:
                dbElements[element.id] = element
        else:
            if not element.id in newElements:
                newElements[element.id] = element
               
    logger.debug("newElementsCommand...")
    newElementsCommand = modify.CreateNewElementsCommand(newElements.values())
    modify.push(newElementsCommand)
    # new elements committed -> now all elements are in the DB. Add new ones to dbElements
    idMap = newElementsCommand.idMap
    for oldId, element in newElements.items():
        element.id = idMap[oldId]
        dbElements[element.id] = element
    for element in dbElements.values():
        if element.isContainer():
            element.printStructure()
   
    # now we need to load the original states of the elements from the database, in order to be able
    # to undo the commit.
    logger.debug("Loading original state")
    originalElements = dict()
    for element in dbElements.values():
        origEl = Element.fromId(element.id, loadData = True)
        if origEl.isContainer():
            origEl.loadContents(recursive = False, loadData = False)
        originalElements[element.id] = origEl
    logger.debug("big undo command")
    changes = {id:(originalElements[id], dbElements[id]) for id in dbElements}
    #import pprint
    #pprint.pprint({id: (v[0].tags,v[1].tags) for id,v in changes.items()})
    bigUndoCommand = modify.UndoCommand(modify.REAL, changes, True, 'main commit command')
    modify.push(bigUndoCommand)
    modify.endMacro()
    logger.debug("end commit")