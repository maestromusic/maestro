# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

from . import wrappertreemodel, treebuilder
from .. import application, config, utils
from ..core import levels
from ..core.nodes import RootNode, Wrapper

            
class PlaylistModel(wrappertreemodel.WrapperTreeModel):
    """Model for Playlists of a player backend."""

    def __init__(self,backend=None,level=None):
        """Initialize with an empty playlist."""
        super().__init__(level if level is not None else levels.real)

        self.backend = backend
        self.current = None
         # self.current and all of its parents. The delegate draws an arrow in front of these nodes
        self.currentlyPlayingNodes = []
        self.level.changed.connect(self._handleLevelChanged)
    
    def clearCurrent(self):
        """Unsets the current song and clears the currentlyPlayingNodes list."""
        self.current = None
        for node in self.currentlyPlayingNodes:
            index = self.getIndex(node)
            self.dataChanged.emit(index,index)
        self.currentlyPlayingNodes = []
    
    def setCurrent(self, offset):
        """Set the currently playing song to the song with the given offset. If offset is negative, no song
        is currenlty playing."""
        if offset < 0:       
            self.clearCurrent() 
            return
               
        oldPlayingNodes = self.currentlyPlayingNodes
        
        # Update data in the model
        self.current = self.root.fileAtOffset(offset)
        self.currentlyPlayingNodes = [self.current]
        parent = self.current.parent
        while not isinstance(parent, RootNode):
            self.currentlyPlayingNodes.append(parent)
            parent = parent.parent
        
        # Emit events for nodes whose state changed
        for node in oldPlayingNodes:
            if node not in self.currentlyPlayingNodes:
                index = self.getIndex(node)
                self.dataChanged.emit(index,index)
                
        for node in self.currentlyPlayingNodes:
            if node not in oldPlayingNodes:
                index = self.getIndex(node)
                self.dataChanged.emit(index,index)

    def _buildWrappersFromPaths(self,paths):
        """Build wrappers for the given paths and if possible add containers. In other words: convert a flat
        playlist to a tree playlist."""
        levels.real.loadPaths(paths)
        files = [self.level.get(path) for path in paths]
        return treebuilder.buildTree(self.level,files)
    
    def initFromPaths(self,paths):
        """Initialize the playlist to contain the given files. This method is not undoable."""
        self._setRootContents(self._buildWrappersFromPaths(paths))
        
    def resetFromPaths(self,paths,fromOutside=False):
        """Reset the playlist to contain the given files. This method is undoable."""
        wrappers = self._buildWrappersFromPaths(paths)
        application.stack.push(PlaylistChangeCommand(self,self.root.contents,wrappers,fromOutside))

    def clear(self,fromOutside=False):
        """Clear the playlist."""
        application.stack.push(PlaylistChangeCommand(self,[],fromOutside))
    
    def _getPrePostWrappers(self,parent,position):
        if position > 0:
            preWrapper = parent.contents[position-1].lastLeaf(allowSelf=True)
        else: preWrapper = None
        if position < len(parent.contents):
            postWrapper = parent.contents[position].firstLeaf(allowSelf=True)
        else: postWrapper = None
        return preWrapper, postWrapper
        
    def insert(self,parent,position,origWrappers,fromOutside=False):
        assert not parent.isFile()
        application.stack.beginMacro(self.tr("Insert elements"))
            
        preWrapper, postWrapper = self._getPrePostWrappers(parent,position)
        wrappers = treebuilder.buildTree(self.level,origWrappers,parent,preWrapper,postWrapper)
        print("WRAPPERS: {}".format(wrappers))
        
        # Check whether we have to split the parent because some nodes do not fit into parent
        while parent is not self.root:
            if any(w.element.id not in parent.element.contents for w in wrappers):
                self.split(parent,position)
                position = parent.parent.index(parent) + 1
                parent = parent.parent
            else: break
        
        # If parent is the root node, remove toplevel wrappers with only one child from the tree generated
        # by the treebuilder. But do not remove wrappers at the edges that will be glued in the next step
        # (this is also the reason why the treebuilder may return parents with only one child).
        # Also do not remove wrappers originally inserted by the user even if they are single parents.
        if parent is self.root:
            # We will remove single parents from wrappers[startPos:endPos] 
            startPos, endPos = 0, len(wrappers)
            if position > 0:
                preSibling = parent.contents[position-1]
                if preSibling.element.id == wrappers[0].element.id:
                    # First wrapper will be glued with preSibling => keep its parents
                    startPos += 1
            if position < len(parent.contents):
                postSibling = parent.contents[position]
                if postSibling.element.id == wrappers[-1].element.id:
                    # Last wrapper will be glued with postSibling => keep its parents
                    endPos -= 1
            for i in range(startPos,endPos):
                while wrappers[i].getContentsCount() == 1 and wrappers[i] not in origWrappers:
                    wrappers[i] = wrappers[i].contents[0]
                    
        print("FINAL WRAPPERS: {}".format(wrappers))
            
        command = PlaylistInsertCommand(self,parent,position,wrappers,fromOutside)
        application.stack.push(command)
        
        self.glue(parent,position+len(wrappers))
        self.glue(parent,position)
        application.stack.endMacro()
        
    def insertPathsAtOffset(self,offset,paths,fromOutside=False):
        """Insert the given paths at the given offset."""
        self.level.loadPaths(paths)
        wrappers = [Wrapper(self.level.get(path)) for path in paths]
        file = self.root.fileAtOffset(offset,allowFileCount=True)
        if file is None:
            parent = self.root
            index = self.root.getContentsCount()
        else:
            parent = file.parent
            index = parent.index(file)
        application.stack.push(PlaylistInsertCommand(self,parent,index,wrappers,fromOutside))
        #TODO: glue?
        
    def remove(self,parent,first,last):
        raise NotImplementedError()

    def removeByOffset(self,offset,count,fromOutside=False):
        """Remove *count* files beginning at *offset* from the playlist."""
        # TODO: This is very inefficient
        ranges = []
        for offset in range(offset,offset+count):
            file = self.root.fileAtOffset(offset)
            parent = file.parent
            index = parent.index(file)
            ranges.append((parent,index,index))
        application.stack.push(PlaylistRemoveCommand(self,ranges,fromOutside))
        
    def removeMany(self,ranges,fromOutside=False):
        command = PlaylistRemoveCommand(self,ranges,fromOutside)
        application.stack.push(command)
        #TODO glue
               
    def _handleLevelChanged(self,event):
        #TODO
        pass
    
    def dropMimeData(self,mimeData,action,row,column,parentIndex):
        # Compute drop position
        if parentIndex.isValid():
            parent = parentIndex.internalPointer()
        else: parent = self.root
        if row == -1 or row == parent.getContentsCount():
            if parent.isFile(): # Drop onto a file
                position = parent.parent.index(parent) + 1
                parent = parent.parent
            else: position = parent.getContentsCount()
        else: position = row
        
        if mimeData.hasFormat(config.options.gui.mime):
            wrappers = [wrapper.copy() for wrapper in mimeData.getWrappers()]
        else:
            paths = [utils.relPath(path) for path in itertools.chain.from_iterable(
                                    utils.collectFiles(u.path() for u in mimeData.urls()).values())]
                
            #TODO create a shortcut for the following lines (this calls db.idFromPath twice for each element)
            self.level.loadPaths(paths) 
            files = [self.level.get(path) for path in paths]
            
            preWrapper,postWrapper = self._getPrePostWrappers(parent,position)
            wrappers = treebuilder.buildTree(self.level,files,preWrapper,postWrapper)
                
        #TODO: handle move actions
