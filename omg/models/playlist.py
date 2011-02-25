#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import difflib, logging, os, itertools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg import database, models, mpclient, tags, absPath, relPath, distributor
from omg.config import options
from . import rootedtreemodel, treebuilder, mimedata

db = database.get()
logger = logging.getLogger("omg.models.playlist")

class RemoveContentsCommand(QtGui.QUndoCommand):
    def __init__(self, model, parentIdx, row, num, text="remove element(s)"):
        QtGui.QUndoCommand.__init__(self, text)
        self.model = model
        self.parentIdx = QtCore.QPersistentModelIndex(parentIdx)
        self.row = row
        self.num = num
        self.parentItem = model.data(parentIdx, Qt.EditRole)
        if self.parentItem is None:
            self.parentItem = model.root
        self.elements = self.parentItem.getChildren()[row:row+num]
    
    def redo(self):
        self.model.beginRemoveRows(QtCore.QModelIndex(self.parentIdx), self.row, self.row+self.num-1)
        del self.parentItem.getChildren()[self.row:self.row+self.num]
        self.model.endRemoveRows()
    
    def undo(self):
        self.model.beginInsertRows(QtCore.QModelIndex(self.parentIdx), self.row, self.row+self.num-1)
        self.parentItem.getChildren()[self.row:self.row] = self.elements
        for el in self.elements:
            el.parent = self.parentItem
        self.model.endInsertRows()

class InsertContentsCommand(QtGui.QUndoCommand):
    def __init__(self, model, parent, row, contents, copy = True, text = "insert element(s)"):
        QtGui.QUndoCommand.__init__(self, text)
        self.model = model
        if parent.isFile():
            raise ValueError("Cannot insert contents into file {}".format(parent))
        self.parentIdx = QtCore.QPersistentModelIndex(model.getIndex(parent))
        self.parentItem = parent
        self.row = row
        self.contents = contents
        if copy:
            self.contents = [node.copy() for node in self.contents]
    
    def redo(self):
        self.model.beginInsertRows(QtCore.QModelIndex(self.parentIdx), self.row, self.row + len(self.contents) - 1)
        for node in self.contents:
            node.setParent(self.parentItem)
        self.parentItem.getChildren()[self.row:self.row] = self.contents
        self.model.endInsertRows()
    
    def undo(self):
        self.model.beginRemoveRows(QtCore.QModelIndex(self.parentIdx), self.row, self.row + len(self.contents) - 1)
        del self.parentItem.getChildren()[self.row:self.row+len(self.contents)]
        self.model.endRemoveRows()
        

class ModelResetCommand(QtGui.QUndoCommand):
    def __init__(self, model):
        QtGui.QUndoCommand.__init__(self, "reset model")
        self.model = model
    
    def redo(self):
        self.oldRoot = self.model.root
        self.model.setRoot(models.RootNode())
    
    def undo(self):
        self.model.setRoot(self.oldRoot)
        self.model.reset()
        
