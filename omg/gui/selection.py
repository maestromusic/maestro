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

from ..core.nodes import RootNode, Wrapper

_globalSelection = None

# This signal is emitted when the global selection changes. As parameter it contains the current global
# selection as NodeSelection object.
changed = None
# Because a signal must be bound to a QObject, this signal is defined in MainWindow.
# We cannot import mainwindow here because we have to import this module there to define
# MainWindow._globalSelectionChanged = QtCore.pyqtSignal(selection.NodeSelection)
# For this reason this signal is initialized in MainWindow.__init__ 


def getGlobalSelection():
    """Return the level in which the global selection is contained and the wrappers that form the current
    global selection."""
    return _globalSelection


def setGlobalSelection(nodeSelection):
    """Set the global selection."""
    global _globalSelection
    _globalSelection = nodeSelection
    changed.emit(_globalSelection)


class NodeSelection:
    """Objects of this class store a selection of nodes and provide methods to e.g. determine whether
    at least one file is selected or to get all selected wrappers including all of their descendants.
    Actions can use this information to decide whether they are enabled or not.

    *level* is the level that contains all selected wrappers.
    *nodes* are the selected nodes. This must be a list and it will be sorted.
    If it is clear that only wrappers can be selected, you can set *onlyWrappers* to True to increase
    performance.
    """
    def __init__(self,level,nodes,onlyWrappers=False):
        self.level = level
        self._nodes = nodes
        
        # Sort nodes
        def indexGenerator(node):
            """Return the index of *node* in its parent, the index of the parent in the grandparent and
            so on."""
            while not isinstance(node,RootNode):
                yield node.parent.index(node)
                node = node.parent
        nodes.sort(key=lambda n: tuple(indexGenerator(n)))
        
        if onlyWrappers or all(isinstance(node,Wrapper) for node in self._nodes):
            self._wrappers = self._nodes
        else: self._wrappers = [node for node in self._nodes if isinstance(node,Wrapper)]
    
    def empty(self):
        """Return whether no nodes are selected at all."""
        return len(self._nodes) == 0
    
    def nodes(self,onlyToplevel=False):
        """Return all nodes that are currently selected. If *onlyToplevel* is True, exclude nodes if an
        ancestor is also selected.
        """
        if not onlyToplevel:
            return self._nodes
        else:
            # this is reimplemented using model.isSelected in the subclass used by treeview.TreeView
            return [n for n in self._nodes if not any(parent in self._nodes for parent in n.getParents())]
        
    def wrappers(self,recursive=False):
        """Return a list of all selected element wrappers. If *recursive* is True return all children of
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
        """Search the tree for the toplevel wrappers and return them. This differs from the result of
        getNodes only if some nodes are no wrappers (but e.g. ValueNodes from the broswer).
        In other words: Strip everything at the top of the tree that is not a Wrapper and remove the rest.
        """
        return self._toplevelWrappers(self._nodes)
         
    def _toplevelWrappers(self,nodes):
        """Like getWrappers, but use the given nodes."""
        return itertools.chain.from_iterable(
                        [node] if isinstance(node,Wrapper) else self._toplevelWrappers(node.getContents())
                    for node in nodes)
        
    def elements(self,recursive=False):
        """Return all elements that are selected. Remove duplicates (elements might be selected in several
        wrappers."""
        ids = set()
        def check(w):
            if w.element.id in ids:
                return False
            else:
                ids.add(w.element.id)
                return True
        return (w.element for w in self.wrappers(recursive) if check(w))
        
    def singleWrapper(self):
        """Return True iff one single element is selected. This does not exclude that other non-element
        nodes are selected too."""
        return len(self._wrappers) == 1
    
    def singleParent(self, requireParentElement = False):
        """Return True iff all selected elements share the same parent. IF *requireParentElement* is True,
        that parent must also be an element, otherwise False is returned."""
        if len(self._wrappers) == 0:
            return False
        parent = self._wrappers[0].parent
        if requireParentElement and not isinstance(parent,Wrapper):
            return False
        return all(w.parent == parent for w in self._wrappers[1:])
    
    def hasWrappers(self):
        """True iff at least one element is selected."""
        return len(self._wrappers) > 0
    
    def hasContainers(self):
        """True iff at least one container is selected."""
        return any(w.isContainer() for w in self._wrappers)

    def hasFiles(self):
        """True iff at least one file is selected."""
        return any(el.isFile() for el in self._elements)
    
    def files(self,recursive=False):
        """Return all file wrappers that are selected. If *recursive* is True, also return files of which
        at least one parent is selected."""
        return (w for w in self.wrappers(recursive) if w.isFile())
        