#         if action == Qt.MoveAction:
#            offsetShift = 0
#            removePairs = []
#            for file in fileElems:
#                fileOffset = file.offset()
#                removePairs.append((fileOffset, file.path))
#                if fileOffset < offset:
#                    offsetShift += 1
#            offset -= offsetShift
#            self.backend.stack.beginMacro(self.tr("move songs"))
#            self.backend.removeFromPlaylist(removePairs)
#       self.backend.insertIntoPlaylist(list(enumerate(paths, start = offset)))
#      if action == Qt.MoveAction:
#           self.backend.stack.endMacro()
#       return True
    
        application.stack.beginMacro(self.tr("Drop elements"))
        self.insert(parent,position,wrappers)
        application.stack.endMacro()
        return True
    
    def merge(self,first,second,firstIntoSecond):
        print("MERGE: {} {} {} ".format(first,second,firstIntoSecond))
        assert first.element.id == second.element.id
        if firstIntoSecond:
            source,target,insertPos = first,second,0
        else: source,target,insertPos = second,first,len(first.contents)
        wrappers = list(source.contents)
        super().removeMany([(source,0,len(wrappers)-1)])
        pos = source.parent.index(source)
        super().removeMany([(source.parent,pos,pos)])
        super().insert(target,insertPos,wrappers)
        
    def _getParentsUpTo(self,wrapper,parent):
        parents, ids = [],[]
        for p in wrapper.getParents():
            if p != parent:
                parents.append(p)
                ids.append(p.element.id)
            else: break
        return parents,ids
    
    def glue(self,parent,position):
        print("This is glue for parent {} at {}".format(parent,position))
        if position == 0 or position == parent.getContentsCount():
            return # nothing to glue here
        preWrapper,postWrapper = self._getPrePostWrappers(parent,position)
        assert preWrapper is not None and postWrapper is not None
        preParents,preParentIds = self._getParentsUpTo(preWrapper,parent)
        postParents,postParentIds = self._getParentsUpTo(postWrapper,parent)
        
        while len(postParentIds) and len(preParentIds):
            pos = utils.rfind(postParentIds,preParentIds[-1])
            if pos >= 0:
                self.merge(preParents[-1],postParents[pos],firstIntoSecond=True)
                del preParentIds[-1]
                del preParents[-1]
                del postParentIds[pos:]
                continue
            pos = utils.rfind(preParentIds,postParentIds[-1])
            if pos >= 0:
                self.merge(preParents[pos],postParents[-1],firstIntoSecond=False)
                del preParentIds[pos:]
                del postParentIds[-1]
                del postParents[-1]
                continue
            break # no glue possible
    
