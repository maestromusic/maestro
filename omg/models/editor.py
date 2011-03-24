# -*- coding: utf-8 -*-
# Copyright 2011 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#


from omg import database, tags, constants
from omg.models.playlist import BasicPlaylist, RemoveContentsCommand, InsertContentsCommand
from omg.models import Container, PositionChangeCommand, TagChangeCommand
from omg.config import options
from omg import relPath, absPath
import omg.gopulate

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt
import itertools
import logging
logger = logging.getLogger("models.editor")
db = database.get()

class EditorModel(BasicPlaylist):
    
    def __init__(self):
        BasicPlaylist.__init__(self)
        
    def _prepareMimeData(self, mimeData):
        """Overwrites the function of BasicPlaylist to add album-recognition intelligence."""
        if mimeData.hasFormat(options.gui.mime): # already elements -> no preprocessing needed
            return [node.copy() for node in mimeData.retrieveData(options.gui.mime)]
        elif mimeData.hasFormat('text/uri-list'):
            filePaths = [relPath(path) for path in self._collectFiles(absPath(p.path()) for p in mimeData.urls())]
            guess = omg.gopulate.GopulateGuesser(filePaths)
            return guess.guessTree(True)
        else:
            return None
        
    def merge(self, indices, name):
        self.undoStack.beginMacro("Merge {} items, title »{}«".format(len(indices),name))
        amount = len(indices)
        if amount > 0:
            indices.sort(key = lambda ind: ind.row())
            
            rows = [ ind.row() for ind in indices ]
            elements = [ ind.internalPointer() for ind in indices ]
            parentIdx = indices[0].parent()
            parent = elements[0].parent
            if not parent:
                parent = self.root()
            lastrow = self.rowCount(parentIdx)
            for row in reversed(rows): # remove element from current child list
                if row != rows[0]:
                    for r in range(row+1,lastrow): # adjust position of elements behind
                        child = parentIdx.child(r,0).internalPointer()
                        self.undoStack.push(PositionChangeCommand(child, child.position - 1))
                self.undoStack.push(
                      RemoveContentsCommand(self, parentIdx, row, 1))
                lastrow -= 1
            
            newContainer = Container(id = None)
            newContainer.parent = parent
            newContainer.position = elements[0].position
            newContainer.loadTags()
            newContainer.setContents(elements)
            for element,j in zip(elements, itertools.count(1)):
                self.undoStack.push(PositionChangeCommand(element, j))
                for tag, i in zip(element.tags[tags.TITLE], itertools.count()):
                    if tag.find(name) != -1:
                        newtag = tag.replace(name, "").\
                            strip(constants.FILL_CHARACTERS).\
                            lstrip("0123456789").\
                            strip(constants.FILL_CHARACTERS)
                        if newtag == "":
                            newtag = "Part {}".format(i+1)
                        self.undoStack.push(TagChangeCommand(element, tags.TITLE, i, newtag))
            newContainer.updateSameTags()  
            newContainer.tags[tags.TITLE] = [ name ]
            self.undoStack.push(InsertContentsCommand(self, parent, row, [newContainer], copy = False))
            
            self.dataChanged.emit(
                self.index(row, 0, parentIdx), self.index(self.rowCount(parentIdx)-1, 0, parentIdx))
            self.dataChanged.emit(parentIdx, parentIdx)
        self.undoStack.endMacro()
        
    def commit(self):
        """Commits all the containers and files in the current model into the database."""
        #Todo: make undoable
        logger.debug("commit called")
        for item in self.root.contents:
            item.commit(toplevel = True)
        self.layoutChanged.emit()