class BasicPlaylist(rootedtreemodel.RootedTreeModel):
    """Basic model for playlists. A BasicPlaylists contains a list of nodes and supports insertion and removal of nodes as well as drag and drop of omg's own mimetype (config-variable gui->mime) and "text/uri-list"."""
    # Toplevel elements in the playlist
    contents = None
    
    def __init__(self):
        """Initialize with an empty playlist."""
        rootedtreemodel.RootedTreeModel.__init__(self,models.RootNode())
        self.setContents([])
        distributor.indicesChanged.connect(self._handleIndicesChanged)
        self.undoStack = QtGui.QUndoStack(self)
    
    def setRoot(self,root):
        """Set the root-node of this playlist which must be of type models.RootNode. All views using this model will be reset."""
        assert isinstance(root,models.RootNode)
        self.contents = root.contents
        rootedtreemodel.RootedTreeModel.setRoot(self,root)
       # self.undoStack.clear()
        
    def setContents(self,contents):
        """Set the contents of this playlist and set their parent to self.root. The contents are only the toplevel-elements in the playlist, not all files. All views using this model will be reset."""
        self.contents = contents
        self.root.contents = contents
        for node in contents:
            node.setParent(self.root)
        self.reset()
        
    def flags(self,index):
        defaultFlags = rootedtreemodel.RootedTreeModel.flags(self,index)
        if index.isValid():
            return defaultFlags | Qt.ItemIsDropEnabled | Qt.ItemIsDragEnabled
        else: return defaultFlags | Qt.ItemIsDropEnabled
    
    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction
         
    def mimeTypes(self):
        return [options.gui.mime,"text/uri-list"]
    
    def mimeData(self,indexes):
        return mimedata.createFromIndexes(self,indexes)

    # A note on removing and inserting rows via DND: We cannot implement insertRows because we have no way to insert empty rows without elements. Instead we overwrite dropMimeData and use self.insertElements. On the other hand we implement removeRows to remove rows at the end of internal move operations and let Qt call this method.
    def dropMimeData(self,mimeData,action,row,column,parentIndex):
        if action == Qt.IgnoreAction:
            return True

        if column > 0:
            return False
        
        contents = self._prepareMimeData(mimeData)
        if contents is None:
            return False
        self.undoStack.beginMacro("Drop item(s)")
        if parentIndex.isValid():
            parent = self.data(parentIndex)
        else: parent = self.root
        
        if 0 <= row < parent.getChildrenCount():
            self.insertContents(parent,row,contents,copy=False)
        else: # Probably the element was dropped onto parent and not between any rows
            if parent.isFile():
                # Insert as sibling next to parent
                self.insertContents(parent.getParent(),parent.getParent().index(parent)+1,contents,copy=False)
            else: self.insertContents(parent,parent.getChildrenCount(),contents,copy=False)
        self.undoStack.endMacro()
        return True

    def _prepareMimeData(self, mimeData):
        """Create an Element structure from the MIME data that can be inserted into the model."""
        if mimeData.hasFormat(options.gui.mime):
            return [node.copy() for node in mimeData.retrieveData(options.gui.mime)]
        elif mimeData.hasFormat("text/uri-list"):
            return self.importPaths(relPath(url.path()) for url in mimeData.urls())
        else:
            return None
        
    def removeRows(self,row,count,parentIndex):
        # Reimplementation of QAbstractItemModel.removeRows
        if parentIndex.isValid():
            parent = self.data(parentIndex)
        else: parent = self.root
        self.removeContents(parent,row,row+count)
        return True
        
    def removeContents(self,parent,start,end):
        """Remove the nodes with indices <start>-<end> (without <end>!) from <parent>'s children."""
        command = RemoveContentsCommand(self, self.getIndex(parent), start, end-start, "remove Item")
        self.undoStack.push(command)
        #self.beginRemoveRows(self.getIndex(parent),start,end-1)
        #del parent.getChildren()[start:end]
        #self.endRemoveRows()
    
    def removeByQtIndex(self,index):
        """Remove the element with the given Qt-index from the model and remove all files within it from the MPD-playlist. The index may point to a file or a container, but must be valid."""
        if not index.isValid():
            raise ValueError("BaiscPlaylist.removeByQtIndex: Index is not valid.")
        element = self.data(index)
        start =  element.getParent().index(element)
        self.removeContents(element.getParent(),start,start+1)
        
    def insertContents(self,parent,row,contents,copy=True):
        """Insert <contents> as children at the given row into the node <parent>. If <copy> is True, <contents> will be copied deeply which is usually the right thing to do, as the parents of the nodes in <contents> must be adjusted."""
        
        command = InsertContentsCommand(self, parent, row, contents, copy, text="insert Item(s)")
        self.undoStack.push(command)
        #=======================================================================
        # if parent.isFile():
        #    raise ValueError("Cannot insert contents into file {}".format(parent))
        # self.beginInsertRows(self.getIndex(parent),row,row+len(contents)-1)
        # if copy:
        #    contents = [node.copy() for node in contents]
        # for node in contents:
        #    node.setParent(parent)
        # parent.getChildren()[row:row] = contents
        # self.endInsertRows()
        #=======================================================================
    
    def importPaths(self,paths):
        """Return a list of elements from the given (relative) paths which may be inserted into the playlist."""
        # _collectFiles works with absolute paths, so we need to convert paths before and after _collectFiles
        filePaths = [relPath(path) for path in self._collectFiles(absPath(p) for p in paths)]
        return [self._createItem(path) for path in filePaths]
        
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
        """Create a playlist-item for the given path. The parent of the new element is set to <parent> (even when this is None)."""
        id = db.query("SELECT element_id FROM files WHERE path = ?",path).getSingle() # may be None
        result = models.File(id,path=path)
        result.loadTags()
        result.parent = parent
        return result

    def _handleIndicesChanged(self,event):
        allIds = event.getAllIds()

        if (event.deleted or event.created)\
                  and not set(allIds).isdisjoint(set(node.id for node in self.getAllNodes())):
            self.restructure()
            return

        for element in self.getAllNodes():
            if element.id in allIds:
                index = self.getIndex(element)
                dataChanged = False
                if event.cover:
                    element.deleteCoverCache()
                    dataChanged = True
                if event.tags:
                    element.loadTags()
                    dataChanged = True
                if dataChanged:
                    self.dataChanged.emit(index,index)
                

