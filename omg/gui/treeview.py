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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import models, logging
from ..modify.treeactions import *
from ..constants import REAL
from omg.modify.treeactions import ToggleMajorAction

translate = QtGui.QApplication.translate
logger = logging.getLogger(__name__)

def makeUnique(iterable):
    """Return a list that is a copy of *iterable* where all elements with the same ID appear only once."""
    ret = []
    ids = set()
    for elem in iterable:
        if hasattr(elem, 'id'):
            if not elem.id in ids:
                ids.add(elem.id)
                ret.append(elem)
        else:
            ret.append(elem)
    return ret

class NodeSelection:
    """Objects of this class store a selection of nodes a TreeView. Different than a QItemSelectionModel,
    a NodeSelection knows about Nodes, Elements etc and provides special methods to determine properties
    of the selection. Actions can use this information to decide whether they are enabled or not.
    
    Besides the methods defined below, the following attributes are available:
    - nodes: A list of all selected nodes (both elements and other nodes)
    - parents: A list of parents of selected elements (parents may or may not be elements themselves)
    """
    def __init__(self, model):
        """Initialize with the given *model* (instance of QItemSelectionModel). Computes and stores
        all attributes."""
        indexes = model.selectedIndexes()
        self._nodes = [ model.model().data(index) for index in indexes ]
        self._elements = [ node for node in self._nodes if isinstance(node, models.Element) ]
        self._parents = set(elem.parent for elem in self._elements)
        self._model = model
    
    def empty(self):
        return len(self._nodes) == 0
    
    def nodes(self,onlyToplevel=False):
        """Return all nodes that are currently selected. If *onlyToplevel* is True, nodes will be excluded
        if an ancestor is also selected.
        """
        if not onlyToplevel:
            return self._nodes
        else:
            result = []
            for node in self._nodes:
                if not any(self._model.isSelected(self._model.model().getIndex(parent))
                               for parent in node.getParents()):
                    result.append(node)
            return result
        
    def elements(self, recursive = False, unique = True):
        """Returns a list of all selected elements. If *recursive* is True, all children of selected elements
        are also returned. If *unique* is True, the list does not contain more than one element with the same ID."""
        if not recursive:
            # Just remove duplicates and nodes which don't have tags
            return makeUnique(self._elements) if unique else self._elements
        else:
            selectedNodes = self.nodes(onlyToplevel=True)
            elements = []
            ids = set()
            for node in selectedNodes:
                for child in node.getAllNodes():
                    if isinstance(child,models.Element):
                        # if the element is inside the database, load it from there, because
                        # browser stores incomplete elements
                        # TODO: bääh
                        elements.append(models.Element.fromId(child.id) if child.isInDB() else child)
            return elements
        
    def singleElement(self):
        """Returns True iff one single element is selected. This does not exclude that other non-element
        nodes are selected too."""
        return len(self._elements) == 1
    
    def singleParent(self, requireParentElement = False):
        """Returns True iff all selected elements share the same parent. IF *requireParentElement* is True,
        that parent must also be an element, otherwise False is returned."""
        return len(self._parents) == 1 and \
            (not requireParentElement or isinstance(next(iter(self._parents)), models.Element))
    
    def hasElements(self):
        """True iff at least one element is selected."""
        return len(self._elements) > 0
    
    def hasFiles(self):
        """True iff at least one file is selected."""
        return any(el.isFile() for el in self._elements)
        

        
class TreeView(QtGui.QTreeView):
    """Base class for tree views that contain mainly elements. This class handles mainly the
    ContextMenuProvider system, that allows plugins to insert entries into the context menus of playlist and
    browser.
    """
    level = REAL
    @classmethod
    def initContextMenu(cls):
        """Class method to initialize the context menu. This method should be overwritten in subclasses."""
        menu = [ ]
        tagsMenu = NamedList(translate(__name__, 'tags'), (EditTagsAction(False),
                                                              EditTagsAction(True),
                                                              MatchTagsFromFilenamesAction()) )
        structureMenu = NamedList(translate(__name__, 'structure'), (DeleteAction(CONTENTS),
                                                                     DeleteAction(DB),
                                                                     DeleteAction(DISK),
                                                                     MergeAction(),
                                                                     ToggleMajorAction()))
        menu.append(tagsMenu)
        menu.append(structureMenu)
        
        return menu
        
        
    @classmethod
    def contextMenu(cls):
        if not '_contextMenu' in cls.__dict__:
            if 'initContextMenu' in cls.__dict__:
                # ensure that init is called only for subclasses defining their own init function
                cls._contextMenu = cls.initContextMenu()
            else:
                cls._contextMenu = []
        return cls._contextMenu
    
    @classmethod
    def contextMenus(cls):
        for c in reversed(cls.mro()):
            if issubclass(c, TreeView):
                yield c.contextMenu()
                
        
    def __init__(self,parent):
        QtGui.QTreeView.__init__(self,parent)
        self.contextMenuProviderCategory = None
        
        self.setHeaderHidden(True)
        self.setExpandsOnDoubleClick(False)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Base,QtGui.QColor(0xE9,0xE9,0xE9))
        palette.setColor(QtGui.QPalette.AlternateBase,QtGui.QColor(0xD9,0xD9,0xD9))
        self.setPalette(palette)
    
        # These rows enable a horizontal scrollbar. The length that can be scrolled will be determined by
        # the column length and _not_ by the delegate's sizehint (though you may use resizeColumnToContents).
        #self.header().setHorizontalScrollMode(QtGui.QAbstractItemView.ScrollPerPixel)
        #self.header().setStretchLastSection(False)
        #self.header().setResizeMode(0,QtGui.QHeaderView.ResizeToContents)

    def _addContextMenuItem(self, item, menu):
        """Adds the context menu part defined by *item* to the parent *menu*.
        
        *item* must be either a TreeAction object or an iterable with a *name* attribute (e.g. a
        NamedList) containing valid items."""
        if isinstance(item, TreeAction):
            item.initialize(self.nodeSelection, self)
            if item.visible:
                menu.addAction(item)
                return True
            return False
        elif isinstance(item, HybridTreeAction):
            item.initialize(self.nodeSelection, self)
            if item.visible:
                if any( [self._addContextMenuItem(subItem, menu) for subItem in item.actions] ):
                    return True
            return False
        else:
            subMenu = QtGui.QMenu(item.name, menu)
            
            if any( [self._addContextMenuItem(subItem, subMenu) for subItem in item] ):
                menu.addMenu(subMenu)
                return True
            return False

    def contextMenuEvent(self,event):
        self.nodeSelection = NodeSelection(self.selectionModel())
        
        contextMenus = list(self.contextMenus())
        menu = QtGui.QMenu(self)
        for i, cm in enumerate(contextMenus):
            for item in cm:
                self._addContextMenuItem(item, menu)
            if i < len(contextMenus) -1:
                menu.addSeparator()

        menu.popup(event.globalPos() + QtCore.QPoint(2,2))
        event.accept()
        