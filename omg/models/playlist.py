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

    def __init__(self, backend=None):
        """Initialize with an empty playlist."""
        super().__init__(levels.real)

        self.backend = backend
        self.current = None
         # self.current and all of its parents. The delegate draws an arrow in front of these nodes
        self.currentlyPlayingNodes = []
        levels.real.changed.connect(self._handleLevelChanged)
    
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
        wrappers = [Wrapper(levels.real.get(path)) for path in paths]
        treeBuilder = treebuilder.TreeBuilder(wrappers)
        treeBuilder.buildParentGraph()
        return treeBuilder.buildTree(createOnlyChildren=False)
    
    def initFromPaths(self,paths):
        """Initialize the playlist to contain the given files. This method is not undoable."""
        self._setRootContents(self._buildWrappersFromPaths(paths))
        
    def resetFromPaths(self,paths,fromOutside=False):
        """Reset the playlist to contain the given files. This method is undoable."""
        wrappers = self._buildWrappersFromPaths(paths)
        application.stack.push(PlaylistChangeCommand(self,self.root.contents,wrappers,fromOutside))

    def clear(self,fromOutside=False):
        """Clear the playlist."""
        application.stack.push(ChangePlaylistCommand(self,self.root.contents,[]))
        
    def insert(self,parent,position,wrappers,fromOutside=False):
        assert not parent.isFile()
        application.stack.beginMacro(self.tr("Insert elements"))
        while parent is not self.root:
            #TODO handle special case that all nodes are descendants of parent but some are no children
            if any(w.element.id not in parent.element.contents for w in wrappers):
                self.split(parent,position)
                position = parent.parent.index(parent) + 1
                parent = parent.parent
            else: break
        
        command = PlaylistInsertCommand(self,parent,position,wrappers,fromOutside)
        application.stack.push(command)
        
        application.stack.endMacro()
        
    def insertPathsAtOffset(self,offset,paths,fromOutside=False):
        """Insert the given paths at the given offset."""
        levels.real.loadPaths(paths)
        wrappers = [Wrapper(levels.real.get(path)) for path in paths]
        file = self.root.fileAtOffset(offset,allowFileCount=True)
        if file is None:
            parent = self.root
            index = self.root.getContentsCount()
        else:
            parent = file.parent
            index = parent.index(file)
        application.stack.push(PlaylistInsertCommand(self,parent,index,wrappers,fromOutside))
    
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