class ManagedPlaylist(BasicPlaylist):
    """A ManagedPlaylist organizes the tree-structure over the "flat playlist" (just the files) in a nice way. In contrast to BasicPlaylist, ManagedPlaylist uses mainly offsets to address files, as the tree-structure may change during most operations. Additionally offset-based insert- and remove-functions are needed for synchronization with MPD (confer SynchronizablePlaylist). Of course, there are also functions to insert and remove using a reference to the parent-container, but they internally just call the offset-based functions."""
    
    def restructure(self):
        """Restructure the whole container tree in this model. This method does not change the flat playlist, but it uses treebuilder to create an optimal container structure over the MPD playlist."""
        treeBuilder = self._createTreeBuilder([self._createItem(path) for path in self.pathList])
        treeBuilder.buildParentGraph()
        self.setContents(treeBuilder.buildTree(createOnlyChildren=False))
        for element in self.contents:
            element.parent = self.root
        self.reset()
        
    def removeContents(self,parent,start,end):
        # Reimplemented from BasicPlaylist
        startOffset = parent.getChildren()[start].getOffset()
        if end == parent.getChildrenCount():
            endOffset = parent.getOffset()+parent.getFileCount()
        else: endOffset = parent.getChildren()[end].getOffset()
        self.removeFiles(startOffset,endOffset)
    
    def removeFiles(self,start,end):
        """Remove the files with offsets <start>-<end> (without <end>!) from the playlist. Containers which are empty after removal are removed, too. <start> must be >= 0 and < self.root.getFileCount(), <end> must be > <start> and <= self.root.getFileCount(), or otherwise an IndexError is raised."""
        self._removeFiles(self.root,start,end)
        self.glue(self.root,start)
        
    def _removeFiles(self,element,start,end):
        """Remove the files with offsets <start>-<end> (without <end>!) from <element>s children. <start> and <end> are file offset, so the files which are removed are not necessarily direct children. Containers which are empty after removal are removed, too. But note that <element> may be empty after this method. <start> must be >= 0 and < element.getFileCount(), <end> must be > <start> and <= element.getFileCount(), or otherwise an IndexError is raised.
        
        Warning: This method does not update the pathlist used to synchronize with MPD, nor does it update MPD itself. Use removeFiles, to keep the model consistent.
        """
        #print("This is _removeFiles for element {} at start {} and end {}".format(element,start,end))
        logger.debug("This is _removeFiles for element {} at start {} and end {}".format(element,start,end))
        if start < 0 or end <= start:
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

    def insertContents(self,parent,index,contents,copy=True):
        # Reimplemented from BasicPlaylist.
        if index == parent.getChildrenCount():
            offset = parent.getOffset() + parent.getFileCount()
        else: offset = parent.getChildren()[index].getOffset()
        self.insertElements(contents,offset,copy)
        
    def insertElements(self,elements,offset,copy=True):
        """Insert <elements> into the playlist at the given offset (that is in front of the file with offset <offset>). <elements> may contain containers and files. If <copy> is True, <elements> will be copied deeply which is usually the right thing to do, as the parents of the nodes in <elements> must be adjusted."""
        if offset == -1:
            offset = len(self.pathList)
        
        if copy:
            elements = [element.copy() for element in elements]
        
        # Replace nodes with only one child by the child. This is necessary to be consistent with using the TreeBuilder with createOnlyChildren=False.
        for i in range(0,len(elements)):
            if elements[i].getChildrenCount() == 1:
                elements[i] = elements[i].getChildren()[0]
               
        self._insertElements(self.root,elements,offset)
    
    def _insertElements(self,parent,elements,offset):
        """Insert <elements> into <parent> at the given <offset> (relative to <parent>!)."""
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
        """Try to glue the files at offsets <offset> and <offset-1> and their parent containers. For example if the files have a common parent container, but only the first file is contained in this parent, while the second file does not have any parent in the current tree-structure, then this method will change the tree-structure so that both files are contained in that parent. This is the main method to ensure a nicely organized playlist."""
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
        
        if not prev.isInDB() or not next.isInDB(): # I cannot glue external stuff
            return
        if prev.isFile() and next.isFile(): #TODO: glue should be able to glue two files that have a common parent
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
    
    def _createTreeBuilder(self,items):
        """Create a TreeBuilder to create container-trees over the given list of elements."""
        return treebuilder.TreeBuilder(items,self._getId,self._getParentIds,self._createNode)
    
    def _getId(self,element):
        """Return the id of <element> or None if it is not contained in the DB. This is a helper method for the TreeBuilder-algorithm."""
        if element.isInDB():
            return element.id
        else: return None
        
    def _getParentIds(self,id):
        """Return a list containing the ids of all parents of the given id. This is a helper method for the TreeBuilder-algorithm."""
        return [id for id in db.query("SELECT container_id FROM contents WHERE element_id = ?",id).getSingleColumn()]
               
    def _createNode(self,id,contents):
        """If contents is not empty, create an Container-instance for the given id containing <contents>. Otherwise create an instance of File with the given id. This is a helper method for the TreeBuilder-algorithm."""
        if len(contents) > 0:
            newNode = models.Container(id,contents=contents)
        else: newNode = models.File(id)
        newNode.loadTags()
        return newNode
        
    def _seqLen(self,sequence):
        """Return the length of an item-sequence."""
        return sequence[1] - sequence[0] + 1


