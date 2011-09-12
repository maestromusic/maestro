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
from . import delegates, formatter, treeview, tageditor

logger = logging.getLogger("omg.gui.playlist")

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
        

class PlaylistTreeView(treeview.TreeView):
    """Specialized TreeView, which draws the currently playing track highlighted."""
    def __init__(self,parent):
        treeview.TreeView.__init__(self,parent)
        self.contextMenuProviderCategory = 'playlist'
        self.setModel(parent.model)
        self.setItemDelegate(delegates.PlaylistDelegate(self,parent.model))
        self.setDefaultDropAction(Qt.MoveAction)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def contextMenuProvider(self,actions,currentIndex):
        treeview.TreeView.contextMenuProvider(self,actions,currentIndex)
        
        action = QtGui.QAction(self.tr("Remove selected elements"),self)
        action.triggered.connect(self.removeSelected)
        actions.insert(2,action)

        action = QtGui.QAction(self.tr("Create container..."),self)
        action.setEnabled(self.selectionModel().hasSelection())
        action.triggered.connect(self.createContainer)
        actions.insert(3,action)
        
        action = QtGui.QAction(self.tr("Restructure playlist tree"),self)
        action.triggered.connect(self.model().restructure)
        actions.append(action)
        
    
    def editTags(self,recursive):
        if not recursive:
            elements = self.getSelectedNodes()
        else: 
            elements = self.getSelectedNodes(onlyToplevel=True)
            ids = set(element.id for element in elements)
            contentIds = db.contents(ids,recursive=True)
            for id in contentIds:
                if id not in ids:
                    ids.add(id)
                    newElement = models.createElement(id)
                    newElement.loadTags()
                    elements.append(newElement)

        dialog = tageditor.TagEditorDialog(self,elements)
        dialog.exec_()
        
    def removeSelected(self):
        for node in self.getSelectedNodes(onlyToplevel=True):
            self.model().removeByQtIndex(self.model().getIndex(node))

    def createContainer(self):
        """Query the user for a title and create a new container containing the selected items."""
        if not self.selectionModel().hasSelection():
            return

        # Copy the elements as the parent will change!
        elements = [node.copy() for node in self.getSelectedNodes(onlyToplevel=True)]
        
        default = strutils.commonPrefix(el.tags[tags.TITLE][0] for el in elements if len(el.tags[tags.TITLE]) > 0)
        default = strutils.rstripSeparator(default)
        title,ok = QtGui.QInputDialog.getText(self,self.tr("New container"),
                                              self.tr("Enter the title of the new container:"),
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

    def dropEvent(self,event):
        if event.source() is None:
            logger.debug("Drop from external source.")
        QtGui.QTreeView.dropEvent(self,event)
