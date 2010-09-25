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
from omg import database
from omg.models.playlist import BasicPlaylist, ManagedPlaylist
from omg import constants

from . import GopulateGuesser, findNewAlbums
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
          
    def merge(self, indices, name):
        amount = len(indices)
        if amount > 0:
            posItem = indices[0]
            parent = posItem.parent().internalPointer()
            if not parent:
                parent = self.root
            newContainer = omg.models.Container(id = None)
            newContainer.parent = parent
            newContainer.position = posItem.internalPointer().getPosition()
            parent.contents.insert(posItem.row(), newContainer)
            j = 1
            for index in indices:
                item = index.internalPointer()
                item.parent = newContainer
                item.setPosition(j)
                newContainer.contents.append(item)
                parent.contents.remove(item)
                parent.changesPending = True
                for i in range(len(item.tags["title"])):
                    item.tags["title"][i] = item.tags["title"][i].replace(name, "").\
                        strip(constants.FILL_CHARACTERS).\
                        lstrip("0123456789").\
                        strip(constants.FILL_CHARACTERS)
                j = j + 1
            for oldItem in parent.contents[posItem.row()+1:]:
                if oldItem.getPosition():
                    oldItem.setPosition(oldItem.getPosition() - amount + 1)
            newContainer.updateSameTags()
            newContainer.tags["title"] = [ name ]
                
        
    def commit(self):
        """Commits all the containers and files in the current model into the database."""
        
        logger.debug("commit called")
        for item in self.root.contents:
            print(item)
            logger.debug("item of type {}".format(type(item)))
            item.commit(toplevel=True)
        self._createTree(self.guesser.guessTree(False))