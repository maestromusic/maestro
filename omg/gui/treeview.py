# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

from .. import application
from . import selection, treeactions


class Selection(selection.Selection):
    """Objects of this class store a selection of nodes in a TreeView. Different than a QItemSelectionModel,
    a Selection knows about Nodes, Elements etc and provides special methods to determine properties
    of the selection. Actions can use this information to decide whether they are enabled or not.

    *model* is a QItemSelectionModel.
    """
    def __init__(self, level, model):
        """Initialize with the given *model* (instance of QItemSelectionModel). Computes and stores
        all attributes."""
        # Get the QAbstractItemModel from a QItemSelectionModel
        super().__init__(level,[model.model().data(index) for index in model.selectedIndexes()])
        self._model = model
        
    def nodes(self, onlyToplevel=False):
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
        self.setDefaultDropAction(Qt.CopyAction)
        self.viewport().setMouseTracking(True)
        
        self.treeActions = {}
        for name, (callable, args, kwargs) in self.actionConfig:
            if callable is not None:
                self.treeActions[name] = action = callable(self, *args, **kwargs)
                self.addAction(action)
        self.actionConfig.actionDefinitionAdded.connect(self._addTreeAction)
        self.actionConfig.actionDefinitionRemoved.connect(self._removeTreeAction)
        self.localActions = []
        
        
    def _addTreeAction(self, path):
        callable, args, kwargs = self.actionConfig.getDefinition(path)
        if callable is not None:
            action = self.treeActions[path[-1][1]] = callable(self, *args, **kwargs)
            self.addAction(action)
    
    def _removeTreeAction(self, name):
        action = self.treeActions[name]
        self.removeAction(action)
        del self.treeActions[name]
    
    def addLocalAction(self, action):
        """Used add an action to this treeview instance only, without the global actionConfig.
        
        The action will be appended to the end of the context menu.
        """
        self.addAction(action)
        self.localActions.append(action)
        
    def removeLocalAction(self, action):
        """Remove an action previously added by *addLocalAction*."""
        self.removeAction(action)
        self.localActions.remove(action)
    
    def setModel(self, model):
        super().setModel(model)
        self.updateSelection()
    
    def focusInEvent(self, event):
        self.updateSelection()
        super().focusInEvent(event)

    def updateSelection(self):
        selectionModel = self.selectionModel()
        if selectionModel is not None: # happens if the view is empty
            self.selection = Selection(self.level, selectionModel)
            for action in self.treeActions.values():
                if isinstance(action, treeactions.TreeAction):
                    action.initialize(self.selection)
        
    def contextMenuEvent(self, event):
        if len(self.treeActions) == 0:
            event.ignore()
            return
        menu = self.actionConfig.createMenu(self, self.treeActions)
        for action in self.localActions:
            menu.addAction(action)
        if menu is not None:
            menu.popup(event.globalPos())
            event.accept()
        else:
            event.ignore()
               
    def selectionChanged(self, selected, deselected):
        super().selectionChanged(selected, deselected)
        self.updateSelection()
        if self.affectGlobalSelection and not self.selection.empty():
            selection.setGlobalSelection(self.selection)  
    
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
    
    
class DraggingTreeView(TreeView):
    """This is the baseclass of tree views that allow to drag and drop wrappers, e.g. playlist and editor.
    It handles the following issues:
    
        - Drag&drop actions must be enclosed in one undo-macro.
        - Drags between views of the same class default to a move, drags between different views to a copy.
          Via the shift and control modifier this default can be overridden. 
        - Models might need to know when a drag&drop action is going on. For this DraggingTreeView will
          call the methods startDrag and endDrag on models which provide them (both without arguments).
        - Before dropMimeData is called a DraggingTreeView will set the attributes dndSource and dndTarget
          of the receiving model to the sending widget and itself. If the drag was started in an external
          application, dndSource will be None. 
        
    """
    def __init__(self, level, parent=None, affectGlobalSelection=True):
        super().__init__(level, parent, affectGlobalSelection)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
    
    @property
    def stack(self):
        """Return the stack that is used for changes to this tree."""
        return application.stack
    
    def startDrag(self, supportedActions):
        model = self.model()
        self.stack.beginMacro("Drag and Drop")
        if hasattr(model, 'startDrag'):
            model.startDrag()
        try:
            super().startDrag(supportedActions)
        finally:
            if hasattr(model, 'endDrag'):
                model.endDrag()
            self.stack.endMacro(abortIfEmpty=True)
            
    def _changeDropAction(self, event):
        if event.keyboardModifiers() & Qt.ShiftModifier:
            event.setDropAction(Qt.MoveAction)
        elif event.keyboardModifiers() & Qt.ControlModifier:
            event.setDropAction(Qt.CopyAction)
        elif isinstance(event.source(), type(self)):
            event.setDropAction(Qt.MoveAction)
        else: 
            event.setDropAction(Qt.CopyAction)
            
    def dragEnterEvent(self, event):
        self._changeDropAction(event)
        event.accept()
        super().dragEnterEvent(event)
        
    def dragMoveEvent(self, event):
        self._changeDropAction(event)
        event.accept()
        super().dragMoveEvent(event)
        
    def dropEvent(self, event):
        # workaround due to bug #67
        if event.mouseButtons() & Qt.LeftButton:
            event.ignore()
            return
        self._changeDropAction(event)
        self.model().dndSource = event.source()
        self.model().dndTarget = self
        super().dropEvent(event)
        self.model().dndSource = None
        self.model().dndTarget = None
        self.updateSelection()
        