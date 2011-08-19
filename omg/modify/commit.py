# -*- coding: utf-8 -*-
# Copyright 2011 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from ..gui import mainwindow
from .. import logging
from .. import modify
from ..models import Container, Element
logger = logging.getLogger(__name__)

def commitEditors():
    """commits all open editors"""
    models = [dock.editor.model() for dock in mainwindow.mainWindow.getWidgets('editor')]
    if len(models) == 0:
        # nothing to commit – no open editors!
        return
    modify.beginMacro(modify.REAL, 'commit')
    myRoot = models[0].root.copy()
    for model in models[1:]:
        myRoot.insertContents(0, [e.copy() for e in model.root.contents])
    print(myRoot)
    newElements = dict()
    dbElements = dict()
    # now we have a single root node containing the contents of all editors
    for element in myRoot.getAllNodes(skipSelf = True):
        if element.isInDB():
            if not element.id in dbElements:
                dbElements[element.id] = element
        else:
            if not element.id in newElements:
                newElements[element.id] = element
    newElementsCommand = modify.CreateNewElementsCommand(newElements)
    modify.push(modify.REAL, newElementsCommand)
    # new elements commited -> now all elements are in the DB. Add new ones to dbElements
    idMap = newElementsCommand.idMap
    for oldId, element in newElements.items():
        element.id = idMap[oldId]
        dbElements[element.id] = element
    
    # now we needte load the original states of the elements from the database, in order to be able
    # to undo the commit.
    originalElements = dict()
    for element in dbElements:
        origEl = Element.fromId(element.id, loadData = True)
        if origEl.isContainer():
            origEl.loadContents(recursive = False, loadData = False)
        originalElements[element.id] = origEl
    changes = {id:(originalElements[id], dbElements[id]) for id in dbElements}
    bigUndoCommand = modify.UndoCommand(modify.REAL, changes, True, 'main commit command')
    modify.push(modify.REAL, bigUndoCommand)
    modify.endMacro(modify.REAL)
        