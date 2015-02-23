# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from .. import config
from ..core.nodes import Wrapper, RootNode


_globalSelection = None

# This signal is emitted when the global selection changes. As parameter it contains the current global
# selection as Selection object.
changed = None
# Because a signal must be bound to a QObject, this signal is defined in MainWindow.
# We cannot import mainwindow here because we have to import this module there to define
# MainWindow._globalSelectionChanged = QtCore.pyqtSignal(selection.Selection)
# For this reason this signal is initialized in MainWindow.__init__


class Selection:
    """Objects of this class store a selection of nodes and provide methods to e.g. determine whether
    at least one file is selected or to get all selected wrappers including all of their descendants.
    Actions can use this information to decide whether they are enabled or not.

    *level* is the level that contains all selected wrappers.
    *nodes* are the selected nodes.
    If it is clear that only wrappers can be selected, you can set *onlyWrappers* to True to increase
    performance.
    """
    def __init__(self, level, nodes, onlyWrappers=False):
        self.level = level
        assert nodes is not None
        self._nodes = nodes
        
        if onlyWrappers or all(isinstance(node, Wrapper) for node in self._nodes):
            self._wrappers = self._nodes
        else: self._wrappers = [node for node in self._nodes if isinstance(node,Wrapper)]
        
    def empty(self):
        """Return whether no nodes are selected at all."""
        return len(self._nodes) == 0
    
    def nodes(self, onlyToplevel=False):
        """Return all nodes that are currently selected. If *onlyToplevel* is True, exclude nodes if an
        ancestor is also selected.
        """
        if not onlyToplevel:
            return self._nodes
        else:
            # this is reimplemented using model.isSelected in the subclass used by treeview.TreeView
            return [n for n in self._nodes if not any(parent in self._nodes for parent in n.getParents())]
        
    def wrappers(self, recursive=False):
        """Return a list of all selected element wrappers. If *recursive* is True, return all children of
        selected wrappers. If a wrapper is selected and one of its parents is also selected, don't return
        it twice.
        """
        if not recursive:
            return self._wrappers
        else:
            selectedNodes = self.nodes(onlyToplevel=True)
            wrappers = []
            for node in selectedNodes:
                wrappers.extend(filter(lambda x: isinstance(x,Wrapper),node.getAllNodes()))
            return wrappers
        
    def toplevelWrappers(self):
        """Search the tree for the toplevel wrappers and return them.
        In other words: Strip everything at the top of the tree that is not a Wrapper and remove the rest.
        """
        return self._toplevelWrappers(self._nodes)
         
    def _toplevelWrappers(self,nodes):
        """Like toplevelWrappers, but use the given nodes."""
        return itertools.chain.from_iterable(
                        [node] if isinstance(node,Wrapper) else self._toplevelWrappers(node.getContents())
                    for node in nodes)
    
    def fileWrappers(self, recursive=False, schemes=None):
        """Return a generator of all file wrappers that are selected.
        If *recursive* is True, also return files of which at least one parent is selected. If
        *schemes* is specified it must be a list of file backend schemes; then only files
        with those schemes will be returned.
        """
        if schemes is None:
            return (w for w in self.wrappers(recursive) if w.isFile())
        return (w for w in self.wrappers(recursive)
                  if w.isFile() and w.element.url.scheme in schemes)
        
    def elements(self, recursive=False):
        """Return all elements that are selected. Remove duplicates (elements might be selected in several
        wrappers)."""
        elids = set()
        def check(w):
            if w.element.id in elids:
                return False
            else:
                elids.add(w.element.id)
                return True
        return (w.element for w in self.wrappers(recursive) if check(w))
    
    def files(self, recursive=False):
        """Return all files (not file wrappers!) that are selected. Remove duplicates (elements might be
        selected in several wrappers)."""
        return (element for element in self.elements(recursive) if element.isFile())

    def containers(self, recursive=False):
        """Return all containers (not container wrappers!) that are selected. Remove duplicates
        (elements might be selected in several wrappers)."""
        return (element for element in self.elements(recursive) if element.isContainer())
    
    def hasWrappers(self):
        """True iff at least one wrapper is selected."""
        return len(self.wrappers()) > 0
    
    def hasElements(self):
        """True iff at least one element is selected (this element might be contained in a wrapper)."""
        return self.hasWrappers()
    
    def hasContainers(self):
        """True iff at least one container is selected."""
        return any(w.isContainer() for w in self.wrappers())

    def hasFiles(self, recursive=False, schemes=None):
        """True iff at least one file is selected.
        
        If *recursive* is True, also count files of which at least one parent is selected. If
        *schemes* is specified it must be a list of file backend schemes; then only files
        with those schemes will be counted.
        """
        iter = self.fileWrappers(recursive, schemes)
        try:
            next(iter)
            return True
        except StopIteration:
            return False
        
    def singleWrapper(self):
        """Return True iff one single element is selected. This does not exclude that other non-element
        nodes are selected too."""
        return len(self.wrappers()) == 1
    
    def singleParent(self, requireParentIsWrapper=False):
        """Return True iff at least one node is selected and all selected nodes share the same parent.
        If *requireParentIsWrapper* is True, that parent must be a wrapper, otherwise False is returned."""
        wrappers = self.wrappers()
        if len(wrappers) == 0:
            return False
        parent = wrappers[0].parent
        if requireParentIsWrapper and not isinstance(parent,Wrapper):
            return False
        return all(w.parent == parent for w in wrappers[1:])
    
    def backendUrls(self):
        """Return a list of BackendUrls of all files contained in this MimeData-instance."""
        return [wrapper.element.url for wrapper in self.fileWrappers()]
        
    def urls(self): # inherited
        """Return a list of QUrls of all files contained in this MimeData-instance."""
        return [url.toQUrl() for url in self.backendUrls()]
    
    @staticmethod
    def fromIndexes(model, indexList):
        """Generate a Selection instance from the QModelIndexes in *indexList*. The indexes will be sorted
        by their position in the tree. *model* must be the model containing these indexes.
        """
        indexList.sort() # QModelIndex implements < 
        return Selection(model.level, [model.data(index,role=Qt.EditRole) for index in indexList])
    
    @staticmethod
    def fromElements(level, elements):
        wrappers = [Wrapper(element) for element in elements]
        for wrapper in wrappers:
            wrapper.loadContents(recursive=True)
        return Selection(level, wrappers)

    def __str__(self):
        return 'Selection({})'.format(','.join(str(node) for node in self.nodes()))


