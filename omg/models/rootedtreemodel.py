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

from PyQt4 import QtCore
from PyQt4.QtCore import Qt

import itertools
from . import Node, Element, RootNode, mimedata
from .. import logging, config
from ..utils import ranges
logger = logging.getLogger(__name__)

class RootedTreeModel(QtCore.QAbstractItemModel):
    """The RootedTreeModel subclasses QAbstractItemModel to create a simple model for QTreeViews. It takes one
    root node which is not considered part of the data of this model (and is not displayed by QTreeViews).
    Nodes in a RootedTreeModel may have every type, but must implement the following methods:
    
        - hasChildren(): return if a node has children
        - getChildrenCount(): return the number of children of the node
        - getChildren(): return the list of children of the node
        - getParent(): return the node's parent. The root-node' getParent-method must return None.
        
    The hasChildren-method allows to implement nodes that calculate the number of children not until the node
    is expanded the first time.
    """
    
    # The root node. Use getRoot to retrieve it.
    root = None
    
    def __init__(self,root=None):
        """Initialize a new RootedTreeModel. Optionally you can specify the root of the model."""
        QtCore.QAbstractItemModel.__init__(self)
        self.root = root
    
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
            element = index.internalPointer()
            if hasattr(element, "toolTipText"):
                return element.toolTipText()
            else:
                return str(element)
            
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
        return QtCore.QAbstractItemModel.createIndex(self,row,column,internalPointer)
        
    def getIndex(self,node):
        """Return the (Qt)-index of the given node. If <node> is the root of this model, return an invalid
        QModelIndex."""
        if node == self.root:
            return QtCore.QModelIndex()
        parent = node.parent
        try:
            parent.index(node)
        except ValueError:
            raise RuntimeError("Cannot create an index for node {} because ".format(node)
                               + "it is not contained in its alleged parent {}.".format(parent))
            
        return self.createIndex(parent.index(node),0,node)     

    def getAllNodes(self):
        """Generator which will return all nodes contained in the tree in depth-first-manner."""
        return self.root.getAllNodes()
    
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
    
    def changePositions(self, parent, changes):
        """Changes positions of elements below *parent*, according to the oldPosition->newPosition dict *changes.*"""
        logger.debug('POSITION CHANGE: {}'.format(changes))
        #TODO: rewrite with difflib / opcodes??
        def argsort(seq):
            # http://stackoverflow.com/questions/3382352/equivalent-of-numpy-argsort-in-basic-python/3383106#3383106
            #lambda version by Tony Veijalainen
            return [x for x,y in sorted(enumerate(seq), key = lambda x: x[1])]
        def newPosition(i):
            try:
                return changes[i]
            except KeyError:
                return i
        sortedIndices = argsort( [ newPosition(node.iPosition()) for node in parent.contents ] )
        # change position attribute of elements
        if not isinstance(parent, RootNode):
            for elem in parent.contents:
                elem.position = newPosition(elem.position)
        parentIndex = self.getIndex(parent)
        # I stores the changes done on the current indexes of the elements in parent.contents
        I = list(range(len(sortedIndices)))
        # J[k] stores where to find the element that, before any changes, was at index k; i.e.
        # at any time parent.contents[J[k]] is the element that was parent.contents[k] before
        # the call to this method 
        J = list(range(len(sortedIndices)))
        i = len(I)-1
        # start from the end
        while i >= 0:
            # decrease i until there is a wrong position
            while sortedIndices[i] == I[i]:
                i -= 1
                if i < 0:
                    return
            # here: sortedIndices[i] != I[i]
            end = sortedIndices[i]
            start = end
            for j in range(i-1,-1,-1):
                if sortedIndices[j] == start - 1:
                    start = sortedIndices[j]
                else:
                    break
            iStart, iEnd = J[start], J[end]
            self.beginMoveRows(parentIndex, iStart, iEnd, parentIndex, i+1)
            # move elements
            for lst in parent.contents, I:
                lst[i+1:i+1] = lst[iStart:iEnd+1]
                lst[iStart:iEnd+1] = [] 
            self.endMoveRows()
            # update J
            tmp = J[start:end+1]
            J[start:end+1] = []
            J[iStart:iStart] = tmp
            i -= 1
        self.dataChanged.emit(parentIndex.child(0, 0), parentIndex.child(0, len(I)))
          
    def insert(self,parent,insertions):
        """Insert nodes below *parent*. *insertions* is a list of (int, Element) tuples. The integer is
        either the position (if *parent* is an Element) or the index (otherwise) of the inserted Element.
        This method always copies elements before insertion."""
        insertionIter = iter(sorted(insertions))
        insertPos, insertElem = next(insertionIter)
        lastIndex = len(parent.contents)
        offset = 0
        insertJobs = []
        allSeen = False
        for i, node in itertools.chain(enumerate(parent.contents), [(lastIndex, None)]):
            insertHere = []
            current = node.position if node and isinstance(parent, Element) else i
            try:
                while node is None or insertPos < current:
                    insertHere.append( insertElem.copy() )
                    insertPos, insertElem = next(insertionIter)
            except StopIteration:
                allSeen = True
            if len(insertHere) > 0:
                insertJobs.append(( i + offset, insertHere))
                offset += len(insertHere)
            if allSeen:
                break
        for i, nodes in insertJobs:
            self.beginInsertRows(self.getIndex(parent), i, i+len(nodes)-1)
            parent.insertContents(i, nodes)
            self.endInsertRows()
    
    def remove(self, parent, removals):
        """Remove nodes below *parent*. The elements to remove are defined by *removals*, a list of IDs."""
        modelIndex = self.getIndex(parent)
        i = [ i for i,elem in enumerate(parent.contents) if elem.iPosition() in removals ]
        for start, end in reversed(ranges(i)):
            self.beginRemoveRows(modelIndex, start, end)
            del parent.contents[start:end+1]
            self.endRemoveRows()