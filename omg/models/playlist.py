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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt 

from . import wrappertreemodel, treebuilder
from .. import application, config, utils
from ..core import levels
from ..core.nodes import Node, RootNode, Wrapper

 
class PlaylistModel(wrappertreemodel.WrapperTreeModel):
    """Model for Playlists of a player backend."""
    _dontGlueAway = None # See glue and move
    
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
        self._updateCurrentlyPlayingNodes()
    
    def setCurrent(self, offset):
        """Set the currently playing song to the song with the given offset. If offset is None, no song is
        currently playing."""
        print("SETCURRENT({})".format(offset))
        if offset is None:     
            self.clearCurrent() 
        else:
            self.current = self.root.fileAtOffset(offset)
            self._updateCurrentlyPlayingNodes()
        
    def _updateCurrentlyPlayingNodes(self):
        """Update the list of currently playing nodes (that is the current song and all its ancestors).
        Emit appropriate dataChanged-signals."""
        oldPlayingNodes = self.currentlyPlayingNodes

        if self.current is None:
            self.currentlyPlayingNodes = []
        elif not self.contains(self.current):
            self.current = None
            self.currentlyPlayingNodes = []
        else:
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
        files = [Wrapper(element) for element in self.level.getFromPaths(paths)]
        wrappers = treebuilder.buildTree(self.level,files)
        for i in range(len(wrappers)):
            while wrappers[i].getContentsCount() == 1:
                wrappers[i] = wrappers[i].contents[0]
        return wrappers
    
    def initFromPaths(self,paths):
        """Initialize the playlist to contain the given files. This method is not undoable."""
        self._setRootContents(self._buildWrappersFromPaths(paths))
        
    def resetFromPaths(self,paths,updateBackend=True):
        """Reset the playlist to contain the given files. This method is undoable."""
        wrappers = self._buildWrappersFromPaths(paths)
        application.stack.push(PlaylistChangeCommand(self,wrappers,updateBackend))

    def clear(self,updateBackend=True):
        """Clear the playlist."""
        application.stack.push(PlaylistChangeCommand(self,[],updateBackend))
    
               
    def _handleLevelChanged(self,event):
        #TODO
        pass
        
    def dropMimeData(self,mimeData,action,row,column,parentIndex):
        # Compute drop position
        if parentIndex.isValid():
            parent = parentIndex.internalPointer()
        else: parent = self.root
        if row == -1 or row == parent.getContentsCount():
            if parent.isFile(): # Drop onto a file => drop behind it
                position = parent.parent.index(parent) + 1
                parent = parent.parent
            else: position = parent.getContentsCount()
        else: position = row
        
        # Handle internal moves separately
        if self._internalMove:
            return self.move(list(mimeData.wrappers()),parent,position)

        application.stack.beginMacro(self.tr("Drop elements"))
        
        # Create wrappers
        if mimeData.hasFormat(config.options.gui.mime):
            # Do not simply copy wrappers from other levels as they might be invalid on real level
            if hasattr(mimeData,'level') and mimeData.level is levels.real:
                wrappers = [wrapper.copy() for wrapper in mimeData.wrappers()]
            else:
                # Note that files might be loaded into the real level via their TID. 
                wrappers = [levels.real.get(id) for id in mimeData.files()]   
        else:
            paths = [utils.relPath(path) for path in itertools.chain.from_iterable(
                                    utils.collectFiles(u.path() for u in mimeData.urls()).values())]
            wrappers = [Wrapper(element) for element in self.level.getFromPaths(paths)]
               
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
        
    def insert(self,parent,position,wrappers,updateBackend=True):
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
                if position > 0:
                    self.split(parent,position)
                    # Now insert behind the first of the two parent nodes after the split. 
                    position = parent.parent.index(parent) + 1
                else: position = parent.parent.index(parent)
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
        command = PlaylistInsertCommand(self,parent,position,wrappers,updateBackend)
        application.stack.push(command)
        
        # Glue at the edges
        self.glue(parent,position+len(wrappers))
        self.glue(parent,position)
        
        application.stack.endMacro()
        
    def insertPathsAtOffset(self,offset,paths,updateBackend=True):
        """Insert the given paths at the given offset."""
        wrappers = [Wrapper(element) for element in self.level.getFromPaths(paths)]
        file = self.root.fileAtOffset(offset,allowFileCount=True)
        if file is None:
            parent = self.root
            position = self.root.getContentsCount()
        else:
            parent = file.parent
            position = parent.index(file)
        self.insert(parent,position,wrappers,updateBackend)
    
    def move(self,wrappers,parent,position):
        """Move *wrappers* at *position* into *parent*. If the current song is moved, keep the player
        unchanged (contrary to removing and inserting the wrappers again).
        
        Return False if the move is not possible because *parent* or one of its ancestors is in *wrappers*
        and True otherwise.
        """
        # Abort if the drop target or one of its ancestors would be moved
        if any(p in wrappers for p in parent.getParents(includeSelf=True)):
            return False
        
        application.stack.beginMacro(self.tr("Move elements"))
        application.stack.push(ConditionalCommand(onRedo=False,method=self._updateCurrentlyPlayingNodes))
        
        # First change the backend
        # We use a special command to really move songs within the backend (contrary to removing and
        # inserting them). This keeps the status of the current song intact even if it is moved.
        application.stack.push(PlaylistMoveInBackendCommand(self,wrappers,parent,position))
        
        # Remove wrappers.
        # This might change the insert position for several reasons:
        # - we might remove wrappers within parent and before the insert position,
        # - we might remove wrappers making a parent node empty,
        # - after any removal adjacent wrappers may be glued
        # While we could easily calculate a new position taking the first effect into account, this is
        # difficult for the other ones. Therefore we mark the insert position with a special wrapper.
        # We use the super()-methods when we don't want fancy stuff like glueing
        # We use _dontGlueAway to avoid the following problems: Assume the playlist contains the containers
        # A, B, A. If we now move B into one of the A-containers, both A-containers are glued. This might
        # delete our insert parent! Similarly nodes behind the before position might be glued with nodes
        # behind it.
        marker = Wrapper(wrappers[0].element)
        super().insert(parent,position,[marker])
        self._dontGlueAway = [parent,marker]
        self.removeWrappers(wrappers,updateBackend=False)
        position = parent.index(marker)
        super().removeMany([(parent,position,position)])
        self._dontGlueAway = None
        self.insert(parent,position,wrappers,updateBackend=False)
                
        application.stack.push(ConditionalCommand(onRedo=True,method=self._updateCurrentlyPlayingNodes))
        application.stack.endMacro()
        return True
        
    def removeByOffset(self,offset,count,updateBackend=True):
        """Remove *count* files beginning at *offset* from the playlist."""
        # TODO: This is very inefficient
        ranges = []
        for offset in range(offset,offset+count):
            file = self.root.fileAtOffset(offset)
            parent = file.parent
            index = parent.index(file)
            ranges.append((parent,index,index))
        self.removeMany(ranges,updateBackend)
        
    def removeMany(self,ranges,updateBackend=True):
        application.stack.beginMacro(self.tr('Remove from playlist'))
        command = PlaylistRemoveCommand(self,ranges,updateBackend)
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
        """Glue nodes at *position* in *parent*: Look at the files before and after the position and at
        their ancestors up to *parent*. Merge wrappers with the same element. Example: Assume the playlist
        contains an album A with some songs, then a different album B and finally again album A. When B is
        removed and glue is called with position 1, both A-containers will be glued to a single one.
        
        Glue also might glue several layers and works below arbitrary parent nodes (not only the root-node
        as in the example above.
        
        It is unspecified which wrapper will be removed when two wrappers are glued. The list
        self._dontGlueAway may be used to save some nodes from being removed in a glue.
        """
        #print("This is glue for parent {} at {}".format(parent,position))
        if position == 0 or position == parent.getContentsCount():
            return # nothing to glue here
        preWrapper,postWrapper = self._getPrePostWrappers(parent,position)
        assert preWrapper is not None and postWrapper is not None
        preParents,preParentIds = self._getParentsUpTo(preWrapper,parent)
        postParents,postParentIds = self._getParentsUpTo(postWrapper,parent)
        
        while len(postParentIds) and len(preParentIds):
            pos = utils.rfind(postParentIds,preParentIds[-1])
            if pos >= 0 and (self._dontGlueAway is None or preParents[-1] not in self._dontGlueAway):
                self.merge(preParents[-1],postParents[pos],firstIntoSecond=True)
                del preParentIds[-1]
                del preParents[-1]
                del postParentIds[pos:]
                continue
            pos = utils.rfind(preParentIds,postParentIds[-1])
            if pos >= 0 and (self._dontGlueAway is None or postParents[-1] not in self._dontGlueAway):
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
    
    def wrapperString(self):
        """Return a representation of the playlist as wrapperstring (see Node.getWrapperString). External
        files will be stored by their path (and not by their temporary id) so this representation can be
        used to store the playlist tree structure persistently.
        """
        return self.root.wrapperString(strFunc=_strFunc)
    
    def initFromWrapperString(self,wrapperString):
        """Initialize the playlist from a wrapperstring created with PlaylistModel.getWrapperString."""
        wrappers = levels.real.createWrappers(wrapperString,createFunc=_createFunc)
        #TODO: check wrappers for consistency
        self._setRootContents(wrappers)
        
        
