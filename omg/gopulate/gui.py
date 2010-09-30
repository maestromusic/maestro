# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
import logging

from . import calculateMergeHint
from omg.gui.delegates import GopulateDelegate
from omg.models import Element

logger = logging.getLogger("gopulate.gui")

class GopulateTreeWidget(QtGui.QTreeView):
    """Suitable to display a GopulateTreeModel"""
    
    def __init__(self, parent = None):
        QtGui.QTreeView.__init__(self, parent)
        self.setItemDelegate(GopulateDelegate())
        self.setAlternatingRowColors(True)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        #self.setDefaultDropAction(Qt.MoveAction)
        self.mergeAction = QtGui.QAction("merge", self)
        self.mergeAction.triggered.connect(self._mergeSelected)
        
        self.commitAction = QtGui.QAction("commit", self)
        self.commitAction.triggered.connect(self._commitSelected)
        
        self.deleteAction = QtGui.QAction("delete from DB", self)
        self.deleteAction.triggered.connect(self._deleteSelected)
        
        self.viewport().setMouseTracking(True)
        
    def dataChanged(self, ind1, ind2):
        QtGui.QTreeView.dataChanged(self, ind1, ind2)
        self.setCorrectWidth()
  
    def reset(self):
        QtGui.QTreeView.reset(self)
        self.setCorrectWidth()
        
    def contextMenuEvent(self, event):
        if self.selectionModel().hasSelection():
            menu = QtGui.QMenu(self)
            if len(set(i.parent() for i in self.selectedIndexes())) == 1: # merge only valid if all indices share the same parent
                menu.addAction(self.mergeAction)
                menu.addAction(self.commitAction)
            if any((i.internalPointer().isInDB() for i in self.selectedIndexes())):
                menu.addAction(self.deleteAction)
            
            if not menu.isEmpty(): 
                menu.popup(event.globalPos())
            else:
                del menu
            event.accept()
        else:
            event.ignore()
    
    def removeSelected(self):
        while len(self.selectedIndexes()) > 0:
            self.model().removeByQtIndex(self.selectedIndexes()[0])       
        
    def keyReleaseEvent(self,keyEvent):
        if keyEvent.key() == Qt.Key_Delete:
            self.removeSelected()
            keyEvent.accept()
        else:
            QtGui.QTreeView.keyReleaseEvent(self, keyEvent)
    
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
    
    def expandNotInDB(self, index = QtCore.QModelIndex()):
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
        self.expandNotInDB()
    
    def _mergeSelected(self):
        indices = self.selectionModel().selectedIndexes()
        hint = calculateMergeHint(indices)
        title,flag = QtGui.QInputDialog.getText(self, "merge elements", "Name of new subcontainer:", text = hint)
        if flag:
            self.model().merge(self.selectionModel().selectedIndexes(), title)
    
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
        
    def setCorrectWidth(self):
        self.resizeColumnToContents(0)
        
class GopulateWidget(QtGui.QWidget):
    """GopulateWidget consists of a GopulateTreeModel and buttons to control the populate process."""
    
    dbChanged = QtCore.pyqtSignal()
    
    def __init__(self, model):
        QtGui.QWidget.__init__(self)
        self.dirLabel = QtGui.QLabel()
        self.tree = GopulateTreeWidget()
        model.searchDirectoryChanged.connect(self.dirLabel.setText)
        
        self.accept = QtGui.QPushButton('accept')
        self.accept.pressed.connect(self._handleAcceptPressed)
        self.accept.released.connect(self._handleAcceptReleased)
        self.accept.clicked.connect(model.commit)
        
        self.next = QtGui.QPushButton('next')
        self.next.pressed.connect(self._handleNextPressed)
        self.next.released.connect(self._handleNextReleased)
        self.next.clicked.connect(model.nextDirectory)
        self.next.clicked.connect(self.dbChanged.emit)
        
        layout = QtGui.QVBoxLayout(self)
        layout.addWidget(self.dirLabel)
        layout.addWidget(self.tree)
        subLayout = QtGui.QHBoxLayout()
        subLayout.addWidget(self.accept)
        subLayout.addWidget(self.next)
        layout.addLayout(subLayout)
        
        self.tree.setModel(model)
        self.tree.setHeaderHidden(True)
        self.dirLabel.setText(model.searchdir)
    
    def _handleAcceptPressed(self):
        self.accept.setText("calculating audio hashes...")
    
    def _handleAcceptReleased(self):
        self.accept.setText("accept")
        
    def _handleNextPressed(self):
        self.next.setText("searching for new files...")
    
    def _handleNextReleased(self):
        self.next.setText("next")
