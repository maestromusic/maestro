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

from .. import database as db, models, config, utils, logging, modify, models
from . import rootedtreemodel, treebuilder, levels

logger = logging.getLogger(__name__)
translate = QtCore.QCoreApplication.translate


class WrapperTreeModel(rootedtreemodel.RootedTreeModel):
    """A WrapperTreeModel is a general model for trees consisting mainly of wrappers. It provides undoable
    methods to modify the tree structure and drag and drop support that allows the user to modify the tree
    arbitrarily (the only rule is that contents must not be inserted into a file. They will be placed behind
    it instead).
    
    Usually the main undostack is used, but you can specify a different stack using the argument *stack*.
    """
    def __init__(self,level=None,stack=None):
        super().__init__(level,models.RootNode(self))
        if stack is None:
            self.stack = modify.stack
        else: self.stack = stack
        
    def _setRootContents(self,wrappers):
        """Resets the model to contain the given wrappers.""" 
        self.beginResetModel()
        self.root.setContents(wrappers)
        self.endResetModel()
        
    def _insert(self,parent,position,wrappers):
        """Insert *wrappers* at the given position into the wrapper *parent*. This method does not care
        about undo, so usually you want to use insert.""" 
        self.beginInsertRows(self.getIndex(parent),position,position + len(wrappers) - 1)
        parent.insertContents(position,wrappers)
        self.endInsertRows()
        
    def _remove(self,parent,start,end):
        """Remove contents from the wrapper *parent*. *start* and *end* are the first and last index that
        is removed, respectively. This method does not care about undo, so usually you want to use one
        of the remove* methods.
        """ 
        self.beginRemoveRows(self.getIndex(parent),start,end)
        del parent.contents[start:end+1]
        self.endRemoveRows()
    
    def insert(self,parent,position,wrappers):
        """Insert *wrappers* at the given position into the wrapper *parent*.""" 
        command = InsertCommand(self,parent,position,wrappers)
        self.stack.push(command)
    
    def removeWrappers(self,wrappers):
        """Remove the given wrappers from the model. When possible its usually faster to use the range-based
        methods remove or removeMany."""
        # TODO: Maybe detect adjacent wrappers here and create a single range for them. This is not really
        # necessary as RemoveCommand will merge adjacent ranges. 
        ranges = []
        for wrapper in wrappers:
            parent = wrapper.parent
            index = parent.index(wrapper)
            ranges.append((parent,index,index))
        self.removeMany(ranges)
    
    def remove(self,parent,first,last):
        """Remove contents from the wrapper *parent*. *start* and *end* are the first and last index that
        is removed, respectively."""
        self.removeMany([(parent,first,last)])
        
    def removeMany(self,ranges):   
        """Remove arbitrary wrappers from the model. *ranges* is a list of tuples consisting of a parent,
        whose contents should be modified and the first and last index that should be removed (confer the
        arguments of remove). So at first glance removeMany is equivalent
            
            for range in ranges:
                self.remove(*range)
                
        But in fact removeMany does some magic so that you can safely call it with any ranges (see
        RemoveCommand).
        """
        command = RemoveCommand(self,ranges)
        self.stack.push(command)
        
    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def flags(self,index):
        defaultFlags = super().flags(index)
        if index.isValid():
            return defaultFlags | Qt.ItemIsDropEnabled | Qt.ItemIsDragEnabled
        else: return defaultFlags | Qt.ItemIsDropEnabled
        
    def dropMimeData(self,mimeData,action,row,column,parentIndex):
        if mimeData.hasFormat(config.options.gui.mime):
            wrappers = [wrapper.copy() for wrapper in mimeData.getWrappers()]
        else:
            paths = [utils.relPath(path) for path in utils.collectFiles(u.path()
                                                                    for u in mimeData.urls()).values()]
                
            #TODO create a shortcut for the following lines (this calls db.idFromPath twice for each element)
            levels.real.loadPaths(paths) 
            wrappers = [models.Wrapper(levels.real.get(path)) for path in paths]
        
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
    
    
        self.insert(parent,position,wrappers)
        return True
    
    # Necessary for Qt so that Drag&Drow moves work 
    def removeRows(self,row,count,parent):
        self.remove(self.data(parent),row,row+count-1)
        return True
    
    def split(self,parent,position):
        """Split the wrapper *parent* at the given position, i.e. insert a copy of *parent* directly behind
        *parent* and move parent.contents[position:] to the copy.
        
        If *position* is 0 or equal to the number of contents of *parent*, do nothing.
        """
        assert parent != self.root
        if position == 0 or position == len(parent.contents):
            return # nothing to split here
        elif position < 0 or position > len(parent.contents):
            raise ValueError("Position {} is out of bounds".format(position))
        
        self.stack.beginMacro(self.tr("Split node"))
        # Insert a copy of parent directly after parent
        copy = parent.copy(contents=[])
        self.insert(parent.parent,parent.parent.index(parent)+1,[copy])
        movingWrappers = parent.contents[position:]
        self.remove(parent,position,len(parent.contents)-1)
        self.insert(copy,0,movingWrappers)
        self.stack.endMacro()
                        

