# -*- coding: utf-8 -*-
# Copyright 2011 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
import logging

from omg import constants, tags
from omg.gui.delegates import GopulateDelegate
from omg.models import Element, RootNode, playlist
from .playlist import PlaylistTreeView
from . import treeview, tageditor

logger = logging.getLogger("gui.editor")

class EditorTreeWidget(treeview.TreeView):
    """Suitable widget to display an EditorModel"""
    
    itemsSelected = QtCore.pyqtSignal(list, name="itemsSelected")
    
    def __init__(self, parent = None):
        treeview.TreeView.__init__(self, parent)
        self.setItemDelegate(GopulateDelegate())
        self.setAlternatingRowColors(True)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        #self.setDefaultDropAction(Qt.MoveAction)
        self.mergeAction = QtGui.QAction(self.tr("Merge"), self)
        self.mergeAction.triggered.connect(self._mergeSelected)
        
        self.commitAction = QtGui.QAction(self.tr("Commit"), self)
        self.commitAction.triggered.connect(self._commitSelected)
        
        
        self.flattenAction = QtGui.QAction(self.tr("Flatten"), self)
        self.flattenAction.triggered.connect(self._flattenSelected)
        
        self.viewport().setMouseTracking(True)
        
    def dataChanged(self, ind1, ind2):
        QtGui.QTreeView.dataChanged(self, ind1, ind2)
        self.setCorrectWidth()
  
    def reset(self):
        QtGui.QTreeView.reset(self)
        self.setCorrectWidth()
        
    def contextMenuProvider(self, actions, currentIndex):
        treeview.TreeView.contextMenuProvider(self,actions,currentIndex)
        
        actions.append(self.undoAction)
        actions.append(self.redoAction)
        if self.selectionModel().hasSelection():
            if len(set(i.parent() for i in self.selectedIndexes())) == 1: # merge only valid if all indices share the same parent
                actions.append(self.mergeAction)
                actions.append(self.commitAction)
            if self.currentIndex().internalPointer().isContainer():
                actions.append(self.flattenAction)
    
    def removeSelected(self):
        while len(self.selectedIndexes()) > 0:
            self.model().removeByQtIndex(self.selectedIndexes()[0])       
        
    def keyReleaseEvent(self,keyEvent):
        if keyEvent.key() == Qt.Key_Delete:
            self.removeSelected()
            keyEvent.accept()
        else:
            QtGui.QTreeView.keyReleaseEvent(self, keyEvent)
    
    def dragMoveEvent(self, event):
        if event.keyboardModifiers() & Qt.ShiftModifier:
            event.setDropAction(Qt.MoveAction)
        elif event.keyboardModifiers() & Qt.ControlModifier:
            event.setDropAction(Qt.CopyAction)
        elif isinstance(event.source(), PlaylistTreeView):
            event.setDropAction(Qt.CopyAction)
        else:
            event.setDropAction(event.proposedAction())
        QtGui.QTreeView.dragMoveEvent(self, event)
    
    def wheelEvent(self, wheelEvent):
        if QtGui.QApplication.keyboardModifiers() & Qt.AltModifier:
            index = self.indexAt(wheelEvent.pos())
            elem = index.internalPointer()
            if not index.isValid() or not isinstance(elem.parent, Element):
                wheelEvent.ignore()
                return
            if elem.getPosition() is not None:
                if wheelEvent.delta() > 0:
                    elem.setPosition(elem.getPosition()+1)
                elif elem.getPosition() > 1:
                    elem.setPosition(elem.getPosition()-1)
                else:
                    elem.setPosition(None)
            else:
                elem.setPosition(1)
            self.model().dataChanged.emit(index, index)
            self.model().dataChanged.emit(index.parent(), index.parent())
            
            wheelEvent.accept()
        else:
            QtGui.QTreeView.wheelEvent(self, wheelEvent) 
        
    def editTags(self,recursive):
        elements = self.getSelectedNodes(True)
        if recursive:
            for elem in elements:
                if elem.isContainer():
                    elements.extend(elem.getChildren())
            
        dialog = tageditor.TagEditorDialog(self,elements)
        dialog.exec_()
    
    def expandNotInDB(self, index = QtCore.QModelIndex(), *args):
        """expands all tree items that are not in the database, or contain children that ar not in the databaes. Collapse all other items."""
        num = self.model().rowCount(index)
        if index.isValid():
            if index.internalPointer().isInDB(recursive = True):
                self.collapse(index)
            else:
                self.expand(index)
        for i in range(num):
            self.expandNotInDB(self.model().index(i, 0, index))
                
    def setModel(self, model):
        QtGui.QTreeView.setModel(self, model)
        model.modelReset.connect(self.expandNotInDB)
        self.selectionModel().selectionChanged.connect(self._handleSelectionChanged)
        self.expandNotInDB()
        self.undoAction = model.undoStack.createUndoAction(self,self.tr("Undo"))
        self.redoAction = model.undoStack.createRedoAction(self,self.tr("Redo"))
        model.rowsInserted.connect(self.expandNotInDB)
    
    def _mergeSelected(self):
        indices = self.selectionModel().selectedIndexes()
        hint = calculateMergeHint(indices)
        title,flag = QtGui.QInputDialog.getText(self,self.tr("Merge elements"),
                                                self.tr("Name of new subcontainer:"), text = hint)
        if flag:
            self.model().merge(indices, title)
    
    def _commitSelected(self):
        for i in self.selectionModel().selectedIndexes():
            i.internalPointer().commit(toplevel = not isinstance(i.parent().internalPointer(), Element))
    
    def _deleteSelected(self):
        indices = self.selectedIndexes()
        indicesToDelete = set()
        implicitlyDeleted = set()
        for ind in indices:
            if ind.internalPointer().isInDB() and not ind.parent() in indices:
                indicesToDelete.add(ind)
        for i in indicesToDelete:
            i.internalPointer().delete()
        self.model().reset()
        
    def _flattenSelected(self):
        self.model().flatten(self.currentIndex())
        
    def setCorrectWidth(self):
        self.resizeColumnToContents(0)
    
    def _handleSelectionChanged(self, selected, deselected):
        items = [self.model().data(index, Qt.EditRole) for index in self.selectionModel().selectedIndexes() ]
        self.itemsSelected.emit(items)
        