#TODO: remove
#        first = parent.contents[position-1]
#        second = parent.contents[position]
#        if first.element.id == second.element.id:
#            priorLength = first.getContentsCount()
#            wrappers = list(second.contents)
#            # Of course the second line would be sufficient to remove the wrappers.
#            # But on undo the parent pointers of the wrappers wouldn't be corrected.
#            super().remove(second,0,len(wrappers)-1)
#            super().remove(parent,position,position)
#            super().insert(first,priorLength,wrappers)
#            # Glue recursively
#            self.glue(first,priorLength)
        
    def split(self,parent,position):
        """Split the wrapper *parent* at the given position, i.e. insert a copy of *parent* directly behind
        *parent* and move parent.contents[position:] to the copy.
        
        If *position* is 0 or equal to the number of contents of *parent*, do nothing.
        """
        assert parent is not self.root
        if position == 0 or position == len(parent.contents):
            return # nothing to split here
        elif position < 0 or position > len(parent.contents):
            raise ValueError("Position {} is out of bounds".format(position))
        print("SPLIT {} {} ".format(parent,position))
        application.stack.beginMacro(self.tr("Split node"))
        # Insert a copy of parent directly after parent
        copy = parent.copy(contents=[])
        super().insert(parent.parent,parent.parent.index(parent)+1,[copy])
        movingWrappers = parent.contents[position:]
        super().removeMany([(parent,position,len(parent.contents)-1)])
        super().insert(copy,0,movingWrappers)
        application.stack.endMacro()
        
        
class PlaylistInsertCommand(wrappertreemodel.InsertCommand):
    """Subclass of InsertCommand that additionally changes the backend."""
    def __init__(self,model,parent,position,wrappers,fromOutside):
        super().__init__(model,parent,position,wrappers)
        self._dontUpdatePlayer = fromOutside
        self._count = sum(w.fileCount() for w in wrappers)
    
    def redo(self):
        super().redo()
        
        if not self._dontUpdatePlayer:
            offset = self.parent.contents[self.position].offset()
            files = itertools.chain.from_iterable(w.getAllFiles() for w in self.wrappers)
            self.model.backend.insertIntoPlaylist(offset,(f.element.path for f in files))
        else: self._dontUpdatePlayer = False
        
    def undo(self):
        offset = self.parent.contents[self.position].offset()
        self.model.backend.removeFromPlaylist(offset,self._count)
        super().undo()
        
        
class PlaylistRemoveCommand(wrappertreemodel.RemoveCommand):
    """Subclass of RemoveCommand that additionally changes the backend."""
    def __init__(self,model,ranges,fromOutside):
        print("this is a PlaylistRemoveCommand for {}".format(','.join(str(range) for range in ranges)))
        assert all(range[2] >= range[1] for range in ranges)
        super().__init__(model,ranges)
        self._dontUpdatePlayer = fromOutside
        self._playlistEntries = None
        
    def redo(self):
        for parent,start,end in reversed(self.ranges):
            if not self._dontUpdatePlayer:
                startOffset = parent.contents[start].offset()
                endOffset = parent.contents[end].offset() + parent.contents[end].fileCount()
                self.model.backend.removeFromPlaylist(startOffset,endOffset)
            self.model._remove(parent,start,end)
        self._dontUpdatePlayer = False
            
    def undo(self):
        for parent,pos,wrappers in self.insertions:
            self.model._insert(parent,pos,wrappers)
            offset = parent.contents[pos].offset()
            files = itertools.chain.from_iterable(w.getAllFiles() for w in wrappers)
            self.model.backend.insertIntoPlaylist(offset,(f.element.path for f in files))


class PlaylistChangeCommand(wrappertreemodel.ChangeCommand):
    """Subclass of ChangeCommand that additionally changes the backend."""
    def __init__(self,model,newContents,fromOutside):
        super().__init__(model,newContents)
        self._dontUpdatePlayer = fromOutside
        
    def redo(self):
        super().redo()
        if not self._dontUpdatePlayer:
            paths = list(f.element.path for f in self.model.root.getAllFiles())
            self.model.backend.setPlaylist(paths)
        else: self._dontUpdatePlayer = False
        
    def undo(self):
        super().undo()
        paths = list(f.element.path for f in self.model.root.getAllFiles())
        self.model.backend.setPlaylist(paths)