class SynchronizablePlaylist(ManagedPlaylist):
    """SynchronizablePlaylist adds the capability to synchronize the playlist with MPD to ManagedPlaylist."""
    # List of all paths of songs in the playlist. Used for fast synchronization with MPD.
    pathList = None
    
    # Currently playing offset and a persistent index to the element
    currentlyPlayingOffset = None
    
    # While _syncLock is True, synchronization with MPD pauses. This is used during complex changes of the model.
    _syncLock = False
    
    def _refreshPathList(self):
        """Recompute the internal pathlist used to synchronize with MPD."""
        self.pathList = [file.getPath() for file in self.root.getAllFiles()]
        
    def startSynchronization(self):
        """Start to synchronize this playlist with MPD."""
        self._refreshPathList()
    
    def stopSynchronization(self):
        """Stop synchronizing this playlist with MPD."""
        self.pathList = None
        self.currentlyPlayingOffset = None
        
    def setRoot(self,root):
        self._syncLock = True
        ManagedPlaylist.setRoot(self,root)
        self._refreshPathList()
        self._syncLock = False
        
    def setContents(self,contents):
        self._syncLock = True
        ManagedPlaylist.setContents(self,contents)
        self._refreshPathList()
        self._syncLock = False
    
    def removeFiles(self,start,end):
        if self._syncLock:
            logger.warning("removeFiles was called while syncLock was True.")
            return
        self._syncLock = True
        if self.pathList is not None:
            del self.pathList[start:end]
            try:
                mpclient.delete(start,end)
            except mpclient.CommandError as e:
                logger.error("Deleting files from MPD's playlist failed: "+e.message)
        ManagedPlaylist.removeFiles(self,start,end)
        self._syncLock = False
        
    def insertElements(self,elements,offset,copy=True):
        if self._syncLock:
            logger.warning("insertElements was called while syncLock was True.")
            return
        self._syncLock = True
        if offset == -1:
            offset = len(self.pathList)
            
        if copy:
            elements = [node.copy() for node in elements]
        
        # Warning: This may change elements by throwing away songs that didn't fit into MPD.
        self._insertFilesToMPD(offset,elements)
        if len(elements) > 0:
            files = (element.getAllFiles() for element in elements)
            self.pathList[offset:offset] = [file.getPath() for file in itertools.chain.from_iterable(files)]
            ManagedPlaylist.insertElements(self,elements,offset,copy=False) # no need to copy again
        self._syncLock = False
    
    def _insertFilesToMPD(self,offset,elements):
        """Insert the files contained in the tree <elements> into MPD at the given offset. If insertion of a certain file fails, the file is removed from <elements> (so this parameter is changed by the method!)"""
        assert offset >= 0
        startOffset = offset
        i = 0
        while i < len(elements):
            element = elements[i]
            if element.isFile():
                if mpclient.insert(offset,element):
                    offset = offset + 1
                    i = i + 1
                else:
                    logger.warning("File '{}' could not be added to MPD. Maybe it is not in MPD's database?"
                                        .format(element.getPath()))
                    del elements[i]
            else:
                offset = offset + self._insertFilesToMPD(offset,element.getChildren())
                i = i + 1
        return offset-startOffset
        
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
            BasicPlaylist.setContents(self,[]) # this will reset the model
        else:
            for tag,i1,i2,j1,j2 in self._getFilteredOpcodes(self.pathList,pathList):
                if tag == 'delete':
                    del self.pathList[i1:i2]
                    ManagedPlaylist.removeFiles(self,i1,i2) # call the super-class implementation since otherwise elements would be removed from the pathlist again.
                    self.glue(self.root,i1)
                elif tag == 'insert':
                    self.pathList[i1:i1] = pathList[j1:j2]
                    ManagedPlaylist.insertElements(self,self.importPaths(pathList[j1:j2]),i1)
                else:
                    # Opcodes are filtered to contain only 'delete' and 'insert'
                    logger.warning("Got an unknown opcode: '{}',{},{},{},{}".format(tag,i1,i2,j1,j2))
            
            # Synchronize currently playing song
            if 'song' not in status:
                if self.currentlyPlayingOffset is not None:
                    self.currentlyPlayingOffset = None
                    try:
                        currentlyPlaying = self.currentlyPlaying()
                        if currentlyPlaying is not None:
                            index = self.getIndex(currentlyPlaying)
                            self.dataChanged.emit(index,index)
                    except ValueError: pass # Probably the element was removed from the playlist
            elif int(status['song']) != self.currentlyPlayingOffset:
                if self.currentlyPlayingOffset is not None:
                    oldElement = self.root.getFileAtOffset(self.currentlyPlayingOffset)
                else: oldElement = None
                self.currentlyPlayingOffset = int(status['song'])
                # Update the new and the old song
                if oldElement is not None:
                    try:
                        index = self.getIndex(oldElement)
                        self.dataChanged.emit(index,index)
                    except ValueError: pass # Probably the element was removed from the playlist
                index = self.getIndex(self.currentlyPlaying())
                self.dataChanged.emit(index,index)
    
    def currentlyPlaying(self):
        """Return the element, which is currently playing."""
        if self.currentlyPlayingOffset is None:
            return None
        else: return self.root.getFileAtOffset(self.currentlyPlayingOffset)
        
    def isPlaying(self,element):
        """Return whether the song <element> is the one which is currently played by MPD."""
        return element.getOffset() == self.currentlyPlayingOffset
