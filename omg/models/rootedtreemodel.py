# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

import os.path

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ..gui import selection
from .. import logging, config
from ..core.nodes import Node, RootNode, Wrapper
from ..core import elements, levels, tags


logger = logging.getLogger(__name__)


class RootedTreeModel(QtCore.QAbstractItemModel):
    """The RootedTreeModel subclasses QAbstractItemModel to create a simple model for QTreeViews. It has one
    root node which is not considered part of the data of this model (and is not displayed by QTreeViews).
    Nodes in a RootedTreeModel may have every type, but must implement the following attributes and methods:
    
        - parent: the node's parent. The root node must have parent None
        - hasContents(): return if a node has children
        - getContentsCount(): return the number of children of the node
        - getContents(): return the list of children of the node
        
    The hasContents-method allows to implement nodes that don't calculate the number of children until the
    node is expanded the first time.
    """
    def __init__(self, root = None):
        super().__init__()
        self.root = RootNode(self) if root is None else root
    
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
        return (config.options.gui.mime, "text/uri-list")
    
    def mimeData(self,indexes):
        return selection.MimeData.fromIndexes(self, indexes)
    
    def toolTipText(self, index):
        """Return a tooltip for the node at the given index. If no tooltip is available, return None.
        
        To implement tool tips in models inheriting RootedTreeModel it is usually sufficient to
        
            - implement the method 'toolTipText' in custom node classes used by the model. If a node
              has this method, it is used to create its tooltip.
            - reimplement 'createWrapperToolTip' to customize tooltips of Wrapper nodes.

        """
        if index:
            node = index.internalPointer()
            if hasattr(node, "toolTipText"):
                return node.toolTipText()
            elif isinstance(node, Wrapper):
                return self.createWrapperToolTip(node)
        return None
    
    def createWrapperToolTip(self, wrapper, coverSize=120,
                             showTags=True, showFlags=False, showParents=False, showFileNumber=True):
        """Return a tooltip for *wrapper*. Using the optional arguments of this method various parts of the
        tooltip can be enabled/disabled. Subclasses that wish to customize tooltips often only need to
        reimplement this method, only changing its default arguments.
        """
        el = wrapper.element
        lines = [el.getTitle()]
        if el.isFile() and el.url is not None:
            lines.append(str(el.url))
        elif el.isContainer():
            if showFileNumber:
                lines.append(self.tr("{} with {} pieces").format(elements.getTypeTitle(el.type),
                                                                 wrapper.fileCount()))
            else: lines.append(elements.getTypeTitle(el.type))
        if showTags and el.tags is not None:
            lines.extend("{}: {}".format(tag.title, ', '.join(map(str, values)))
                         for tag, values in el.tags.items() if tag != tags.TITLE)
        
        if showFlags and el.tags is not None and len(el.flags) > 0:
            lines.append(self.tr("Flags: ")+','.join(flag.name for flag in el.flags))
            
        if showParents and el.parents is not None:
            parentIds = list(el.parents)
            if isinstance(wrapper.parent, Wrapper) and wrapper.parent.element.id in parentIds:
                parentIds.remove(wrapper.parent.element.id)
            parents = levels.real.collectMany(parentIds)
            parents.sort(key=elements.Element.getTitle)
            lines.extend(self.tr("#{} in {}").format(p.contents.positionOf(el.id), p.getTitle())
                         for p in parents)
        
        # Escape tags for use in HTML
        import html
        lines = '<br/>'.join(html.escape(line) for line in lines)
        
        if coverSize is not None and el.hasCover():
            imgTag = el.getCoverHTML(coverSize, 'style="float: left"')
            if imgTag is not None:
                return imgTag + '<div style="margin-left: {}">{}</div>'.format(coverSize+5, lines)
        # enclose in a div so that Qt formats this as rich text.
        # Otherwise HTML escapes would be printed as plain text.
        return '<div>{}</div>'.format(lines)
            
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

    def getAllNodes(self):
        """Generator which will return all nodes contained in the tree (excluding the rootnode) 
        in depth-first-manner. If *skipSelf*."""
        return self.root.getAllNodes(skipSelf=True)
    
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
                
    def walk(self, node):
        """A tree iterator for nodes, inspired by os.walk.
        
        Yields tuples (node, contents), and contents may be modified in-place to influence further
        processing.
        """
        contents = node.getContents()[:]
        yield node, contents
        for child in contents:
            for x in self.walk(child):
                yield x
    
    def __contains__(self, node):
        """Return whether *node* is contained in this model."""
        if node == self.root:
            return True
        else: return node in node.parent.contents and node.parent in self