#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg import db, distributor, models

# Plugins may insert functions here to insert entries in the context menu. Each function must take three parameters:
# - the treeview where the context-menu is opened
# - a list of actions and/or separators which will be inserted in the menu
# - the current index, i.e. the index where the mouse was clicked (None if the mouse was not over an element)
# To insert actions into the context menu, the function must modify the second parameter.
# There are three lists (categories) where such function can be inserted: 'all' will be executed for all treeviews, 'playlist' and 'browser' only in playlists or browsers, respectively.
contextMenuProviders = {
'all': [],
'playlist': [],
'browser': []
}

# SEPARATOR is a special value which can be inserted in the list of actions for a context-menu. TreeView.contextMenuEvent will insert a separator at that position.
class Separator: pass
SEPARATOR = Separator()

class TreeView(QtGui.QTreeView):
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

    def getSelectedNodes(self,onlyToplevel=False):
        model = self.model()
        if not onlyToplevel:
            return [model.data(index) for index in self.selectedIndexes()]
        else:
            result = []
            for index in self.selectedIndexes():
                node = model.data(index)
                if not any(self.selectionModel().isSelected(model.getIndex(parent)) for parent in node.getParents()):
                    result.append(node)
            return result

    def contextMenuProvider(self,actions,currentIndex):
        # Check whether at least one Element is selected
        hasSelectedElements = any(isinstance(node,models.Element) for node in self.getSelectedNodes())
        
        action = QtGui.QAction("Tags editieren...",self)
        action.setEnabled(hasSelectedElements)
        action.triggered.connect(lambda: self.editTags(False))
        actions.append(action)

        action = QtGui.QAction("Tags rekursiv editieren...",self)
        action.setEnabled(self.selectionModel().hasSelection())
        action.triggered.connect(lambda: self.editTags(True))
        actions.append(action)

        action = QtGui.QAction("Ausgewählte Elemente neu einlesen",self)
        action.setEnabled(hasSelectedElements)
        action.triggered.connect(self.updateFromFileSystem)
        actions.append(action)
        
        action = QtGui.QAction("Ausgewählte Elemente aus DB löschen...", self)
        action.setEnabled(hasSelectedElements)
        action.triggered.connect(self.deleteFromDB)
        actions.append(action)
        
    def contextMenuEvent(self,event):
        currentIndex = self.indexAt(event.pos())
        actions = []
        self.contextMenuProvider(actions,currentIndex)
        for f in contextMenuProviders['all']:
            f(actions)
        if self.contextMenuProviderCategory is not None:
            for f in contextMenuProviders[contextMenuProviderCategory]:
                f(actions)

        menu = QtGui.QMenu(self)
        for action in actions:
            menu.addAction(action)

        menu.popup(event.globalPos() + QtCore.QPoint(2,2))
        event.accept()

    def updateFromFileSystem(self):
        ids = [element.id for element in self.getSelectedNodes()]
        #TODO hier gehts weiter
        
    def deleteFromDB(self):
        """Non-recursively deletes the selected elements from the database."""
        if (QtGui.QMessageBox.question(self,"Element löschen",
                                       "Sollen die ausgewählten Elemente wirklich aus der Datenbank gelöscht werden?",
                                       QtGui.QMessageBox.Yes|QtGui.QMessageBox.No,QtGui.QMessageBox.No)
                != QtGui.QMessageBox.Yes):
            return
        ids = [element.id for element in self.getSelectedNodes()]
        db.deleteElements(ids)
        distributor.indicesChanged.emit(distributor.DatabaseChangeNotice(ids,deleted=True))
