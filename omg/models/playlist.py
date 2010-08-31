#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import difflib, logging, os

from PyQt4 import QtCore
from PyQt4.QtCore import Qt

from omg import config, database, mpclient, tags, absPath, relPath, models
import omg.gopulate.models as gopmodels
from . import rootedtreemodel, treebuilder, mimedata
from . import Node, DBFile, Container

db = database.get()
logger = logging.getLogger("omg.models.playlist")


class Playlist(rootedtreemodel.RootedTreeModel):
    # List of all paths of songs in the playlist. Used for fast synchronization with MPD.
    pathList = None
    
    # Toplevel elements in the playlist
    contents = None
    
    # Currently playing offset and a persistent index to the element
    currentlyPlayingOffset = None
    currentlyPlayingElement = None
    
    # While _syncLock is True, synchronization with MPD pauses. This is used during complex changes of the model.
    _syncLock = False
    
    def __init__(self):
        """Initialize with an empty playlist."""
        rootedtreemodel.RootedTreeModel.__init__(self,models.RootNode())
        self.setContents([])
    
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
    
    def flags(self,index):
        defaultFlags = rootedtreemodel.RootedTreeModel.flags(self,index)
        if index.isValid():
            return defaultFlags | Qt.ItemIsDropEnabled | Qt.ItemIsDragEnabled
        else: return defaultFlags | Qt.ItemIsDropEnabled
    
    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction
         
    def mimeTypes(self):
        return [config.get("gui","mime"),"text/uri-list"]
    
    def mimeData(self,indexes):
        return mimedata.createFromIndexes(self,indexes)
    
    # A note on removing and inserting rows via DND: We cannot implement insertRows because we have no way to insert empty rows without elements. Instead we overwrite dropMimeData and use self.insertElements. On the other hand we implement removeRows to remove rows at the end of internal move operations and let Qt call this method.
    def dropMimeData(self,mimeData,action,row,column,parentIndex):
        if action == Qt.IgnoreAction:
            return True

        if column > 0:
            return False
            
        if parentIndex.isValid():
            parent = self.data(parentIndex)
            if 0 <= row < parent.getChildrenCount():
                offset = parent.getChildren()[row].getOffset()
            else: offset = parent.getOffset()+parent.getFileCount() # at the end of parent
        else:
            parent = self.root
            if 0 <= row < self.root.getChildrenCount():
                offset = self.root.getChildren()[row].getOffset()
            else: offset = len(self.pathList)
            
        if mimeData.hasFormat(config.get("gui","mime")):
            self.insertElements([node.copy() for node in mimeData.retrieveData(config.get("gui","mime"))],offset)
            return True
        elif mimeData.hasFormat("text/uri-list"):
            self.insertElements(self.importPaths(relPath(url.path()) for url in mimeData.urls()),offset)
            return True
        else: return False
        
    def removeRows(self,row,count,parentIndex):
        parent = self.data(parentIndex) if parentIndex.isValid() else self.root
        start = parent.getChildren()[row].getOffset()
        lastElement = parent.getChildren()[row+count-1]
        end = lastElement.getOffset()+lastElement.getFileCount()
        self.removeFiles(start,end)
        return True

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
                yield ('insert',i1+offset,i2+offset,j1,j2)
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
                    self._removeFiles(self.root,i1,i2)
                    self.glue(self.root,i1)
                elif tag == 'insert':
                    self.pathList[i1:i1] = pathList[j1:j2]
                    self._insertElements(self.root,[self._createItem(path) for path in pathList[j1:j2]],i1)
                else:
                    # Opcodes are filtered to contain only 'delete' and 'insert'
                    logger.debug("Got an unknown opcode: '{}',{},{},{},{}".format(tag,i1,i2,j1,j2))
            
            # Synchronize currently playing song
            if 'song' not in status:
                if self.currentlyPlayingOffset is not None:
                    self.currentlyPlayingOffset = None
                    try:
                        index = self.getIndex(self.currentlyPlayingElement)
                        self.dataChanged.emit(index,index)
                    except ValueError: pass # Probably the element was removed from the playlist
                    self.currentlyPlayingElement = None
            elif status['song'] != self.currentlyPlayingOffset:
                oldElement = self.currentlyPlayingElement
                self.currentlyPlayingOffset = status['song']
                self.currentlyPlayingElement = self.root.getFileAtOffset(status['song'])
                # Update the new and the old song
                if oldElement is not None:
                    try:
                        index = self.getIndex(oldElement)
                        self.dataChanged.emit(index,index)
                    except ValueError: pass # Probably the element was removed from the playlist
                index = self.getIndex(self.currentlyPlayingElement)
                self.dataChanged.emit(index,index)
    
    def restructure(self):
        """Restructure the whole container tree in this model. This method does not change the flat playlist, but it uses treebuilder to create an optimal container structure over the MPD playlist."""
        treeBuilder = self._createTreeBuilder([self._createItem(path) for path in self.pathList])
        treeBuilder.buildParentGraph()
        self.setContents(treeBuilder.buildTree(createOnlyChildren=False))
        for element in self.contents:
            element.parent = self.root
        self.reset()
        
    def isPlaying(self,element):
        """Return whether the song <element> is the one which is currently played by MPD."""
        return element == self.currentlyPlayingElement
    
    def removeByQtIndex(self,index):
        """Remove the element with the given Qt-index from the model and remove all files within it from the MPD-playlist. The index may point to a file or a container, but must be valid."""
        if not index.isValid():
            raise ValueError("Playlist.removeByQtIndex: Index is not valid.")
        
        offset = self.data(index).getOffset()
        self.removeFiles(offset,offset+1)
        #~ self._syncLock = True
        #~ element = self.data(index)
        #~ parentIndex = self.parent(index)
        #~ if parentIndex.isValid():
            #~ parent = self.data(parentIndex)
            #~ if parent.getChildrenCount() == 1:
                #~ # Instead of removing the only child, remove parent
                #~ self.removeByQtIndex(parentIndex)
                #~ return
        #~ else: parent = self.root
                #~ 
        #~ # Update playlists
        #~ start = element.getOffset()
        #~ end = start+element.getFileCount()
        #~ mpclient.delete(start,end)
        #~ del self.pathList[start:end]
        #~ 
        #~ # Update TreeModel
        #~ pos = parent.index(element)
        #~ self.beginRemoveRows(parentIndex,pos,pos)
        #~ del parent.contents[pos]
        #~ self.endRemoveRows()
        #~ self._syncLock = False
        
    def removeFiles(self,start,end):
        """Remove the files with offsets <start>-<end> (without <end>!) from the playlist. Containers which are empty after removal are removed, too. <start> must be >= 0 and < self.root.getFileCount(), <end> must be > <start> and <= self.root.getFileCount(), or otherwise an IndexError is raised."""
        if self._syncLock:
            logger.warning("removeFiles was called while syncLock was True.")
            return
        self._syncLock = True
        self._removeFiles(self.root,start,end)
        self.glue(self.root,start)
        try:
            mpclient.delete(start,end)
        except mpclient.CommandError as e:
            logger.error("Deleting files from MPD's playlist failed: "+e.message)
        del self.pathList[start:end]
        self._syncLock = False
        
    def _removeFiles(self,element,start,end):
        """Remove the files with offsets <start>-<end> (without <end>!) from <element>s children. <start> and <end> are file offset, so the files which are removed are not necessarily direct children. Containers which are empty after removal are removed, too. But note that <element> may be empty after this method. <start> must be >= 0 and < element.getFileCount(), <end> must be > <start> and <= element.getFileCount(), or otherwise an IndexError is raised.
        
        Warning: This method does not update the pathlist used to synchronize with MPD, nor does it update MPD itself. Use removeFiles, to keep the model consistent.
        """
        #print("This is _removeFiles for element {} at start {} and end {}".format(element,start,end))
        logger.debug("This is _removeFiles for element {} at start {} and end {}".format(element,start,end))
        if start <0 or end <= start:
            raise IndexError("Playlist._removeFiles: Offsets out of bounds: start is {} and end is {}.".format(start,end))
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
    
    def insertElements(self,elements,offset):
        if self._syncLock:
            logger.warning("insertElements was called while _syncLock was True.")
            return
        self._syncLock = True

        if offset == -1:
            offset = len(self.pathList)
            
        elements = elements[:]
        
        # Replace nodes with only one child by the child. This is necessary to be consistent with using the TreeBuilder with createOnlyChildren=False.
        for i in range(0,len(elements)):
            if elements[i].getChildrenCount() == 1:
                elements[i] = elements[i].getChildren()[0]
               
        self._insertElements(self.root,elements,offset)
        
        # Update pathList
        for element in elements:
            pathList = [file.getPath() for file in element.getAllFiles()]
            self.pathList[offset:offset] = pathList
            mpclient.insert(offset,pathList)  #TODO: Catch errors
            offset = offset + len(pathList)
        self._syncLock = False
    
    def _insertElements(self,parent,elements,offset):
        #print("This is _insertElements for parent {} at offset {} and with elements {}"
            #.format(parent,offset,[str(element) for element in elements]))
        logger.debug("This is _insertElements for parent {} at offset {} and with {} elements."
                        .format(parent,offset,len(elements)))
        fileCount = parent.getFileCount()
        if offset == -1:
            offset = fileCount

        if offset < 0 or offset > fileCount:
            raise IndexError("Offset {} is out of bounds".format(offset))
        
        treeBuilder = self._createTreeBuilder(elements)
        treeBuilder.buildParentGraph()
        treeRoots = treeBuilder.buildTree(createOnlyChildren=False)
        
        parent,insertIndex,insertOffset,split = self._getInsertInfo(treeBuilder,parent,offset)
        #print("I am trying to {4}insert {0} elements at index {1}/offset {2} into {3}"
        #         .format(len(treeRoots),insertIndex,insertOffset,parent,"split and " if split else ""))

        if split:
            if self.split(parent,insertOffset):
                insertIndex = insertIndex + 1 # A new node has been created
        
        for root in treeRoots:
            root.parent = parent
            
        self.beginInsertRows(self.getIndex(parent),insertIndex,insertIndex+len(treeRoots)-1)
        parent.contents[insertIndex:insertIndex] = treeRoots
        self.endInsertRows()
        
        self.glue(parent,insertOffset)
        self.glue(parent,insertOffset+sum(element.getFileCount() for element in elements))
        
        # Update the parent since the number of files in it will have changed
        if parent is not self.root:
            parentIndex = self.getIndex(parent)
            self.dataChanged.emit(parentIndex,parentIndex)
    
    def _getInsertInfo(self,treeBuilder,parent,offset):
        #print("This is _getInsertInfo for parent {0} at offset {1}".format(parent,offset))
        if not parent.hasChildren():
            return parent,0,0,False
            
        insertIndex,innerOffset = parent.getChildIndexAtOffset(offset)
        if insertIndex is None: # insertOffset points to the end of parent
            child = parent.getChildren()[-1]
            insertIndex = parent.getChildrenCount()
            innerOffset = child.getFileCount()
            split = False
        else:
            child = parent.getChildren()[insertIndex]
            # Don't split if offset points to the start of parent
            split = innerOffset != 0
        # If the elements which should be inserted fit all into child, then use child as parent
        if treeBuilder.containsAll(child):
            return self._getInsertInfo(treeBuilder,child,innerOffset)
        else: return parent,insertIndex,offset,split
            
    def split(self,element,offset):
        """Split <element> at the given offset. This method will ensure, that element has a child starting at offset <offset>. Note that this method does not change the flat playlist, but only the tree-structure. Split will return True if and only if a new node was created.
        
        Example: Assume <element> contains a container which contains 10 files. After splitting <element> at offset 5, <element> will contain two copys of the container, containing the files 0-4 and 5-9, respectively.
        """
        logger.debug("This is split for element {} at offset {}".format(element,offset))
        fileCount = element.getFileCount()
        if offset < 0 or offset > fileCount:
            raise IndexError("Offset {0} is out of bounds.".format(offset))
        if offset == 0 or offset == fileCount:
            return False # Nothing to split here
        
        index,innerOffset = element.getChildIndexAtOffset(offset)
        child = element.contents[index]
        if innerOffset == 0: # child starts at the given offset, so we there is no need to split
            return False
        newChild = child.copy(self._splitHelper(child,innerOffset))
        self.beginInsertRows(self.getIndex(element),index+1,index+1)
        element.contents.insert(index+1,newChild)
        self.endInsertRows()
        return True
        
    def _splitHelper(self,element,offset):
        """Helper for the split-Algorithm: Crop <element> to contain only the files before the given offset and return a tree containing the remaining children. If <element> contains a child starting at <offset>, this method will remove that child and all further children from <element> and return the removed children as list. Otherwise the method will copy the child containing <offset>, crop the original and insert the removed nodes in the copy. It will return the copy together with all further children."""
        index,innerOffset = element.getChildIndexAtOffset(offset)
        child = element.contents[index]
        
        # If there is a child starting at offset, we just remove all later children from this node and return them
        if innerOffset == 0:
            result = element.contents[index:]
            self.beginRemoveRows(self.getIndex(element),index,len(element.contents)-1)
            del element.contents[index:]
            self.endRemoveRows()
            return result
        else:
            # Otherwise we have to create a copy of child containing the files starting at offset. Here we use _splitHelper recursively.
            newChild = child.copy(contents=self._splitHelper(child,innerOffset))
            result = [newChild].extend(element.contents[index+1:])
            self.beginRemoveRows(self.getIndex(element),index+1,len(element.contents)-1)
            del element.contents[index+1:]
            self.endRemoveRows()
            return result
    
    def glue(self,parent,offset):
        #print("This is glue for parent {} at offset {}".format(parent,offset))
        logger.debug("This is glue for parent {} at offset {}".format(parent,offset))
        fileCount = parent.getFileCount()
        if offset < 0 or offset > fileCount:
            raise IndexError("Offset {} is out of bounds.".format(offset))
        
        if offset == 0 or offset == fileCount:
            return # There is nothing to glue at this positions
        
        prevIndex,prevOffset = parent.getChildIndexAtOffset(offset-1)
        nextIndex,nextOffset = parent.getChildIndexAtOffset(offset)
        prev = parent.getChildren()[prevIndex]
        next = parent.getChildren()[nextIndex]
        
        if isinstance(prev,ExternalFile) or isinstance(next,ExternalFile):
            return
        if prev.isFile() and next.isFile():
            return
            
        if prev is next: # Let next handle this
            self.glue(next,nextOffset)
        elif prev.id == next.id:
            prevFileCount = prev.getFileCount()
            self.beginRemoveRows(self.getIndex(parent),nextIndex,nextIndex)
            del parent.getChildren()[nextIndex]
            self.endRemoveRows()
            for element in next.getChildren():
                element.parent = prev
            self.beginInsertRows(self.getIndex(prev),prev.getChildrenCount(),
                                 prev.getChildrenCount()+next.getChildrenCount()-1)
            prev.getChildren().extend(next.getChildren())
            self.endInsertRows()
            self.glue(prev,prevFileCount) # glue just before the files which were just copied
        else:
            prevParents = prev.getParentIds(True)
            nextParents = next.getParentIds(True)
            if prev.id in nextParents:
                self.beginRemoveRows(self.getIndex(parent),nextIndex,nextIndex)
                del parent.getChildren()[nextIndex]
                self.endRemoveRows()
                self._insertElements(prev,[next],-1)
            elif next.id in prevParents:
                self.beginRemoveRows(self.getIndex(parent),prevIndex,prevIndex)
                del parent.getChildren()[prevIndex]
                self.endRemoveRows()
                self._insertElements(next,[prev],0)
            else: pass # TODO: If prev and next are files with a common parent we should group them into this parent
    
    def importPaths(self,paths):
        """Return a list of elements from the given (relative) paths which may be inserted into the playlist."""
        # _collectFiles works with absolute paths, so we need to convert paths before and after _collectFiles
        filePaths = [relPath(path) for path in self._collectFiles(absPath(p) for p in paths)]
        return [self._createItem(path) for path in filePaths]
        
    #~ def importElements(self,elements):
        #~ """Return a list of copies of <elements> which may be inserted into the playlist."""
        #~ return [self._importElement(element,None) for element in elements]
        #~ 
    #~ def _importElement(self,element,parent):
        #~ """Return a copy of <element> which may be inserted into the playlist. This method won't change <element> but it will set the copy's parent to <parent>, ensure that the copy's tags are loaded and recursively import all child elements."""
        #~ if isinstance(element,ExternalFile):
            #~ return ExternalFile(element.path,parent)
        #~ elif isinstance(element,Element):
            #~ newElement = PlaylistElement(element.id,[])
            #~ newElement.parent = parent
            #~ newElement.tags = element.tags
            #~ newElement.ensureTagsAreLoaded()
            #~ assert element.getChildren() is not None
            #~ newElement.contents = [self._importElement(child,newElement) for child in element.getChildren()]
            #~ return newElement
        #~ else: raise ValueError("element must be of type ExternalFile or Element, I got {} of type {}"
                                    #~ .format(element,type(element)))

    def _collectFiles(self,paths): # TODO: Sort?
        """Return a list of absolute paths to all files in the given paths (which must be absolute, too). That is, if a path in <paths> is a file, it will be contained in the resulting list, whereas if it is a directory, all files within (recursively) will be contained in the result."""
        filePaths = []
        for path in paths:
            if os.path.isfile(path):
                filePaths.append(path)
            elif os.path.isdir(path):
                filePaths.extend(self._collectFiles(os.path.join(path,p) for p in os.listdir(path)))
        return filePaths
   
    def _createItem(self,path,parent=None):
        """Create a playlist-item for the given path. If the path is in the database, an instance of DBFile is created, otherwise an instance of ExternalFile. The parent of the new element is set to <parent> (even when this is None)."""
        id = db.query("SELECT element_id FROM files WHERE path = ?",path).getSingle()
        if id is None:
            result = ExternalFile(path)
        else: result = DBFile(id)
        if not isinstance(result,ExternalFile): #TODO remove this line
            result.loadTags()
        result.parent = parent
        return result
        
    def _createTreeBuilder(self,items):
        """Create a TreeBuilder to create container-trees over the given list of elements."""
        return treebuilder.TreeBuilder(items,self._getId,self._getParentIds,self._createNode)
    
    def _getId(self,item):
        """Return the id of item or None if it is an ExternalFile. This is a helper method for the TreeBuilder-algorithm."""
        if isinstance(item,ExternalFile):
            return None
        else: return item.id
        
    def _getParentIds(self,id):
        """Return a list containing the ids of all parents of the given id. This is a helper method for the TreeBuilder-algorithm."""
        return [id for id in db.query("SELECT container_id FROM contents WHERE element_id = ?",id).getSingleColumn()]
               
    def _createNode(self,id,contents):
        """If contents is not empty, create an Container-instance for the given id containing <contents>. Otherwise create an instance of DBFile with the given id. This is a helper method for the TreeBuilder-algorithm."""
        if len(contents) > 0:
            newNode = Container(id,contents=contents)
        else: newNode = DBFile(id)
        newNode.loadTags()
        return newNode
        
    def _seqLen(self,sequence):
        """Return the length of an item-sequence."""
        return sequence[1] - sequence[0] + 1
            
    
class ExternalFile(gopmodels.FileSystemFile):
    """This class holds a file that appears in the playlist, but is not in the database."""
    
    def __init__(self,path,parent = None):
        """Initialize with the given path and parent."""
        gopmodels.FileSystemFile.__init__(self, path, parent = parent)
    
    def isFile(self):
        return True
    
    def isContainer(self):
        return False
        
    def getPath(self):
        return self.path
    
    def hasChildren(self):
        return False

    def getChildren(self):
        return []
        
    def getChildrenCount(self):
        return 0
        
    def getAllFiles(self):
        return (self,)
    
    def getFileCount(self):
        return 1
        
    def getFileAtOffset(self,offset):
        if offset != 0:
            raise IndexError("Offset {0} is out of bounds".format(offset))
        return self
    
    def loadTags(self):
        self.readTagsFromFilesystem()
        
    def __str__(self):
        return self.path