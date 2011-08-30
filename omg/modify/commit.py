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
from ..models import Container, Element, RootNode
logger = logging.getLogger(__name__)

def compress(node, uniqueElements):
    if isinstance(node.parent, RootNode):
        if node.id in tuple(zip(*uniqueElements.keys()))[0]:
            return
        parentId = None
    else:
        parentId = node.parent.id
    if (node.id,parentId) in uniqueElements:
        return uniqueElements[(node.id,parentId)]
    uniqueElements[(node.id,parentId)] = current = node.copy()
    if parentId is not None and (node.id,None) in uniqueElements:
        del uniqueElements[(node.id,None)] # remove duplicate root children 
    for child in node.contents:
        childCopy = compress(child, uniqueElements)
        current.contents.append(childCopy)
    return current

def commitEditors():
    """commits all open editors"""
    models = [dock.editor.model() for dock in mainwindow.mainWindow.getWidgets('editor')]
    if len(models) == 0:
        # nothing to commit – no open editors!
        return
    logger.info('Starting commit; {0} active editors'.format(len(models)))
    
    uniqueElements = dict()
    for model in models:
        for parent in model.root.contents:
            compress(parent, uniqueElements)
    print(uniqueElements)
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
    logger.info('have collected elements; ready to create new elements...')
    newElementsCommand = modify.CreateNewElementsCommand(newElements.values())
    modify.push(modify.REAL, newElementsCommand)
    logger.info('...new elements created')
    # new elements commited -> now all elements are in the DB. Add new ones to dbElements
    idMap = newElementsCommand.idMap
    for oldId, element in newElements.items():
        element.id = idMap[oldId]
        dbElements[element.id] = element
    
    # now we needte load the original states of the elements from the database, in order to be able
    # to undo the commit.
    originalElements = dict()
    logger.info('loading original container data...')
    for element in dbElements.values():
        origEl = Element.fromId(element.id, loadData = True)
        if origEl.isContainer():
            origEl.loadContents(recursive = False, loadData = False)
        originalElements[element.id] = origEl
    logger.info('...done')
    changes = {id:(originalElements[id], dbElements[id]) for id in dbElements}
    logger.info('creating and pushing the real big fat commit undo command...')
    bigUndoCommand = modify.UndoCommand(modify.REAL, changes, True, 'main commit command')
    modify.push(modify.REAL, bigUndoCommand)
    logger.info('...done!')
    modify.endMacro(modify.REAL)
        