class InsertCommand(QtGui.QUndoCommand):
    """UndoCommand that inserts the given list of wrappers at the index *position* into the wrapper *parent*.
    *model* is the WrapperTreeModel containing *parent*.
    """
    def __init__(self,model,parent,position,wrappers):
        super().__init__(translate("WrapperTreeModel","Insert contents"))
        self.model = model
        self.parent = parent
        self.position = position
        self.wrappers = wrappers
    
    def redo(self):
        self.model._insert(self.parent,self.position,self.wrappers)
        
    def undo(self):
        self.model._remove(self.parent,self.position,self.position+len(self.wrappers)-1)
        
      
class RemoveCommand(QtGui.QUndoCommand):
    """UndoCommand that removes arbitrary nodes from *model*. *rangeList* is a list of 3-tuples, each
    specifying a range of nodes with a common parent that should be removed. To be precise, each tuple
    consist of
    
        - the parent (a wrapper in *model*)
        - the first index of parent.contents that should be removed
        - the last index of parent.contents that should be removed
    
    RemoveCommand will deal with all nasty things that might break undo/redo so you can safely give it
    any list of ranges (ok, parent must be in *model* and indexes must not be out of bounds). In particular
    
        - overlapping or adjacent ranges will be merged,
        - redundant ranges will be ignored (a range is redundant if its parent will be removed due to some
          range)
        - ranges will be sorted in a way such that removing a range doesn't make the indexes of the others
          invalid.
    
    Contrary to InsertCommand, we allow removal of many wrappers in one step because this is
    possible without ambiguity and needed for "Remove selected" (Qt stores the selection in ranges).
    """
    def __init__(self,model,rangeList):
        super().__init__(translate("WrapperTreeModel","Remove contents"))
        self.model = model
        
        # Make dict mapping parent to list of ranges with this parent
        rangeDict = {}
        for range in rangeList:
            parent = range[0]
            if parent not in rangeDict:
                rangeDict[parent] = [range]
            else: rangeDict[parent].append(range)
            
        # Sort ranges below each parent by start index
        # Merge ranges (in particular remove overlapping ranges)
        for parent,ranges in rangeDict.items():
            ranges.sort(key=lambda range: range[1])
            
            currentIndex = 0
            i = 1
            while i < len(ranges):
                # If the start point of the next range is inside the current range or directly after the 
                # current range...
                current = ranges[currentIndex]
                next = ranges[i]
                if next[1] <= current[2] + 1:
                    # ...then expand the current range to the union of both and remove the next range
                    # equivalent to current[2] = next[2], but works with tuples
                    ranges[currentIndex] = (current[0],current[1],next[2])
                    del ranges[i]
                else:
                    # ...otherwise set current to the next range 
                    currentIndex = i
                    i += 1
        
        # Remove redundant parents (those that will be removed completely due to some range in an ancestor)
        # parents that will be removed will first be marked by a None entry (don't remove dict entries
        # while iterating over the dict). This is also used as a shortcut to detect ancestors that will be
        # removed anyway.
        for parent in rangeDict:
            for ancestor,index in self._ancestorGenerator(parent):
                if ancestor in rangeDict:
                    if (rangeDict[ancestor] is None  # we already marked the parent
                         or any(range[1] <= index <= range[2] for range in rangeDict[ancestor])):
                        rangeDict[parent] = None # mark the parent to be removed
                        break
        
        # Finally concat the different lists to a single list of ranges removing those that have been marked
        self.ranges = list(itertools.chain.from_iterable(
                                            ranges for ranges in rangeDict.values() if ranges is not None))
        
        self.insertions = [(parent,start,parent.contents[start:end+1]) for parent,start,end in self.ranges]
                    
    def _ancestorGenerator(self,node):
        """Return a generator which, going up the line of ancestors of *node* yields each ancestor together
        with the index of the last ancestor within the current ancestor's contents.""" 
        while node is not self.model.root:
            parent = node.parent
            yield parent,parent.index(node)
            node = parent
            
    def redo(self):
        # Removing ranges in reversed order guarantees that ranges below the same parent are removed
        # from bottom to top, keeping indexes valid. The order of the parents does not matter.
        for parent,start,end in reversed(self.ranges):
            self.model._remove(parent,start,end)
            
    def undo(self):
        for parent,position,wrappers in self.insertions:
            self.model._insert(parent,position,wrappers)
            
            
class ChangeCommand(QtGui.QUndoCommand):
    """UndoCommand to replace the complete contents of a WrapperTreeModel by *newContents*."""
    def __init__(self,model,newContents):
        super().__init__(translate("WrapperTreeModel","Change tree"))
        self.model = model
        self.before = model.root.contents
        self.after = newContents
        
    def redo(self):
        self.model._setRootContents(self.after)
        
    def undo(self):
        self.model._setRootContents(self.before)
        