def getGlobalSelection() -> Selection:
    """Return the Selection-instance that is globally selected."""
    return _globalSelection


def setGlobalSelection(selection: Selection):
    """Set the global selection."""
    global _globalSelection
    if _globalSelection != selection:
        _globalSelection = selection
        changed.emit(_globalSelection)


class MimeData(QtCore.QMimeData):
    """Subclass of QMimeData specialized to transport a tree of nodes. It supports two MimeTypes: The first
    one is used internally by Maestro and stores the tree-structure. Its name is stored in the config 
    variable "gui->mime". The second one is "text/uri-list" and contains a list of URLs to all files in the
    tree. This type is used by applications like Amarok and Dolphin.
        
    Use the attribute 'level' to check whether the wrappers in the MimeData are on the level used by the
    widget/model where they are dropped. If not, they might contain elements that do not exist on the second
    level as well as an invalid tree structure.
    """
    def __init__(self, selection):
        super().__init__()
        self.selection = selection
        
    def __getattr__(self, attr):
        return getattr(self.selection, attr)
        
    def hasFormat(self, format):
        return format in self.formats()
    
    def formats(self):
        return [config.options.gui.mime, "text/uri-list"]
    
    def hasUrls(self):
        return True
    
    def urls(self): #inherited
        return self.selection.urls()
        
    def retrieveData(self, mimeType, type=None):
        if mimeType == config.options.gui.mime:
            return self.selection.nodes()
        elif mimeType == "text/uri-list":
            return self.urls()
        else:
            # following the documentation of Qt a null QVariant should be returned
            # PyQt does not allow to instantiate QVariant
            return None
           
    @classmethod
    def fromIndexes(cls, model, indexList):
        """Generate a MimeData instance from the QModelIndexes in *indexList*. The indexes will be sorted
        by their position in the tree. *model* must be the model containing these indexes.
        """
        return cls(Selection.fromIndexes(model, indexList))
    
    @classmethod
    def fromElements(cls, level, elements):
        return cls(Selection.fromElements(level, elements))
    