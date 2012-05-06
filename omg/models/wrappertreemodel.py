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
from ..modify import treeactions
from . import rootedtreemodel, treebuilder, levels, ContentList, Wrapper

logger = logging.getLogger(__name__)
translate = QtCore.QCoreApplication.translate


class WrapperTreeModel(rootedtreemodel.RootedTreeModel):
    """A WrapperTreeModel is a general model for trees consisting mainly of wrappers. It provides undoable
    methods to modify the tree structure and drag and drop support that allows the user to modify the tree
    arbitrarily (the only rule is that contents must not be inserted into a file. They will be placed behind
    it instead).
    
    Usually the main undostack is used, but you can specify a different stack using the argument *stack*.
    """
    def __init__(self,level = None, root = None, stack = None):
        super().__init__(models.RootNode(self) if root is None else root)
        if stack is None:
            self.stack = modify.stack
        else: self.stack = stack
        self.level = level
        if level is not None:
            level.changed.connect(self._handleLevelChanged)
        
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
                        
    def changeContents(self, index, new):
        parent = self.data(index, Qt.EditRole)
        old = [ node.element.id for node in parent.contents ]
        if isinstance(new, ContentList):
            newP = new.positions
            new = new.ids
        else:
            newP = None
        i = 0
        while i < len(new):
            id = new[i]
            try:
                existingIndex = old.index(id)
                if existingIndex > 0:
                    self.removeContents(index, i, i + existingIndex - 1)
                del old[:existingIndex+1]
                if newP and newP[i] != parent.contents[i].position:
                    parent.contents[i].position = newP[i]
                    index = self.getIndex(parent.contents[i])
                    self.dataChanged.emit(index, index)
                i += 1
            except ValueError:
                insertStart = i
                insertNum = 1
                i += 1
                while id not in old and i < len(new):
                    id = new[i]
                    insertNum += 1
                    i += 1
                self.insertContents(index, insertStart, new[insertStart:insertStart+insertNum],
                                    newP[insertStart:insertStart+insertNum] if newP else None)
        if len(old) > 0:
            self.removeContents(index, i, i + len(old) - 1)
    
    def removeContents(self, index, first, last):
        self.beginRemoveRows(index, first, last)
        del self.data(index, Qt.EditRole).contents[first:last+1]
        self.endRemoveRows()
        
    def insertContents(self, index, position, ids, positions = None):
        self.beginInsertRows(index, position, position + len(ids) - 1)
        wrappers = [Wrapper(self.level.get(id)) for id in ids]
        if positions:
            for pos, wrap in zip(positions, wrappers):
                wrap.position = pos
        for wrapper in wrappers:
            wrapper.loadContents(recursive = True)
        self.data(index, Qt.EditRole).insertContents(position, wrappers) 
        self.endInsertRows()
        
    def _handleLevelChanged(self, event):
        dataIds = event.dataIds
        contentIds = event.contentIds
        for node, contents in utils.walk(self.root):
            if isinstance(node, Wrapper):
                if node.element.id in dataIds:
                    self.dataChanged.emit(self.getIndex(node), self.getIndex(node))
                if node.element.id in contentIds:
                    self.changeContents(self.getIndex(node), self.level.get(node.element.id).contents)
                    contents[:] = [wrapper for wrapper in contents if wrapper in node.contents ]
                    
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
            

class ChangeRootCommand(QtGui.QUndoCommand):
    def __init__(self, model, old, new, text = "<change root>"):
        super().__init__()
        self.model = model
        self.old = old
        self.new = new
        self.setText(text)
        
    def redo(self):
        logger.debug("change root: {} --> {}".format(self.old, self.new))
        self.model.changeContents(QtCore.QModelIndex(), self.new )
        
    def undo(self):
        logger.debug("change root: {} --> {}".format(self.new, self.old))
        self.model.changeContents(QtCore.QModelIndex(), self.old )
        
             
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



