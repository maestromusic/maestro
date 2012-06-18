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

from ..core.nodes import Wrapper

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

    *level* is the level that contains all selected wrappers. *nodes* are the selected nodes. If it is clear
    that only wrappers can be selected, you can set *onlyWrappers* to True to increase performance.
    """
    def __init__(self,level,nodes,onlyWrappers=False):
        self.level = level
        self._nodes = nodes
        if onlyWrappers or all(isinstance(node,Wrapper) for node in self._nodes):
            self._wrappers = self._nodes
        else: self._wrappers = [node for node in self._nodes if isinstance(node,Wrapper)]
    
    def empty(self):
        """Return whether no nodes are selected at all."""
        return len(self._nodes) == 0
    
    def nodes(self,onlyToplevel=False):
        """Return all nodes that are currently selected. If *onlyToplevel* is True, nodes will be excluded
        if an ancestor is also selected.
        """
        if not onlyToplevel:
            return self._nodes
        else:
            #TODO (this is implemented using model.isSelected in the subclass used by treeview.TreeView)
            raise NotImplementedError()
        
    def wrappers(self,recursive=False):
        """Returns a list of all selected element wrappers. If *recursive* is True, all children of selected
        wrappers are also returned."""
        if not recursive:
            return self._wrappers
        else:
            selectedNodes = self.nodes(onlyToplevel=True)
            wrappers = []
            for node in selectedNodes:
                wrappers.extend(filter(lambda x: isinstance(x,Wrapper),node.getAllNodes()))
            return wrappers
        
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
        """Returns True iff one single element is selected. This does not exclude that other non-element
        nodes are selected too."""
        return len(self._wrappers) == 1
    
    def singleParent(self, requireParentElement = False):
        """Returns True iff all selected elements share the same parent. IF *requireParentElement* is True,
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
        