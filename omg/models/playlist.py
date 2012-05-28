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
        print("setCurrent {}".format(offset))
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
            if node not in self.currentlyPlayingNodes and self.contains(node):
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
        files = [Wrapper(self.level.get(path)) for path in paths]
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
        
        # Create wrappers
        if mimeData.hasFormat(config.options.gui.mime):
            # Do not simply copy wrappers from other levels as they might be invalid on real level
            if hasattr(mimeData,'level') and mimeData.level is levels.real:
                wrappers = [wrapper.copy() for wrapper in mimeData.getWrappers()]
            else:
                # Note that files might be loaded into the real level via their TID. 
                wrappers = [levels.real.get(id) for id in mimeData.getFiles()]
        else:
            paths = [utils.relPath(path) for path in itertools.chain.from_iterable(
                                    utils.collectFiles(u.path() for u in mimeData.urls()).values())]
                
            #TODO create a shortcut for the following lines (this calls db.idFromPath twice for each element)
            self.level.loadPaths(paths) 
            wrappers = [self.level.get(path) for path in paths]
                
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
    
    def _getPrePostWrappers(self,parent,position):
        """From the subtree below *parent* return the last leaf in parent.contents[:position] and the first
        leaf from parent.contents[position:]. Return None for leaves that do not exist."""
        if position > 0:
            preWrapper = parent.contents[position-1].lastLeaf(allowSelf=True)
        else: preWrapper = None
        if position < len(parent.contents):
            postWrapper = parent.contents[position].firstLeaf(allowSelf=True)
        else: postWrapper = None
        return preWrapper, postWrapper
        
    def insert(self,parent,position,wrappers,fromOutside=False):
        """As in the inherited method, add *wrappers* at *position* into *parent*. But do this in a way
        that preserves a valid and if possible nice tree structure:
        
            - Call the treebuilder to add super containers to wrappers. When inserting into the rootnode
            this just makes nice trees, but otherwise it might be mandatory: When for example a file is
            inserted into a CD-box container the CD-container between has to be added.
            - Split the parent if the treebuilder returns wrappers that are not contained into it (e.g. when
            a file is inserted in the middle of an album to which it does not belong).
            - Glue the inserted wrappers with existing wrappers right before or after the insert position
            (e.g. when inserting a file next to its album container. It will be moved below the album).
             
        """
        assert not parent.isFile()
        origWrappers = wrappers
        application.stack.beginMacro(self.tr("Insert elements"))
        
        # Build a tree
        preWrapper, postWrapper = self._getPrePostWrappers(parent,position)
        wrappers = treebuilder.buildTree(self.level,origWrappers,parent,preWrapper,postWrapper)
        #print("WRAPPERS: {}".format(wrappers))
        
        # Check whether we have to split the parent because some wrappers do not fit into parent
        # It might be necessary to split several parents
        while parent is not self.root:
            if any(w.element.id not in parent.element.contents for w in wrappers):
                self.split(parent,position)
                position = parent.parent.index(parent) + 1
                parent = parent.parent
            else: break
        
        # If parent is the root node, remove toplevel wrappers with only one child from the tree generated
        # by the treebuilder.
        # But do not remove wrappers at the edges that will be glued in the next step
        # (this is also the reason why the treebuilder is allowed to return parents with only one child).
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
                    
        #print("FINAL WRAPPERS: {}".format(wrappers))
        
        # Insert
        command = PlaylistInsertCommand(self,parent,position,wrappers,fromOutside)
        application.stack.push(command)
        
        # Glue add the edges
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
            position = self.root.getContentsCount()
        else:
            parent = file.parent
            position = parent.index(file)
        self.insert(parent,position,wrappers,fromOutside)
        
    def removeByOffset(self,offset,count,fromOutside=False):
        """Remove *count* files beginning at *offset* from the playlist."""
        # TODO: This is very inefficient
        ranges = []
        for offset in range(offset,offset+count):
            file = self.root.fileAtOffset(offset)
            parent = file.parent
            index = parent.index(file)
            ranges.append((parent,index,index))
        self.removeMany(ranges,fromOutside)
        
    def removeMany(self,ranges,fromOutside=False):
        application.stack.beginMacro(self.tr('Remove from playlist'))
        command = PlaylistRemoveCommand(self,ranges,fromOutside)
        application.stack.push(command)
        
        # Process gaps in reversed order to keep indexes below the same parent intact
        for parent,gap in reversed(command.getGaps()):
            self.glue(parent,gap)
        
        application.stack.endMacro()
        
    def merge(self,first,second,firstIntoSecond):
        """If *firstIntoSecond* is True, copy the contents of *first* into *second* (insert them at the
        beginning) and remove *first*. Otherwise do it vice versa but insert at the end.
        *first* and *second* must store the same element and must be adjacent (without having the same
        parent necessarily).
        """
        assert first.element.id == second.element.id
        if firstIntoSecond:
            source,target,insertPos = first,second,0
        else: source,target,insertPos = second,first,len(first.contents)
        wrappers = list(source.contents)
        # See self.split for the reason for changing self.__class__
        self.__class__ = PlaylistModel.__bases__[0]
        self.remove(source,0,len(wrappers)-1)
        pos = source.parent.index(source)
        self.remove(source.parent,pos,pos)
        self.insert(target,insertPos,wrappers)
        self.__class__ = PlaylistModel
        
    def _getParentsUpTo(self,wrapper,parent):
        """Return a tuple containing firstly all ancestors of *wrapper* up to but not including *parent*
        and secondly the ids of those ancestors.""" 
        parents, ids = [],[]
        for p in wrapper.getParents():
            if p != parent:
                parents.append(p)
                ids.append(p.element.id)
            else: break
        return parents,ids
    
    def glue(self,parent,position):
        #print("This is glue for parent {} at {}".format(parent,position))
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
        
    def split(self,parent,position):
        # Call the implementation of the base class but ensure that it uses the base class implementations
        # of insert and remove. Those implementations don't do fancy stuff (e.g. treebuilder) and do not
        # change the backend's playlist (split does not change the flat playlist). 
        self.__class__ = PlaylistModel.__bases__[0]
        self.split(parent,position)
        self.__class__ = PlaylistModel
        return
        
        
class PlaylistInsertCommand(wrappertreemodel.InsertCommand):
    """Subclass of InsertCommand that additionally changes the backend."""
    def __init__(self,model,parent,position,wrappers,fromOutside):
        super().__init__(model,parent,position,wrappers)
        #print("This is a PLaylistInsertCommand for {} {} {} ".format(parent,position,wrappers))
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
        self.model.backend.removeFromPlaylist(offset,offset+self._count)
        super().undo()
        
        
class PlaylistRemoveCommand(wrappertreemodel.RemoveCommand):
    """Subclass of RemoveCommand that additionally changes the backend."""
    def __init__(self,model,ranges,fromOutside):
        #print("this is a PlaylistRemoveCommand for {}".format(','.join(str(range) for range in ranges)))
        assert all(range[2] >= range[1] for range in ranges)
        super().__init__(model,ranges,removeEmptyParents=True)
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