class MergeCommand(QtGui.QUndoCommand):
    """Merge creates a new container between *parent* and the children at the given *indices*.
    Those child elements will be removed from *parent* and instead inserted as children of
    the new container at indices[0]. The new container will contain all tags that are equal in
    all of its new children; its TITLE tag will be set to *newTitle*.
    
    removeString defines what to remove from the titles of the elements that are moved below the
    new container; this will usually be similar to *newTitle* plus possibly some punctutaion.
    If *adjustPositions* is True, the positions of items that are *not* removed are decreased
    to fill the gaps arising from moved elements.
    Example: Consider the following setting of an album containing a Sonata: 
    
    * parent
    |- pos1: child0 (title = Sonata Nr. 5: Allegro)
    |- pos2: child1 (tilte = Sonata Nr. 5: Adagio)
    |- pos3: child2 (title = Sonata Nr. 5: Finale. Presto)
    |- pos4: child3 (title = Nocturne Op. 13/37)
    |- pos5: child4 (title = Prelude BWV 42)
    
    After a call to merge with *indices=(0,1,2)*, *newTitle='Sonata Nr. 5'*, *removeString='Sonata Nr. 5: '*,
    *adjustPositions = True* the layout would be:
    
    * parent
    |- * pos1: new container (title = Sonata Nr. 5)
       |- pos1: child0 (title = Allegro)
       |- pos2: child1 (title = Adagio)
       |- pos3: child2 (title = Finale. Presto)
    |- pos2: child3 (title = Nocturne Op. 13/37)
    |- pos3: child4 (title = Prelude BWV 42)
    """ 
    def __init__(self, level, parent, indices, newTitle, removeString, adjustPositions):
        
        super().__init__()
        self.insertIndex = indices[0] # where the new container will live
        self.level = level
        self.newTitle = newTitle
        self.tagChanges = {}
        self.parentChanges = {} # maps child id to (position under old parent, position under new container) tuples
        self.positionChanges = {}
        def recordTagChanges(element):
            if tagsModule.TITLE in element.tags:
                tagCopy = element.tags.copy()
                tagCopy[tagsModule.TITLE] = [ t.replace(removeString, '') for t in tagCopy[tagsModule.TITLE]]
                self.tagChanges[id] = tagsModule.TagDifference(element.tags, tagCopy)
        if isinstance(parent, Wrapper):
            self.elementParent = True
            self.insertPosition = parent.element.contents[self.insertIndex][1]
            
            self.parentID = parent.element.id
            
            for index, (position, id) in enumerate(parent.element.contents.items()):
                element = level.get(id)
                if index in indices:
                    self.parentChanges[id] = (position, len(self.parentChanges) + 1)
                    recordTagChanges(element)
                elif adjustPositions and len(self.parentChanges) > 1:
                    self.positionChanges[id] = (position, position - len(self.parentChanges) + 1)
                    
        else:
            self.elementParent = False
            for index, wrapper in enumerate(parent.contents):
                id = wrapper.element.id
                element = level.get(id)
                if index in indices:
                    self.parentChanges[id] = (index, len(self.parentChanges) + 1)
                    recordTagChanges(element)
            
    def redo(self):
        if not hasattr(self, "containerID"):
            if self.level is levels.real:
                self.containerID = db.write.createElements([(False, not self.elementParent, len(self.parentChanges), False)])[0]
            else:
                self.containerID = levels.createTId()
        elif self.level is levels.real:
            db.write.createElementsWithIds([(self.containerID, False, not self.elementParent, len(self.parentChanges), False)])
        container = Container(self.level, self.containerID, major = False)
        elements = []
        self.level.elements[self.containerID] = container
        if self.elementParent:
            parent = self.level.get(self.parentID)
            
        for id, (oldPos, newPos) in self.parentChanges.items():
            element = self.level.get(id)
            if self.elementParent:
                parent.contents.remove(pos = oldPos)
                element.parents.remove(self.parentID)
            element.parents.append(self.containerID)
            container.contents.insert(newPos, id)
            elements.append(element)
            if id in self.tagChanges:
                self.tagChanges[id].apply(element.tags)
        container.tags = tagsModule.findCommonTags(elements)
        container.tags[tagsModule.TITLE] = [self.newTitle]
        if self.elementParent:
            parent.contents.insert(self.insertPosition, self.containerID)
        for id, (oldPos, newPos) in sorted(self.positionChanges.items()):
            element = self.level.get(id)
            parent.contents.positions[parent.contents.positions.index(oldPos)] = newPos
        if self.level is levels.real:
            db.transaction()
            modify.real.changeTags(self.tagChanges)
            modify.real.changeTags({self.containerID: tagsModule.TagDifference(None, container.tags)})
            db.write.addContents([(self.containerID, id, newPos) for (id, (oldPos,newPos)) in self.parentChanges.items()])
            if self.elementParent:
                db.write.removeAllContents([self.parentID])
                db.write.addContents([(self.parentID, pos, childID) for pos,childID in parent.contents.items()])
            db.commit()
            for id, diff in self.tagChanges.items():
                elem = self.level.get(id)
                if elem.isFile() and not diff.onlyPrivateChanges():
                    modify.real.changeFileTags(elem.path, diff)
        
        self.level.emitEvent(dataIds = list(self.positionChanges.keys()),
                             contentIds = [self.containerID, self.parentID] if self.elementParent else [self.containerID])
                  
    def undo(self):
        if self.elementParent:
            parent = self.level.get(self.parentID)
            del parent.contents[self.insertIndex]
            for id, (oldPos, newPos) in self.positionChanges.items():
                element = self.level.get(id)
                parent.contents.positions[parent.contents.positions.index(newPos)] = oldPos
        for id, (oldPos, newPos) in self.parentChanges.items():
            element = self.level.get(id)
            if self.elementParent:
                parent.contents.insert(oldPos, id)
                element.parents.append(self.parentID)
            element.parents.remove(self.containerID)
            if id in self.tagChanges:
                self.tagChanges[id].revert(element.tags)
        if self.level is levels.real:
            db.transaction()
            modify.real.changeTags(self.tagChanges, reverse = True)
            db.write.deleteElements([self.containerID])
            if self.elementParent:
                db.write.removeAllContents([self.parentID])
                db.write.addContents([(self.parentID, pos, childID) for pos,childID in parent.contents.items()])
            db.commit()
            for id, diff in self.tagChanges.items():
                elem = self.level.get(id)
                if elem.isFile() and not diff.onlyPrivateChanges():
                    modify.real.changeFileTags(elem.path, diff)
        del self.level.elements[self.containerID]
        self.level.emitEvent(dataIds = list(self.positionChanges.keys()),
                             contentIds = [self.parentID] if self.elementParent else [])
        
    
