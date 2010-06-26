#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import difflib

from omg import database, mpclient
from . import rootedtreemodel, treebuilder, Node, Element, FilelistMixin, IndexMixin

db = database.get()

class PlaylistElement(Element):
    def __init__(self,id,contents):
        Element.__init__(self,id)
        self.length = None
        self.position = None
        self.contents = contents
    
    def getPosition(self):
        if self.parent is None or isinstance(self.parent,RootNode): # Without parent, there can't be a position
            return None
        if self.position is None:
            self.position = db.query("SELECT position FROM contents WHERE container_id = ? AND element_id = ?", 
                                     self.parent.id,self.id).getSingle()
        return self.position
    
    def getLength(self):
        if self.length is None:
            self.length = Element.getLength(self)
        return self.length
        
        
class Playlist(rootedtreemodel.RootedTreeModel):
    # List of all paths of songs in the playlist. Used for fast synchronization with MPD.
    pathList = None
    
    # Toplevel elements in the playlist
    contents = None
    
    # Currently playing index (file-index; position in the playlist) and element
    currentlyPlayingIndex = None
    currentlyPlayingElement = None
    
    # TreeBuilder to create the playlist-tree from MPD's playlist-list.
    _treeBuilder = None
    
    # While _syncLock is True, synchronization with MPD pauses. This is used during complex changes of the model.
    _syncLock = False
    
    def __init__(self):
        """Initialize with an empty playlist."""
        rootedtreemodel.RootedTreeModel.__init__(self,RootNode())
        self.setContents([])
        self._treeBuilder = treebuilder.TreeBuilder(self._getId,self._getParentIds,self._createNode,self._insertIntoNode)
    
    def setContents(self,contents):
        """Set the contents of this playlist. The contents are only the toplevel-elements in the playlist, not all files."""
        self.contents = contents
        self.root.contents = contents
        
    def startSynchronization(self):
        """Start to synchronize this playlist with MPD."""
        self.pathList = [file.getPath() for file in self.root.getAllFiles()]
    
    def stopSynchronization(self):
        """Stop synchronizing this playlist with MPD."""
        self.pathList = None
    
    def _getFilteredOpcodes(self,a,b):
        """Helper method for synchronize: Use difflib.SequenceMatcher to retrieve a list of opCodes describing how to turn <a> into <b> and filter and improve it:
        - opCodes with 'equal'-tag are removed
        - opCodes with 'replace'-tag are replaced by a 'delete'-tag and an 'insert'-tag
        - After performing the action of an opCode (e.g. deleting some files) the indices of subsequent files change and performing the action of the next opCode would lead to errors. So this method also corrects the indices (e.g. decreases all subsequent indices by the number of deleted files."""
        opCodes = difflib.SequenceMatcher(None,a,b).get_opcodes()
        offset = 0
        for tag,i1,i2,j1,j2 in opCodes:
            if tag == 'equal':
                continue
            elif tag == 'delete':
                yield (tag,i1+offset,i2+offset,-1,-1)
                offset = offset - i2 + i1
            elif tag == 'insert':
                yield (tag,i1+offset,i2+offset,j1,j2)
                offset == offset + j2 - j1
            elif tag == 'replace':
                yield ('delete',i1+offset,i2+offset,-1,-1)
                offset = offset - i2 + i1
                yield (tag,i1+offset,i2+offset,j1,j2)
                offset == offset + j2 - j1
            else: raise ValueError("Opcode tag {0} is not supported.".format(tag))
                        
    def synchronize(self,pathList,status):
        """Synchronize with MPD: Change the playlist to match the given list of paths. <status> is the MPD-status and is used to synchronize the currently played song."""
        if self._syncLock:
            return
            
        if len(pathList) == 0 and len(self.contents) > 0:
            self.contents = []
            self.reset()
        else:
            for tag,i1,i2,j1,j2 in self._getFilteredOpcodes(self.pathList,pathList):
                if tag == 'delete':
                    del self.pathList[i1:i2]
                    self._removeByFileIndices(self.root,i1,i2)
                #~ elif tag == 'insert' # TODO
                else: #TODO: This can be removed when handling of 'insert' is implemented
                    self.setContents(self._treeBuilder.build([self._createItem(path) for path in pathList]))
                    for element in self.contents:
                        element.parent = self.root
                    self.pathList = pathList
                    self.reset()
                    break
            
            # Synchronize currently playing song
            if 'song' not in status:
                if self.currentlyPlayingIndex is not None:
                    self.currentlyPlayingIndex = None
                    index = self.getIndex(self.currentlyPlayingElement)
                    self.dataChanged.emit(index,index)
                    self.currentlyPlayingElement = None
            elif status['song'] != self.currentlyPlayingIndex:
                self.currentlyPlayingIndex = status['song']
                self.currentlyPlayingElement = self.root.getFileByIndex(status['song'])
                index = self.getIndex(self.currentlyPlayingElement)
                self.dataChanged.emit(index,index)
                
    def isPlaying(self,element):
        """Return whether the song <element> is the one which is currently played by MPD."""
        return element == self.currentlyPlayingElement
    
    def removeByQtIndex(self,index):
        """Remove the element with the given Qt-index from the model and remove all files within it from the MPD-playlist. The index may point to a file or a container, but must be valid."""
        if not index.isValid():
            raise ValueError("Playlist.removeByQtIndex: Index is not valid.")
        
        self._syncLock = True
        element = self.data(index)
        parentIndex = self.parent(index)
        if parentIndex.isValid():
            parent = self.data(parentIndex)
            if parent.getChildrenCount() == 1:
                # Instead of removing the only child, remove parent
                self.removeByQtIndex(parentIndex)
                return
        else: parent = self.root
                
        # Update playlists
        start = element.getOffset()
        end = start+element.getFileCount()
        mpclient.delete(start,end)
        del self.pathList[start:end]
        
        # Update TreeModel
        pos = parent.index(element)
        self.beginRemoveRows(parentIndex,pos,pos)
        del parent.contents[pos]
        self.endRemoveRows()
        self._syncLock = False
        
    def removeFiles(self,start,end):
        """Remove the files with offsets <start>-<end> (without <end>!) from the playlist. Containers which are empty after removal are removed, too. <start> must be >= 0 and < self.root.getFileCount(), <end> must be > <start> and <= self.root.getFileCount(), or otherwise an IndexError is raised."""
        self._syncLock = True
        mpclient.delete(start,end)
        del self.pathList[start:end]
        self._removeFiles(self.root,start,end)
        self._syncLock = False
        
    def _removeFiles(self,element,start,end):
        """Remove the files with offsets <start>-<end> (without <end>!) from <element>s children. <start> and <end> are file offset, so the files which are removed are not necessarily direct children. Containers which are empty after removal are removed, too. But note that <element> may be empty after this method. <start> must be >= 0 and < element.getFileCount(), <end> must be > <start> and <= element.getFileCount(), or otherwise an IndexError is raised.
        
        Warning: This method does not update the pathlist used to synchronize with MPD, nor does it update MPD itself. Use removeFiles, to keep the model consistent.
        """
        if start <0 or end <= start:
            raise IndexError("Playlist._removeFiles: Offsets out of bounds: start is {0} and end is {0}."
                                .format(start,end))
        # a is the first item which is removed or from which children are removed
        # b is the last item which is removed or from which children are removed
        aIndex = None
        bIndex = None
        
        # Find a and b and gather information about them
        offset = 0
        for i in range(0,len(element.contents)):
            fileCount = element.contents[i].getFileCount()
            if aIndex is None and offset + fileCount > start:
                aIndex = i
                aFileCount = fileCount
                aOffset = offset
                # If all of a's children are going to be removed, remove also a
                removeA = offset == start and offset + fileCount <= end
            if offset + fileCount >= end:
                bIndex = i
                bFileCount = fileCount
                bOffset = offset
                # If all of b's children are going to be removed, remove also b
                removeB = offset >= start and offset + fileCount == end
                break
            offset = offset + fileCount
        
        # If a or b were not found, something is wrong with the offsets
        if aIndex is None or bIndex is None:
            raise IndexError("Something is wrong with the offsets. I tried to remove elements {0}-{1} from {2}".format(start,end,element))
        
        # self.contents[delStart:delEnd] will be removed completely. Now the question is whether to include a or b in this range or not.
        delStart = aIndex if removeA else aIndex+1
        delEnd = bIndex+1 if removeB else bIndex
        
        # Now we start to actually remove elements. We start at the end, because the indices are going to become invalid.
        if not removeB:
            self._removeFiles(element.contents[bIndex],max(start-bOffset,0),end-bOffset)

        if delStart<delEnd:
            self.beginRemoveRows(self.getIndex(element),delStart,delEnd-1)
            del element.contents[delStart:delEnd]
            self.endRemoveRows()
        
        if aIndex != bIndex and not removeA: # If a == b, we've removed the children above
            self._removeFiles(element.contents[aIndex],start-aOffset,aFileCount)
        
    def _createItem(self,path):
        """Create a playlist-item for the given path. If the path is in the database, an instance of PlaylistElement is created, otherwise an instance of ExternalFile. This method is used to create items based on the MPD-playlist."""
        id = db.query("SELECT container_id FROM files WHERE path = ?",path).getSingle()
        if id is None:
            return ExternalFile(path)
        else: return PlaylistElement(id,[])
    
    def _getId(self,item):
        """Return the id of item or None if it is an ExternalFile. This is a helper method for the TreeBuilder-algorithm."""
        if isinstance(item,ExternalFile):
            return None
        else: return item.id
        
    def _getParentIds(self,id):
        """Return a list containing the ids of all parents of the given id. This is a helper method for the TreeBuilder-algorithm."""
        return [id for id in db.query("SELECT container_id FROM contents WHERE element_id = ?",id).getSingleColumn()]
               
    def _createNode(self,id,contents):
        """Create a PlaylistElement for a container with the given id and contents. This is a helper method for the TreeBuilder-algorithm."""
        newElement = PlaylistElement(id,contents)
        for element in contents:
            element.parent = newElement
        return newElement

    def _insertIntoNode(self):
        pass
        
    
class ExternalFile(Node,FilelistMixin):
    """This class holds a file that appears in the playlist, but is not in the database."""
    
    def __init__(self,path,parent = None):
        """Initialize with the given path and parent."""
        self.path = path
        self.parent = parent
    
    def isFile(self):
        return True
    
    def isContainer(self):
        return False
        
    def getParent(self):
        return self.parent
        
    def getPath(self):
        return self.path
    
    def hasChildren(self):
        return False

    def getAllFiles(self):
        return (self,)
    
    def getFileCount(self):
        return 1
        
    def getFileByOffset(self,offset):
        if offset != 0:
            raise IndexError("Offset {0} is out of bounds".format(offset))
        return self


class RootNode(Node,FilelistMixin,IndexMixin):
    """Rootnode of the Playlist-TreeModel."""
    def __init__(self):
        self.contents = []
    
    def getParent(self):
        return None