class PlaylistInsertCommand(wrappertreemodel.InsertCommand):
    """Subclass of InsertCommand that additionally changes the backend."""
    def __init__(self,model,parent,position,wrappers,updateBackend):
        super().__init__(model,parent,position,wrappers)
        #print("This is a PlaylistInsertCommand for {} {} {} ".format(parent,position,wrappers))
        self._updateBackend = updateBackend
        self._count = sum(w.fileCount() for w in wrappers)
    
    def redo(self):
        super().redo()
        if self._updateBackend:
            offset = self.parent.contents[self.position].offset()
            files = itertools.chain.from_iterable(w.getAllFiles() for w in self.wrappers)
            self.model.backend.insertIntoPlaylist(offset,(f.element.path for f in files))
        else: self._updateBackend = True
        
    def undo(self):
        offset = self.parent.contents[self.position].offset()
        self.model.backend.removeFromPlaylist(offset,offset+self._count)
        super().undo()
        
        
class PlaylistRemoveCommand(wrappertreemodel.RemoveCommand):
    """Subclass of RemoveCommand that additionally changes the backend."""
    def __init__(self,model,ranges,updateBackend):
        #print("this is a PlaylistRemoveCommand for {}".format(','.join(str(range) for range in ranges)))
        assert all(range[2] >= range[1] for range in ranges)
        super().__init__(model,ranges,removeEmptyParents=True)
        self._updateBackend = updateBackend
        self._playlistEntries = None
        
    def redo(self):
        for parent,start,end in reversed(self.ranges):
            if self._updateBackend:
                startOffset = parent.contents[start].offset()
                endOffset = parent.contents[end].offset() + parent.contents[end].fileCount()
                self.model.backend.removeFromPlaylist(startOffset,endOffset)
            self.model._remove(parent,start,end)
        self.model._updateCurrentlyPlayingNodes()
        self._updateBackend = True
            
    def undo(self):
        for parent,pos,wrappers in self.insertions:
            self.model._insert(parent,pos,wrappers)
            offset = parent.contents[pos].offset()
            files = itertools.chain.from_iterable(w.getAllFiles() for w in wrappers)
            self.model.backend.insertIntoPlaylist(offset,(f.element.path for f in files))


