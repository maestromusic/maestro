# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore
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

class DirectoryNode(omg.models.Node):
    """Represents a directory in the filesystem, which is not a container."""
    def __init__(self, path=None, parent=None):
        self.contents = []
        self.parent = parent
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
            myId = database.queries.addContainer(self.name, self.tags, len(self.contents), toplevel = toplevel)
        for i in range(len(self.contents)):
            elem = self.contents[i]
            if isinstance(elem, GopulateContainer) or isinstance(elem, FileSystemFile):
                elemId = elem.commit()
                database.queries.addContent(myId, i, elemId)
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

    
    def writeTagsToFilesystem(self):
        real = realfiles.File(absPath(self.path))
        real.tags = self.tags
        real.save_tags()
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
    
    def toolTipText(self):
        return formatter.HTMLFormatter(self).detailView()
    
    def commit(self):
        logger.debug("commiting file {}".format(self.path))
        fileId = database.queries.addContainer(os.path.basename(self.path), self.tags, elements=0)
        querytext = "INSERT INTO files (element_id,path,hash,length) VALUES(?,?,?,?);"
        if self.length is None:
            self.length = 0
        if not self.hash:
            self.computeHash()
        db.query(querytext, fileId, relPath(self.path), self.hash, int(self.length))
        return fileId
        
    def __str__(self):
        return str(self.tags)

class GopulateTreeModel(rootedtreemodel.RootedTreeModel):
    
    currentDirectoryChanged = QtCore.pyqtSignal(['QString'])
    def __init__(self, searchdirs):
        rootedtreemodel.RootedTreeModel.__init__(self)
        self.setSearchDirectory(searchdirs)
    
    def setCurrentDirectory(self, dir):
        self.current = dir
        self._createTree(dir, omg.gopulate.findAlbumsInDirectory(dir, False))
        
    def setSearchDirectory(self, dir):
        self.searchdirs = dir
        self.finder = None
        self.nextDirectory()
        
    def nextDirectory(self):
        logger.debug('next directory, searchdirs: {}'.format(self.searchdirs))
        if self.finder == None:
            self.finder = omg.gopulate.findNewAlbums(self.searchdirs)
        self._createTree(*next(self.finder))
        
    def _createTree(self, path, albums):
        root = DirectoryNode(path)
        for el in albums:
            root.contents.append(el)
            el.parent = root
        self.setRoot(root)
        self.current = path
        
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
        return rootedtreemodel.RootedTreeModel.flags(self,index) | Qt.ItemIsEditable
    
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