# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore
from PyQt4.QtCore import Qt

from omg.models import rootedtreemodel, RootNode
import omg.models
from omg import database, tags, constants
from omg.models.playlist import BasicPlaylist, ManagedPlaylist

from . import GopulateGuesser, findNewAlbums
import omg.gopulate
absPath = omg.absPath

import logging
logger = logging.getLogger("gopulate.models")
db = database.get()

class GopulateTreeModel(BasicPlaylist):
    
    searchDirectoryChanged = QtCore.pyqtSignal(str)
    treeCreated = QtCore.pyqtSignal()
    #currentDirectoryChanged = QtCore.pyqtSignal(['QString'])
    
    def __init__(self, searchdir):
        rootedtreemodel.RootedTreeModel.__init__(self)
        self.current = None
        self.guesser = GopulateGuesser()
        self.setRoot(RootNode())
        self.setSearchDirectory(searchdir)
    
    def setCurrentDirectories(self, dirs, recursive = False):
        logger.debug('current directories set: {}'.format(dirs))
        self.current = dirs
        self.guesser.findFiles(dirs, recursive)
        self._createTree(self.guesser.guessTree(False))
        
    def setSearchDirectory(self, dir):
        logger.debug('search directory set: {}'.format(dir))
        self.searchdir = dir
        self.finder = None
        self.searchDirectoryChanged.emit(dir)
        #self.nextDirectory()
        
    def nextDirectory(self):
        logger.debug('next directory, searchdir: {}'.format(self.searchdir))
        if self.finder == None:
            self.finder = findNewAlbums(self.searchdir)
        self._createTree(next(self.finder))
        
    def _createTree(self, albums):
        root = RootNode()
        for el in albums:
            root.contents.append(el)
            el.parent = root
        self.setRoot(root)
        self.treeCreated.emit()
    
    def data(self, index, role = Qt.EditRole):
        if index.isValid() and role == Qt.StatusTipRole:
            elem = index.internalPointer()
            if elem.outOfSync():
                return ",".join(key for key, value in elem._syncState.items() if value) + " are out of sync"
                    
            elif elem.isInDB():
                return "I'm a synced DB element"
            else:
                return "I'm a happy new element, waiting for commit."
        else:
            return BasicPlaylist.data(self, index, role)
          
    def merge(self, indices, name):
        amount = len(indices)
        indices.sort(key = lambda ind: ind.internalPointer().position)
        if amount > 0:
            posIndex = indices[0]
            posItem = posIndex.internalPointer()
            parentIndex = posIndex.parent()
            parent = parentIndex.internalPointer()
            if not parent:
                parent = self.root
            insertPosition = parent.contents.index(posItem)
            self.beginRemoveRows(parentIndex, insertPosition, self.rowCount(parentIndex)-1)    
            
            newContainer = omg.models.Container(id = None)
            newContainer.parent = parent
            newContainer.position = posIndex.internalPointer().getPosition()
            newContainer.loadTags()
      
            j = 1
            for index in indices:
                item = index.internalPointer()
                item.parent = newContainer
                item.setPosition(j)
                newContainer.contents.append(item)
                parent.contents.remove(item)
                for i in range(len(item.tags[tags.TITLE])):
                    item.tags[tags.TITLE][i] = item.tags[tags.TITLE][i].replace(name, "").\
                        strip(constants.FILL_CHARACTERS).\
                        lstrip("0123456789").\
                        strip(constants.FILL_CHARACTERS)
                    if item.tags[tags.TITLE][i] == "":
                        item.tags[tags.TITLE][i] = "Part {}".format(i+1)
                j = j + 1
            parent._syncState["contents"] = True
            self.endRemoveRows()
            self.beginInsertRows(parentIndex, insertPosition, insertPosition)
            parent.contents.insert(insertPosition, newContainer)
            self.endInsertRows()
            
            for oldItem in parent.contents[insertPosition + 1:]:
                if oldItem.getPosition():
                    oldItem.setPosition(oldItem.getPosition() - amount + 1)
            newContainer.updateSameTags()
            newContainer.tags["title"] = [ name ]
            self.dataChanged.emit(self.index(insertPosition, 0, parentIndex), self.index(self.rowCount(parentIndex)-1, 0, parentIndex))
            self.dataChanged.emit(parentIndex, parentIndex)
            
    def flatten(self, index):
        """Set all files below this container as direct children, enumerate them in ascending order, and forget about all
        intermediate subcontainers."""
        
        self.beginRemoveRows(index, 0, self.rowCount(index)-1)
        self.endRemoveRows()
        index.internalPointer().flatten()
        self.beginInsertRows(index, 0, len(index.internalPointer().contents)-1)
        self.endInsertRows()
        
        
        
    def commit(self):
        """Commits all the containers and files in the current model into the database."""
        
        logger.debug("commit called")
        for item in self.root.contents:
            item.commit(toplevel = True)
        self.setRoot(RootNode())