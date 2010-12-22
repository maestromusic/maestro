#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#
import logging

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from omg import config,mpclient,models, tags, db, strutils, distributor
from omg.models import playlist as playlistmodel
from . import delegates, formatter, tageditor

logger = logging.getLogger("omg.gui.playlist")

# Plugins may insert functions here to insert entries in the context menu. Each function must take two parameters:
# - the playlist where the context-menu is opened
# - the node where the mouse was clicked (None if the mouse was not over an element)
# The function must return a list of QActions which will be inserted into the menu.
contextMenuProvider = []

class Playlist(QtGui.QWidget):
    model = None
    view = None
    
    def __init__(self,parent=None,model=None):
        QtGui.QWidget.__init__(self,parent)
        
        if model is not None:
            self.model = model
        else: self.model = playlistmodel.SynchronizablePlaylist()
        
        # Create Gui
        layout = QtGui.QVBoxLayout()
        self.setLayout(layout)
        
        controlLineLayout = QtGui.QHBoxLayout()
        layout.addLayout(controlLineLayout)
        
        self.view = PlaylistTreeView(self)
        self.view.doubleClicked.connect(self._handleDoubleClick)
        
        self.model.modelReset.connect(self._handleReset)
        
        layout.addWidget(self.view)
        
    def getModel(self):
        return self.model
        
    def _handleReset(self):
        self.view.expandAll()
        
    def _handleDoubleClick(self,index):
        element = self.model.data(index)
        mpclient.play(element.getOffset())


class PlaylistTreeView(QtGui.QTreeView):
    """Specialized QTreeView, which draws the currently playing track highlighted."""
    def __init__(self,parent):
        QtGui.QTreeView.__init__(self,parent)
        self.setHeaderHidden(True)
        self.setModel(parent.model)
        self.setItemDelegate(delegates.PlaylistDelegate(self,parent.model))
        self.setExpandsOnDoubleClick(False)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.MoveAction)
        
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Base,QtGui.QColor(0xE9,0xE9,0xE9))
        palette.setColor(QtGui.QPalette.AlternateBase,QtGui.QColor(0xD9,0xD9,0xD9))
        self.setPalette(palette)

    def removeSelected(self):
        # It may happen that an element and its parent element are selected. When removing the parent, the element will also be removed and will disappear from selectedIndexes(). An easy solution like 
        # for i in selectedIndexes(): removeByQtIndex(i)
        # would try to remove the child a second time.
        while len(self.selectedIndexes()) > 0:
            self.model().removeByQtIndex(self.selectedIndexes()[0])
    
    def editTags(self):
        dialog = tageditor.TagEditorWidget(self,[self.model().data(index) for index in self.selectedIndexes()])
        dialog.exec_()

    def createContainer(self):
        """Query the user for a title and create a new container containing the selected items."""
        if not self.selectionModel().hasSelection():
            return
            
        #TODO: Filter so that only the toplevel selected indexes remain
        # Copy the elements as the parent will change!
        elements = [self.model().data(index).copy() for index in self.selectionModel().selectedIndexes()]
        
        default = strutils.commonPrefix(el.tags[tags.TITLE][0] for el in elements if len(el.tags[tags.TITLE]) > 0)
        default = strutils.rstripSeparator(default)
        title,ok = QtGui.QInputDialog.getText(self,"Neuer Container","Gib den Titel des neuen Containers an:",
                                              QtGui.QLineEdit.Normal,default)

        if ok and not len(title) == 0:
            container = models.Container(tags=tags.Storage(),contents=elements)
            
            # Get the common tags (choose those tags from elements[0] which appear in all other elements, too)
            for tag in elements[0].tags:
                if tag == tags.TITLE:
                    continue
                container.tags[tag] = [v for v in elements[0].tags[tag] if all(v in el.tags[tag] for el in elements[1:])]
                    
            # Add the title tag:
            container.tags[tags.TITLE] = [title]

            # Save the container
            db.saveContainer(container)
            distributor.indicesChanged.emit(distributor.DatabaseChangeNotice([container.id],created=True))
        
    def keyReleaseEvent(self,keyEvent):
        if keyEvent.key() == Qt.Key_Delete:
            self.removeSelected()

    def contextMenuEvent(self,event):
        menu = QtGui.QMenu(self)
         
        restructureAction = QtGui.QAction("Restrukturieren",self)
        restructureAction.triggered.connect(self.model().restructure)
        menu.addAction(restructureAction)

        removeAction = QtGui.QAction("Entfernen",self)
        removeAction.triggered.connect(self.removeSelected)
        menu.addAction(removeAction)
        
        editTagsAction = QtGui.QAction("Tags editieren...",self)
        editTagsAction.triggered.connect(self.editTags)
        menu.addAction(editTagsAction)

        createContainerAction = QtGui.QAction("Container erstellen",self)
        createContainerAction.setEnabled(self.selectionModel().hasSelection())
        createContainerAction.triggered.connect(self.createContainer)
        menu.addAction(createContainerAction)
        
        node = self.model().data(self.indexAt(event.pos()))
        for provider in contextMenuProvider:
         for action in provider(self,node):
            menu.addAction(action)

        menu.exec_(event.globalPos() + QtCore.QPoint(2,2))
    
    def dropEvent(self,event):
        if event.source() is None:
            logger.debug("Drop from external source.")
        QtGui.QTreeView.dropEvent(self,event)