class ClearTreeAction(treeactions.TreeAction):
    """This action clears a tree model using a simple ChangeRootCommand."""
    
    def __init__(self, parent):
        super().__init__(parent, shortcut = "Shift+Del")
        self.setIcon(utils.getIcon("clear_playlist.png"))
        self.setText(self.tr('clear'))
    
    def initialize(self):
        self.setEnabled(self.parent().model().root.getContentsCount() > 0)
    
    def doAction(self):
        model = self.parent().model()
        modify.stack.push(ChangeRootCommand(model,
                                      [node.element.id for node in model.root.contents],
                                      [],
                                      self.tr('clear view')))

class CommitTreeAction(treeactions.TreeAction):
    
    def __init__(self, parent):
        super().__init__(parent, shortcut = "Shift+Enter")
        self.setIcon(QtGui.qApp.style().standardIcon(QtGui.QStyle.SP_DialogSaveButton))
        self.setText(self.tr('commit this tree'))
        
    def initialize(self):
        self.setEnabled(len(self.parent().model().root.contents) > 0)
        
    def doAction(self):
        from . import levels
        model = self.parent().model()
        ids = set(n.element.id for n in self.parent().model().root.contents)
        modify.stack.push(levels.CommitCommand(model.level, ids, self.tr("Commit editor")))
              