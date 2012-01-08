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
from .. import modify
from ..modify import treeactions
from ..constants import REAL
from collections import OrderedDict

translate = QtGui.QApplication.translate
logger = logging.getLogger(__name__)

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
        
    def elements(self, recursive = False):
        """Returns a list of all selected elements. If *recursive* is True, all children of selected elements
        are also returned. If *unique* is True, the list does not contain more than one element with the same ID."""
        if not recursive:
            # Just remove duplicates and nodes which don't have tags
            return self._elements
        else:
            selectedNodes = self.nodes(onlyToplevel=True)
            elements = []
            ids = set()
            for node in selectedNodes:
                for child in node.getAllNodes():
                    if isinstance(child,models.Element):
                        elements.append(child)
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
    
    def hasContainers(self):
        """True iff at least one container is selected."""
        for element in self._elements:
            if isinstance(element, models.Container):
                return True
        return False

    def hasFiles(self):
        """True iff at least one file is selected."""
        return any(el.isFile() for el in self._elements)
        

class TreeActionConfiguration(QtCore.QObject):
    """Objects of this class define an action configuration for a treeview."""
    
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
    """Base class for tree views that contain mainly elements. This class handles mainly the
    ContextMenuProvider system, that allows plugins to insert entries into the context menus of playlist and
    browser.
    """
    level = REAL
    
    actionConfig = TreeActionConfiguration()
    
    def __init__(self,parent = None):
        QtGui.QTreeView.__init__(self, parent)
        
        self.setHeaderHidden(True)
        self.setExpandsOnDoubleClick(False)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Base,QtGui.QColor(0xE9,0xE9,0xE9))
        palette.setColor(QtGui.QPalette.AlternateBase,QtGui.QColor(0xD9,0xD9,0xD9))
        self.setPalette(palette)
        
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
    
    def updateNodeSelection(self):
        self.nodeSelection = NodeSelection(self.selectionModel())
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
        self.updateGlobalSelection(selected, deselected)
        self.updateNodeSelection()
    
    def currentNode(self):
        current = self.currentIndex()
        if current.isValid():
            return current.internalPointer()
        
    def updateGlobalSelection(self, selected, deselected):
        """Change the global selection if some any elements are selected in any views. Connect the
        selectionChanged() signal of the selection model to this slot to obtain the desired effect."""
        globalSelection = []
        for index in self.selectionModel().selectedIndexes():
            node = self.model().data(index)
            # The browser does not load tags automatically
            if isinstance(node, models.Element):
                globalSelection.append(node)
        if len(globalSelection):
            from . import mainwindow
            mainwindow.setGlobalSelection(globalSelection,self)