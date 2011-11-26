# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import itertools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import database as db, models, config, utils, logging, modify
from ..modify import events
from ..constants import REAL
from . import rootedtreemodel, treebuilder

logger = logging.getLogger(__name__)
        
class Playlist(rootedtreemodel.RootedTreeModel):
    """Model for Playlists of a player backend."""
    
    def __init__(self, backend):
        """Initialize with an empty playlist."""
        rootedtreemodel.RootedTreeModel.__init__(self,models.RootNode())
        self.backend = backend
        self.current = self.currentModelIndex = None
        self.currentParents = self.currentParentsModelIndices = []
        modify.dispatcher.changes.connect(self.handleChangeEvent)
    
    def setCurrent(self, index):
        if index == -1:
            return
        elem = self.root.fileAtOffset(index)
        assert elem.isFile()
        newCurrent = elem
        parents = []
        parent = newCurrent.parent
        while isinstance(parent, models.Element):
            parents.append(parent)
            parent = parent.parent
        newIndex = self.getIndex(newCurrent)
        if self.currentModelIndex is not None and self.currentModelIndex.isValid():
            self.dataChanged.emit(self.currentModelIndex, self.currentModelIndex)
        if self.currentParents != parents:
            self.currentParents = parents
            oldIndexes = self.currentParentsModelIndices
            self.currentParentsModelIndices = []
            for idx in oldIndexes:
                if idx.isValid():
                    self.dataChanged.emit(idx, idx)
            for parent in parents:
                parentModelIndex = self.getIndex(parent)
                self.currentParentsModelIndices.append(parentModelIndex)
                self.dataChanged.emit(parentModelIndex, parentModelIndex)
        self.current = newCurrent
        self.currentModelIndex = newIndex
        self.dataChanged.emit(newIndex, newIndex)
        
    def _rebuild(self, paths):
        self.beginResetModel()
        elements = []
        for path in paths:
            id = db.idFromPath(path)
            if id is not None:
                elements.append(models.File.fromId(id))
            else:
                elements.append(models.File.fromFilesystem(path))
        elements = self.restructure(elements)
        self.root.setContents(elements)
        self.endResetModel()
    
    def updateFromPathList(self, paths):
        for path,file in itertools.zip_longest(paths, self.root.getAllFiles()):
            if path is None or file is None:
                self._rebuild(paths)
                return
            if path != file.path:
                self._rebuild(paths)
                return 

    def flags(self,index):
        defaultFlags = super().flags(index)
        if index.isValid():
            return defaultFlags | Qt.ItemIsDropEnabled | Qt.ItemIsDragEnabled
        else: return defaultFlags | Qt.ItemIsDropEnabled
    
    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def dropMimeData(self,mimeData,action,row,column,parentIndex):
        if mimeData.hasFormat(config.options.gui.mime):
            fileElems = list(itertools.chain.from_iterable(e.getAllFiles()
                             for e in mimeData.getElements()))
            paths = [f.path for f in fileElems]   
        else:
            paths = list(map(utils.relPath, itertools.chain.from_iterable(
                utils.collectFiles(u.path() for u in mimeData.urls()).values())))
        
        if parentIndex.isValid():
            parent = parentIndex.internalPointer()
        else:
            parent = self.root
        if  row == -1 or row == parent.getContentsCount():
            offset = parent.offset() + parent.fileCount()
        else:
            offset = parent.contents[row].offset()
        
        if action == Qt.MoveAction:
            offsetShift = 0
            removePairs = []
            for file in fileElems:
                fileOffset = file.offset()
                removePairs.append((fileOffset, file.path))
                if fileOffset < offset:
                    offsetShift += 1
            offset -= offsetShift
            self.backend.stack.beginMacro(self.tr("move songs"))
            self.backend.removeFromPlaylist(removePairs)
        self.backend.insertIntoPlaylist(list(enumerate(paths, start = offset)))
        if action == Qt.MoveAction:
            self.backend.stack.endMacro()
        return True
    
    def insertSongs(self,insertions):
        insertions = {i:p for i,p in insertions}
        rngs = utils.ranges(sorted(insertions.keys()))
        for start,end in rngs:
            paths = [insertions[i] for i in range(start, end+1)]
            elements = []
            for i, path in enumerate(paths, start=start):
                id = db.idFromPath(path)
                if id is not None:
                    elements.append(models.File.fromId(id))
                else:
                    elements.append(models.File.fromFilesystem(path))
            self.insertElements(elements, start)
    
    def removeSongs(self, removals):
        removals = {i:p for i,p in removals}
        rngs = utils.ranges(sorted(removals.keys()))
        for start, end in reversed(rngs):
            self._removeFiles(self.root, start, end+1)
            self.glue(self.root, start)
            
    def restructure(self, elements):
        """Restructure the whole container tree in this model. This method does not change the flat
        playlist, but it uses treebuilder to create an optimal container structure over the MPD playlist."""
        treeBuilder = treebuilder.TreeBuilder(elements)
        treeBuilder.buildParentGraph()
        return treeBuilder.buildTree(createOnlyChildren=False)

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
            fileCount = element.contents[i].fileCount()
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
        """Insert <elements> into the playlist at the given offset (that is in front of the file
        with offset <offset>). <elements> may contain containers and files. If <copy> is True,
        <elements> will be copied deeply which is usually the right thing to do, as the
        parents of the nodes in <elements> must be adjusted."""
        if offset == -1:
            offset = len(self.backend.paths)
        
        elements = [element.copy() for element in elements]
        
        # Replace nodes with only one child by the child. This is necessary to be consistent
        #with using the TreeBuilder with createOnlyChildren=False.
        for i in range(0,len(elements)):
            if elements[i].getContentsCount() == 1:
                elements[i] = elements[i].contents[0]
               
        self._insertElements(self.root,elements,offset)
    
    def _insertElements(self,parent,elements,offset):
        """Insert <elements> into <parent> at the given <offset> (relative to <parent>!)."""
        logger.debug("This is _insertElements for parent {} at offset {} and with {} elements."
                        .format(parent,offset,len(elements)))
        fileCount = parent.fileCount()
        if offset == -1:
            offset = fileCount
        
        treeBuilder = treebuilder.TreeBuilder(elements)
        treeBuilder.buildParentGraph()
        treeRoots = treeBuilder.buildTree(createOnlyChildren=False)
        
        parent,insertIndex,insertOffset,split = self._getInsertInfo(treeBuilder,parent,offset)

        if split:
            if self.split(parent,insertOffset):
                insertIndex = insertIndex + 1 # A new node has been created
        
        for root in treeRoots:
            root.parent = parent
            
        self.beginInsertRows(self.getIndex(parent),insertIndex,insertIndex+len(treeRoots)-1)
        parent.contents[insertIndex:insertIndex] = treeRoots
        self.endInsertRows()
        self.glue(parent,insertOffset)
        self.glue(parent,insertOffset+sum(element.fileCount() for element in elements))
        
        # Update the parent since the number of files in it will have changed
        if parent is not self.root:
            parentIndex = self.getIndex(parent)
            self.dataChanged.emit(parentIndex,parentIndex)
    
    def _getInsertInfo(self,treeBuilder,parent,offset):
        if not parent.hasContents():
            return parent,0,0,False
            
        insertIndex,innerOffset = parent.childIndexAtOffset(offset)
        if insertIndex is None: # insertOffset points to the end of parent
            child = parent.contents[-1]
            insertIndex = len(parent.contents)
            innerOffset = child.fileCount()
            split = False
        else:
            child = parent.contents[insertIndex]
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
        fileCount = element.fileCount()
        if offset < 0 or offset > fileCount:
            raise IndexError("Offset {0} is out of bounds.".format(offset))
        if offset == 0 or offset == fileCount:
            return False # Nothing to split here
        
        index,innerOffset = element.childIndexAtOffset(offset)
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
        index,innerOffset = element.childIndexAtOffset(offset)
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
        """Try to glue the files at offsets <offset> and <offset-1> and their parent containers.
        For example if the files have a common parent container, but only the first file
        is contained in this parent, while the second file does not have any parent in the
        current tree structure, then this method will change the tree structure so that both
        files are contained in that parent. This is the main method to ensure a nicely organized
        playlist."""
        logger.debug("This is glue for parent {} at offset {}".format(parent,offset))
        fileCount = parent.fileCount()
        if offset < 0 or offset > fileCount:
            raise IndexError("Offset {} is out of bounds.".format(offset))
        
        if offset == 0 or offset == fileCount:
            return # There is nothing to glue at this positions
        
        prevIndex,prevOffset = parent.childIndexAtOffset(offset-1)
        nextIndex,nextOffset = parent.childIndexAtOffset(offset)
        prev = parent.contents[prevIndex]
        next = parent.contents[nextIndex]
        
        if not prev.isInDB() or not next.isInDB(): # I cannot glue external stuff
            return
        if prev.isFile() and next.isFile(): #TODO: glue should be able to glue two files that have a common parent
            return
            
        if prev is next: # Let next handle this
            self.glue(next,nextOffset)
        elif prev.id == next.id:
            prevFileCount = prev.fileCount()
            self.beginRemoveRows(self.getIndex(parent),nextIndex,nextIndex)
            del parent.contents[nextIndex]
            self.endRemoveRows()
            for element in next.contents:
                element.parent = prev
            self.beginInsertRows(self.getIndex(prev),prev.getContentsCount(),
                                 prev.getContentsCount()+next.getContentsCount()-1)
            prev.contents.extend(next.contents)
            self.endInsertRows()
            self.glue(prev,prevFileCount) # glue just before the files which were just copied
        else:
            prevParents = db.parents(prev.id, True)
            nextParents = db.parents(next.id, True)
            if prev.id in nextParents:
                self.beginRemoveRows(self.getIndex(parent),nextIndex,nextIndex)
                del parent.contents[nextIndex]
                self.endRemoveRows()
                self._insertElements(prev,[next],-1)
            elif next.id in prevParents:
                self.beginRemoveRows(self.getIndex(parent),prevIndex,prevIndex)
                del parent.contents[prevIndex]
                self.endRemoveRows()
                self._insertElements(next,[prev],0)
            else: pass
            # TODO: If prev and next are files with a common parent
            #we should group them into this parent

    def handleElementChangeEvent(self, event):
        pass
    def handleChangeEvent(self, event):
        if isinstance(event, events.ElementChangeEvent):
            if event.level == REAL:
                self.handleElementChangeEvent(event)