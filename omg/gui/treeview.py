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

from collections import OrderedDict

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ..core.elements import Container
from ..core.nodes import Wrapper
from . import selection, treeactions


class NodeSelection(selection.NodeSelection):
    """Objects of this class store a selection of nodes a TreeView. Different than a QItemSelectionModel,
    a NodeSelection knows about Nodes, Elements etc and provides special methods to determine properties
    of the selection. Actions can use this information to decide whether they are enabled or not.

    *model* is a QItemSelectionModel.
    """
    def __init__(self, level, model):
        """Initialize with the given *model* (instance of QItemSelectionModel). Computes and stores
        all attributes."""
        # Get the QAbstractItemModel from a QItemSelectionModel
        super().__init__(level,[model.model().data(index) for index in model.selectedIndexes()])
        self._model = model
        
    def nodes(self,onlyToplevel=False):
        """Return all nodes that are currently selected. If *onlyToplevel* is True, nodes will be excluded
        if an ancestor is also selected.
        """
        if not onlyToplevel:
            return self._nodes
        else:
            return [n for n in self._nodes
                            if not any(self._model.isSelected(self._model.model().getIndex(parent))
                                            for parent in n.getParents())]
        

class TreeActionConfiguration(QtCore.QObject):
    """Objects of this class define an action configuration for a treeview."""
    #TODO: comment
    
    globalUndoRedo = True # specifies whether or not to add global undo/redo actions to context menu
    actionDefinitionAdded = QtCore.pyqtSignal(object)
    actionDefinitionRemoved = QtCore.pyqtSignal(str)
    
    def __init__(self, toplevel = True):
        super().__init__()
        self.toplevel = toplevel
        self.sections = OrderedDict()
        
    def addActionDefinition(self, path, callable, *args, **kwargs):
        section, name = path[0]
        if section not in self.sections:
                self.sections[section] = OrderedDict()
        if len(path) > 1:
            if name not in self.sections[section]:
                self.sections[section][name] = TreeActionConfiguration(False)
            self.sections[section][name].addActionDefinition(path[1:], callable, *args, **kwargs)
        else:
            self.sections[section][name] = (callable, args, kwargs)
        if self.toplevel:
            self.actionDefinitionAdded.emit(path)
            
    def removeActionDefinition(self, path):
        section, name = path[0]
        if len(path) > 1:
            self.sections[section][name].removeActionDefinition(path[1:])
            if len(self.sections[section][name]) == 0:
                del self.sections[section][name]
        else:
            del self.sections[section][name]
        if len(self.sections[section]) == 0:
            del self.sections[section]
        if self.toplevel:
            self.actionDefinitionRemoved.emit(path[-1][1])
    
    def __len__(self):
        return len(self.sections)
    
    def __iter__(self):
        return self.actionIterator()
    
    def getDefinition(self, path):
        section, name = path[0]
        if len(path) == 1:
            return self.sections[section][name]
        section, name = path[0]
        return self.sections[section][name].getDefinition(path[1:])

    def actionIterator(self):
        """Iterates over the actions and subactions in this configuration in the defined order."""
        for section, actions in self.sections.items():
            for name, definition in actions.items():
                if isinstance(definition, TreeActionConfiguration):
                    for a in definition:
                        yield a
                else:
                    yield name, definition 
            
    def createMenu(self, parent, treeActions):
        menu = QtGui.QMenu(parent)
        for section, actions in self.sections.items():
            sep = menu.addSeparator()
            sep.setText(section)
            
            for name, definition in actions.items():
                if isinstance(definition, TreeActionConfiguration):
                    subMenu = definition.createMenu(menu, treeActions)
                    subMenu.setTitle(name)
                    menu.addMenu(subMenu)
                else:
                    menu.addAction(treeActions[name])
        return menu
        
        
class TreeView(QtGui.QTreeView):
    """Base class for tree views that contain mostly wrappers. This class handles mainly the
    ContextMenuProvider system, that allows plugins to insert entries into the context menus of playlist and
    browser.
    
    *level* is the level that contains all elements in the tree (never mix wrappers from different levels!)
    *affectGlobalSelection* determines whether the treeview will change the global selection whenever nodes
    in the it are selected. This should be set to False for treeviews in dialogs.
    """
    
    actionConfig = TreeActionConfiguration()
    
    def __init__(self,level,parent=None,affectGlobalSelection=True):
        super().__init__(parent)
        self.level = level
        self.affectGlobalSelection = affectGlobalSelection
        
        self.setHeaderHidden(True)
        self.setExpandsOnDoubleClick(False)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        
        self.treeActions = {}
        for name,  (callable, args, kwargs) in self.actionConfig:
            if callable is not None:
                self.treeActions[name] = action = callable(self, *args, **kwargs)
                self.addAction(action)
        self.actionConfig.actionDefinitionAdded.connect(self.addTreeAction)
        self.actionConfig.actionDefinitionRemoved.connect(self.removeTreeAction)
        
    def removeTreeAction(self, name):
        action = self.treeActions[name]
        self.removeAction(action)
        del self.treeActions[name]
        
    def addTreeAction(self, path):
        callable, args, kwargs = self.actionConfig.getDefinition(path)
        if callable is not None:
            action = self.treeActions[path[-1][1]] = callable(self, *args, **kwargs)
            self.addAction(action)
    
    def setModel(self, model):
        super().setModel(model)
        self.updateNodeSelection()
    
    def focusInEvent(self, event):
        self.updateNodeSelection()
        super().focusInEvent(event)
    
    def dropEvent(self, event):
        super().dropEvent(event)
        self.updateNodeSelection()
        
    def updateNodeSelection(self):
        self.nodeSelection = NodeSelection(self.level,self.selectionModel())
        for action in self.treeActions.values():
            if isinstance(action, treeactions.TreeAction):
                action.initialize()
        
    def contextMenuEvent(self, event):
        menu = self.actionConfig.createMenu(self, self.treeActions)
        if menu is not None:
            menu.popup(event.globalPos())
            event.accept()
        else:
            event.ignore()
        
    def keyPressEvent(self, event):
        self.updateNodeSelection()
        super().keyPressEvent(event)
        
    def mousePressEvent(self, event):
        self.updateNodeSelection()
        super().mousePressEvent(event)
    
    def keyReleaseEvent(self, event):
        self.updateNodeSelection()
        super().keyReleaseEvent(event)
        
    def selectionChanged(self, selected, deselected):
        super().selectionChanged(selected, deselected)
        self.updateNodeSelection()
        if self.affectGlobalSelection and not self.nodeSelection.empty():
            selection.setGlobalSelection(self.nodeSelection)  
    
    def currentNode(self):
        current = self.currentIndex()
        if current.isValid():
            return current.internalPointer()
        
    def selectedRanges(self):
        """Return the ranges of selected nodes. Each range is a 3-tuple of parent (which doesn't need to be
        selected), first index of parent.contents that is selected and the last index that is selected.
        """
        selection = self.selectionModel().selection()
        return [(self.model().data(itemRange.parent()),itemRange.top(),itemRange.bottom())
                    for itemRange in selection]