class EditorWidget(QtGui.QWidget):
    """EditorWidget consists of an EditorTreeModel and buttons to control the editing process."""
    
    dbChanged = QtCore.pyqtSignal()
    itemsSelected = QtCore.pyqtSignal(list, name="itemsSelected")
    def __init__(self, model):
        QtGui.QWidget.__init__(self)
        self.dirLabel = QtGui.QLabel()
        self.tree = EditorTreeWidget()
        
        self.accept = QtGui.QPushButton(self.tr("Commit"))
        self.accept.pressed.connect(self._handleAcceptPressed)
        self.accept.released.connect(self._handleAcceptReleased)
        self.accept.clicked.connect(model.commit)
        self.tree.itemsSelected.connect(self.itemsSelected)
       
        self.clear = QtGui.QPushButton(self.tr("Clear"))
        self.clear.clicked.connect(self._handleClear)
        
        layout = QtGui.QVBoxLayout(self)
        layout.addWidget(self.dirLabel)
        layout.addWidget(self.tree)
        subLayout = QtGui.QHBoxLayout()
        subLayout.addWidget(self.accept)
        subLayout.addWidget(self.clear)
        layout.addLayout(subLayout)
        
        self.tree.setModel(model)
        self.tree.setHeaderHidden(True)
        
        self.setAcceptDrops(True)
        
    
    def _handleAcceptPressed(self):
        self.accept.setText(self.tr("Calculating audio hashes..."))
    
    def _handleAcceptReleased(self):
        self.accept.setText(self.tr("Accept"))
    
    def _handleClear(self):
        self.tree.model().undoStack.push(playlist.ModelResetCommand(self.tree.model()))

from functools import reduce
from difflib import SequenceMatcher

def longestSubstring(a, b):
    sm = SequenceMatcher(None, a, b)
    result = sm.find_longest_match(0, len(a), 0, len(b))
    return a[result[0]:result[0]+result[2]]
    
def calculateMergeHint(indices):
    return reduce(longestSubstring,
                   ( ", ".join(ind.internalPointer().tags[tags.TITLE]) for ind in indices )
                 ).strip(constants.FILL_CHARACTERS)
    
