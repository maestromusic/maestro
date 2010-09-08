# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
import os.path

from omg.models import rootedtreemodel
import omg.models
from functools import reduce
import omg.realfiles as realfiles
import omg.database as database
from omg.gui import formatter

import omg.gopulate
import omg.tags as tags
from omg import relPath, absPath
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


class GopulateContainer(omg.models.Node):
    """Class for containers which are not yet in the database."""
    def __init__(self, name = None, parent=None):
        self.parent = parent
        self.contents = []
        self.tracks = {}
        self.name = name
        self.existingContainer = None
        
    def __str__(self):
        return self.name
    
    def finalize(self):
        self.contents = []
        for i in sorted(self.tracks.keys()):
            self.contents.append(self.tracks[i])
            self.tracks[i].parent = self
        del self.tracks
        self.updateSameTags()
        self.tags['title'] = self.contents[0].tags['album']
    
    def updateSameTags(self):
        self.commonTags = reduce(lambda x,y: x & y, [set(tr.tags.keys()) for tr in self.contents])
        self.commonTagValues = {}
        differentTags=set()
        for file in self.contents:
            t = file.tags
            for tag in self.commonTags:
                if tag not in self.commonTagValues:
                    self.commonTagValues[tag] = t[tag]
                if self.commonTagValues[tag] != t[tag]:
                    differentTags.add(tag)
        self.sameTags = self.commonTags - differentTags
        self.tags = tags.Storage()
        for tag in self.sameTags:
            self.tags[tag] = self.commonTagValues[tag]
    
    def mergeWithExisting(self, element):
        self.existingContainer = element
        for i in range(len(element.contents)):
            if tags.get("tracknumber") in element.contents[i].tags:
                self.tracks[int(element.contents[i].tags["tracknumber"][0].split("/")[0])] = element.contents[i] 
            else:
                self.tracks[i] = element.contents[i]
    
    def commit(self, toplevel = False):
        logger.debug("commiting container {}".format(self.name))
        if self.existingContainer:
            myId = self.existingContainer.id
        else:
            myId = database.queries.addContainer(self.name, tags = self.tags, file = False, elements = len(self.contents), toplevel = toplevel)
        for elem in self.contents:
            if isinstance(elem, GopulateContainer) or isinstance(elem, FileSystemFile):
                elemId = elem.commit()
                database.queries.addContent(myId, elem.getPosition(), elemId)
        return myId
    
    def toolTipText(self):
        if self.existingContainer:
            return "DB-container '{}' with some non-DB elements".format(self.name)
        else:
            return "Non-DB container '{}' ({} elements)".format(self.name, len(self.contents))
            
        
class FileSystemFile(omg.models.Node):
    def __init__(self, path, tags = None, length = None, parent = None):
        self.path = path
        self.tags = tags
        self.length = length
        self.parent = parent
        self.hash = None
        self.contents = []
        self.position = 0
    
    def ensureTagsAreLoaded(self):
        if self.tags == None:
            self.readTagsFromFilesystem()
            
    def readTagsFromFilesystem(self):
        real = realfiles.File(absPath(self.path))
        try:
            real.read()
        except realfiles.ReadTagError as e:
            logger.warning("Failed to read tags from file {}: {}".format(self.path, str(e)))
        self.tags = real.tags
        self.length = real.length

    #MIGRATED
    def writeTagsToFilesystem(self):
        real = realfiles.File(absPath(self.path))
        real.tags = self.tags
        real.save_tags()
    
    # MIGRATED    
    def computeHash(self):
        """Computes the hash of the audio stream."""
    
        import hashlib,tempfile,subprocess
        handle, tmpfile = tempfile.mkstemp()
        subprocess.check_call(
            ["mplayer", "-dumpfile", tmpfile, "-dumpaudio", absPath(self.path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        # wtf ? for some reason handle is int instead of file handle, as said in documentation
        handle = open(tmpfile,"br")
        self.hash = hashlib.sha1(handle.read()).hexdigest()
        handle.close()
        os.remove(tmpfile)
    
    # MIGRATED
    def getPosition(self):
        return self.position
    

    def setPosition(self, position):
        self.position = position
        

    #MIGRATED
    def getLength(self):
        return self.length
    
    def toolTipText(self):
        return formatter.HTMLFormatter(self).detailView()
    
    #MIGRATED
    def commit(self):
        logger.debug("commiting file {}".format(self.path))
        fileId = database.queries.addContainer(os.path.basename(self.path), tags = self.tags, file = True, elements = 0)
        querytext = "INSERT INTO files (element_id,path,hash,length) VALUES(?,?,?,?);"
        if self.length is None:
            self.length = 0
        if not self.hash:
            self.computeHash()
        db.query(querytext, fileId, relPath(self.path), self.hash, int(self.length))
        return fileId
        
    def __str__(self):
        return "FileSystemFile " + str(self.tags)

class GopulateTreeModel(rootedtreemodel.RootedTreeModel):
    
    currentDirectoryChanged = QtCore.pyqtSignal(['QString'])
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
            newContainer = GopulateContainer(name="new container", parent = parent)
            parent.contents.insert(posItem.row(), newContainer)
            i = 1
            for item in items:
                item.internalPointer().parent = newContainer
                item.internalPointer().position = i
                newContainer.contents.append(item.internalPointer())
                parent.contents.remove(item.internalPointer())
                i = i + 1
            for oldItem in parent.contents[posItem.row()+1:]:
                oldItem.setPosition(oldItem.getPosition() - amount + 1)
            newContainer.updateSameTags()
            newContainer.tags["album"] = [ name ]
        self.reset()
                
        
    def commit(self):
        """Commits all the containers and files in the current model into the database."""
        
        logger.debug("commit called")
        for item in self.root.contents:
            logger.debug("item of type {}".format(type(item)))
            if isinstance(item, GopulateContainer) or isinstance(item, FileSystemFile):
                item.commit(toplevel=True)
        self.setCurrentDirectory(self.current)
    
    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        return rootedtreemodel.RootedTreeModel.flags(self,index)
    
    def setData(self, index, value, role):
        if index.isValid() and role == Qt.EditRole:
            elem = index.internalPointer()
            if type(elem) == FileSystemFile:
                elem.tags['edit'] = [ value ]
            elif type(elem) == GopulateContainer:
                elem.name = value
            else:
                logger.warning("setData called with type {}".format(type(elem)))
            self.dataChanged.emit(index,index)
            return True
        return False