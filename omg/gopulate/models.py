# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore
from PyQt4.QtCore import Qt

from omg.models import rootedtreemodel
import omg.models
import omg.database as database
from omg.models.playlist import BasicPlaylist

import omg.gopulate
absPath = omg.gopulate.absPath

import logging
logger = logging.getLogger("gopulate.models")
db = database.get()

class DirectoryNode(omg.models.RootNode):
    """Represents a directory in the filesystem, which is not a container."""
    def __init__(self, path=None):
        omg.models.RootNode.__init__(self)
        self.path = path
    
    def __str__(self):
        return self.path

class GopulateTreeModel(BasicPlaylist):
    
    #currentDirectoryChanged = QtCore.pyqtSignal(['QString'])
    
    def __init__(self, searchdirs):
        rootedtreemodel.RootedTreeModel.__init__(self)
        self.current = None
        self.searchdir = None
        self.setSearchDirectory(searchdirs)
    
    def setCurrentDirectory(self, dir):
        logger.debug('current directory set: {}'.format(self.searchdir))
        self.current = dir
        self._createTree(dir, omg.gopulate.findAlbumsInDirectory(dir, False))
        
    def setSearchDirectory(self, dir):
        logger.debug('search directory set: {}'.format(self.searchdir))
        self.searchdir = dir
        self.finder = None
        #self.nextDirectory()
        
    def nextDirectory(self):
        logger.debug('next directory, searchdir: {}'.format(self.searchdir))
        if self.finder == None:
            self.finder = omg.gopulate.findNewAlbums(self.searchdir)
        self._createTree(*next(self.finder))
        
    def _createTree(self, path, albums):
        root = DirectoryNode(path)
        for el in albums:
            root.contents.append(el)
            el.parent = root
        self.setRoot(root)
        self.current = path
        
    def merge(self, items, name):
        amount = len(items)
        if amount > 0:
            posItem = items[0]
            parent = posItem.parent().internalPointer()
            if not parent:
                parent = self.root
            newContainer = omg.models.Container(id = None)
            newContainer.parent = parent
            newContainer.position = posItem.internalPointer().getPosition()
            parent.contents.insert(posItem.row(), newContainer)
            i = 1
            for item in items:
                item.internalPointer().parent = newContainer
                item.internalPointer().position = i
                newContainer.contents.append(item.internalPointer())
                parent.contents.remove(item.internalPointer())
                i = i + 1
            for oldItem in parent.contents[posItem.row()+1:]:
                oldItem.position = oldItem.getPosition() - amount + 1
            newContainer.updateSameTags()
            newContainer.tags["title"] = [ name ]
        self.reset()
                
        
    def commit(self):
        """Commits all the containers and files in the current model into the database."""
        
        logger.debug("commit called")
        for item in self.root.contents:
            logger.debug("item of type {}".format(type(item)))
            item.commit(toplevel=True)
        self.setCurrentDirectory(self.current)