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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import mimedata
from .. import application, logging, config, utils
from .. import database as db, modify
from ..core import levels, tags as tagsModule
from ..core.elements import Container, ContentList
from ..core.nodes import Node, RootNode, Wrapper


logger = logging.getLogger(__name__)


class RootedTreeModel(QtCore.QAbstractItemModel):
    """The RootedTreeModel subclasses QAbstractItemModel to create a simple model for QTreeViews. It has one
    root node which is not considered part of the data of this model (and is not displayed by QTreeViews).
    Nodes in a RootedTreeModel may have every type, but must implement the following methods:
    
        - hasChildren(): return if a node has children
        - getChildrenCount(): return the number of children of the node
        - getChildren(): return the list of children of the node
        - getParent(): return the node's parent. The root-node's getParent-method must return None.
        
    The hasChildren-method allows to implement nodes that don't calculate the number of children until the
    node is expanded the first time.
    """
    def __init__(self, level = None, root = None):
        super().__init__()
        self.root = RootNode(self) if root is None else root
        self.level = level
        if level is not None:
            level.changed.connect(self._handleLevelChanged)
    
    def getRoot(self):
        """Return the root node of this model."""
        return self.root
        
    def setRoot(self,root):
        """Set the root of this model to *root* and reset (QTreeViews using this model will be reset, too)."""
        self.root = root
        self.reset()
    
    def clear(self):
        self.beginResetModel()
        self.root.contents = []
        self.endResetModel()
        
    def data(self,index,role=Qt.EditRole):
        if not index.isValid():
            if role == Qt.EditRole:
                return self.root
            else:
                return None
        if role == Qt.DisplayRole:
            return str(index.internalPointer())
        if role == Qt.EditRole:
            return index.internalPointer()
        if role == Qt.ToolTipRole:
            return self.toolTipText(index)
        return None
    
    def mimeTypes(self):
        return (config.options.gui.mime,"text/uri-list")
    
    def mimeData(self,indexes):
        return mimedata.MimeData.fromIndexes(self,indexes)
    
    def toolTipText(self, index):
        if index:
            node = index.internalPointer()
            if hasattr(node, "toolTipText"):
                return node.toolTipText()
            else:
                return str(node)
            
    def hasChildren(self,index):
        if not index.isValid():
            if self.root is None:
                return False
            else: return self.root.hasContents()
        else: return self.data(index).hasContents()
        
    def rowCount(self,parent):
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            if self.root is None:
                return 0
            return self.root.getContentsCount()
        else: return self.data(parent).getContentsCount()

    def columnCount(self,parent):
        return 1
    
    def parent(self,index):
        if not index.isValid():
            return QtCore.QModelIndex()
        child = index.internalPointer()
        parent = child.parent
        # This method should never be called on the root-node because it is not displayed in the treeview.
        assert parent is not None
        if parent == self.root:
            return QtCore.QModelIndex()
        else: return self.getIndex(parent)
    
    def index(self,row,column,parent):
        if not self.hasIndex(row,column,parent): # Check if parent has a child at the given row and column
            return QtCore.QModelIndex()
        if not parent.isValid():
            parent = self.root
        else:
            parent = parent.internalPointer()
        child = parent.contents[row]
        return self.createIndex(row,column,child)
        
    def flags(self,index):
        if not index.isValid(): 
            # may happen during drag and drop
            # http://doc.trolltech.com/4.4/model-view-dnd.html#enabling-drag-and-drop-for-items
            return Qt.ItemIsEnabled;
        else: return Qt.ItemIsEnabled | Qt.ItemIsSelectable
    
    def createIndex(self,row,column,internalPointer):
        if not isinstance(internalPointer,Node):
            raise TypeError("Internal pointers in a RootedTreeModel must be subclasses of Node, but got {}"
                               .format(type(internalPointer)))
        return super().createIndex(row,column,internalPointer)
        
    def getIndex(self,node):
        """Return the (Qt)-index of the given node. If *node* is the root of this model, return an invalid
        QModelIndex."""
        if node == self.root:
            return QtCore.QModelIndex()

        parent = node.parent
        try:
            pos = parent.index(node)
        except ValueError:
            raise RuntimeError("Cannot create an index for node {} because ".format(node)
                               + "it is not contained in its alleged parent {}.".format(parent))
            
        return self.createIndex(pos,0,node)     

    def getAllNodes(self, skipSelf = False):
        """Generator which will return all nodes contained in the tree in depth-first-manner."""
        return self.root.getAllNodes(skipSelf)
    
    def breadthFirstTraversal(self):
        """Generator which will return all nodes contained in the tree in breadth-first-manner."""
        # Warning: The autoLoad feature of BrowserModel depends on some implementation details of this method.
        # (the problem is that CriterionNodes load their contents during the bfs.)
        queue = [self.root]
        while len(queue) > 0:
            node = queue.pop(0)
            for child in node.getContents():
                if child.hasContents():
                    queue.append(child)
                yield child
                
    def contains(self,node):
        """Return whether *node* is contained in this model."""
        if node == self.root:
            return True
        else: return node in node.parent.contents and self.contains(node.parent)

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
        logger.debug("merge: inserted new container with ID {} into level {}".format(self.containerID, self.level))
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
        