class PlaylistChangeCommand(wrappertreemodel.ChangeCommand):
    """Subclass of ChangeCommand that additionally changes the backend."""
    def __init__(self,model,newContents,updateBackend):
        super().__init__(model,newContents)
        self._updateBackend = updateBackend
        
    def redo(self):
        super().redo()
        if self._updateBackend:
            paths = list(f.element.path for f in self.model.root.getAllFiles())
            self.model.backend.setPlaylist(paths)
        else: self._updateBackend = True
        self.model._updateCurrentlyPlayingNodes()
        
    def undo(self):
        super().undo()
        paths = list(f.element.path for f in self.model.root.getAllFiles())
        self.model.backend.setPlaylist(paths)
        

class PlaylistMoveInBackendCommand(QtGui.QUndoCommand):
    """This command moves songs in the backend. It does not change the PlaylistModel. It will assume that
    *wrappers* should be inserted at *position* into *parent*. Based on this a series of moves (i.e. calls
    of Player.move is computed, that updates the backend accordingly."""
    def __init__(self,model,wrappers,parent,position):
        super().__init__()
        self.model = model
        self.moves = []
        insertOffset = parent.offset() + sum(w.fileCount() for w in parent.contents[:position])
        
        # Compute a series of moves that will move 
        # Since we do not really move files yet, we have to correct positions:
        # - Whenever we move a file before the insert position, the index of all such files decreases by 1.
        #   Note that the insert position remains unchanged.
        # - Whenever we move a file after (or at) the insert position, the insert position increases by 1.
        # The first correction is stored in i, the second one in j
        i,j = 0,0
        for file in itertools.chain.from_iterable(w.getAllFiles() for w in wrappers):
            fileOffset = file.offset()
            if fileOffset < insertOffset:
                # The second entry of a move-tuple stores the offset which the element will have after the
                # move. For elements before the insert position this is insertOffset-1:
                self.moves.append((fileOffset-i,insertOffset-1))
                i += 1
            else:
                if fileOffset > insertOffset: # Don't move a file that is already at the correct position
                    self.moves.append((fileOffset,insertOffset+j))
                j += 1
        
    def redo(self):
        for move in self.moves:
            self.model.backend.move(*move)
            
    def undo(self):
        for move in reversed(self.moves):
            self.model.backend.move(move[1],move[0])
            

class ConditionalCommand(QtGui.QUndoCommand):
    """This UndoCommand executes *method* only on redo or only on undo, depending on *onRedo*. This can be
    used to create a macro that calls *method* after all commands, irrespective of the direction. Usually
    *method* will update something based on the changes done in the macro.
    """
    def __init__(self,onRedo,method):
        super().__init__()
        self.onRedo = onRedo
        self.method = method
        
    def redo(self):
        if self.onRedo:
            self.method()
            
    def undo(self):
        if not self.onRedo:
            self.method()


# Helper functions for playlist<->wrapperstring conversion
def _createFunc(parent,token):
    """This is used as createFunc-argument for Level.createWrappers."""
    if token.startswith('EXT:'):
        path = urllib.parse.unquote(token[4:]) # remove EXT:
        element = levels.real.get(path)
    else:
        element = levels.real.get(int(token))
    return Wrapper(element,parent=parent)
        
def _strFunc(wrapper):
    """This is used as strFunc-argument for Node.wrapperString. It returns external files as url-encoded
    paths because these don't contain the characters ',[]'."""
    if wrapper.element.id > 0:
        return str(wrapper.element.id)
    else:
        # only exception are external files in the playlist
        assert wrapper.isFile()
        return 'EXT:'+urllib.parse.quote(wrapper.element.path)
    