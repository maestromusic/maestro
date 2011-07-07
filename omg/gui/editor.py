# -*- coding: utf-8 -*-
# Copyright 2011 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from collections import OrderedDict
from ..gui import mainwindow
from ..models import editor, Container
from . import treeview
from .. import logging, modify, tags


translate = QtCore.QCoreApplication.translate
logger = logging.getLogger("gui.editor")

class EditorTreeView(treeview.TreeView):
    def __init__(self, name='default', parent = None):
        treeview.TreeView.__init__(self, parent)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.setModel(editor.EditorModel(name))
        self.viewport().setMouseTracking(True)
        self.mergeAction = QtGui.QAction(self.tr('Merge...'), self)
        self.mergeAction.triggered.connect(self.mergeSelected)
    
    def contextMenuProvider(self, actions, currentIndex):
        s = set( index.parent() for index in self.selectedIndexes() )
        if len(s) == 1:
            actions.append(self.mergeAction)
        super().contextMenuProvider(actions,currentIndex)

    def dragEnterEvent(self, event):
        if event.source() is self:
            event.setDropAction(Qt.MoveAction)
        else:
            event.setDropAction(Qt.CopyAction)
        treeview.TreeView.dragEnterEvent(self, event)
        
    def dragMoveEvent(self, event):
        if isinstance(event.source(), EditorTreeView):
            if event.keyboardModifiers() & Qt.ShiftModifier:
                event.setDropAction(Qt.MoveAction)
            elif event.keyboardModifiers() & Qt.ControlModifier:
                event.setDropAction(Qt.CopyAction)
        treeview.TreeView.dragMoveEvent(self, event)
        
    def dropEvent(self, event):
        if isinstance(event.source(), EditorTreeView):
            if event.keyboardModifiers() & Qt.ShiftModifier:
                event.setDropAction(Qt.MoveAction)
            elif event.keyboardModifiers() & Qt.ControlModifier:
                event.setDropAction(Qt.CopyAction)
            elif event.source() is self:
                event.setDropAction(Qt.MoveAction)
            else:
                event.setDropAction(Qt.CopyAction)
        treeview.TreeView.dropEvent(self, event)
        logger.debug("dropEvent in treeview completed")
        
    def keyPressEvent(self, keyEvent):
        if keyEvent.key() == Qt.Key_Delete:
            self.removeSelected()
            keyEvent.accept()
        else:
            QtGui.QTreeView.keyPressEvent(self, keyEvent)
            
    def removeSelected(self):
        modify.pushEditorCommand(
            modify.RemoveElementsCommand(modify.EDITOR, [s.internalPointer() for s in self.selectedIndexes()]))
        
    def mergeSelected(self):
        hintTitle, hintRemove = self.model().createMergeHint(self.selectedIndexes())
        dialog = MergeDialog(hintTitle, hintRemove, self)
        if dialog.exec_() == QtGui.QDialog.Accepted:
            modify.merge([p.internalPointer() for p in self.selectedIndexes()], modify.EDITOR, dialog.newTitle(), dialog.removeString())
            
               
class EditorWidget(QtGui.QDockWidget):
    def __init__(self, parent = None, state = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('editor'))
        widget = QtGui.QWidget()
        self.setWidget(widget)
        vb = QtGui.QVBoxLayout(widget)
        try:
            name = state[0]
            checkState = state[1]
        except:
            name = 'default'
            checkState = True
        self.editor = EditorTreeView(name)
        vb.addWidget(self.editor)
        hb = QtGui.QHBoxLayout()
        vb.addLayout(hb)
        self.newContainerButton = QtGui.QPushButton(self.tr("new container"))
        self.newContainerButton.clicked.connect(self.newContainerDialog)
        hb.addWidget(self.newContainerButton)
        self.nameField = QtGui.QLineEdit(name)
        hb.addWidget(self.nameField)
        self.albumGuesserCheckbox = QtGui.QCheckBox(self.tr('guess albums'))
        self.albumGuesserCheckbox.stateChanged.connect(self.editor.model().setGuessAlbums)
        self.albumGuesserCheckbox.setCheckState(checkState)
        hb.addWidget(self.albumGuesserCheckbox)

    
    def newContainerDialog(self):
        title, ok = QtGui.QInputDialog.getText(self, "Title", "Title of the container:")
        if not ok:
            return
        changes = OrderedDict()
        c_tags = tags.Storage()
        c_tags[tags.TITLE] = [title]
        container = Container(c_tags, None, modify.newEditorId())
        oldRoot = self.editor.model().root
        newRoot = oldRoot.copy()
        newRoot.contents.append(container)
        container.setParent(newRoot)
        changes[oldRoot.id] = (oldRoot, newRoot)
        comm = modify.UndoCommand(modify.EDITOR, changes, contentsChanged = True, text=self.tr('new container'))
        modify.pushEditorCommand(comm)
        
    def saveState(self):
        return (self.nameField.text(), self.albumGuesserCheckbox.checkState())
# register this widget in the main application
eData = mainwindow.WidgetData(id = "editor",
                             name = translate("Editor","editor"),
                             theClass = EditorWidget,
                             central = True,
                             dock = True,
                             default = True,
                             unique = False,
                             preferredDockArea = Qt.RightDockWidgetArea)
mainwindow.addWidgetData(eData)
    
class MergeDialog(QtGui.QDialog):
    def __init__(self, hintTitle, hintRemove, parent = None):
        super().__init__(parent)
        layout = QtGui.QVBoxLayout()
        hLayout = QtGui.QHBoxLayout()
        label = QtGui.QLabel(self.tr('Title of new container:'))
        hLayout.addWidget(label)
        hLayout.addStretch()
        self.titleEdit = QtGui.QLineEdit(hintTitle)
        hLayout.addWidget(self.titleEdit)        
        layout.addLayout(hLayout)
        
        hLayout = QtGui.QHBoxLayout()
        self.checkBox = QtGui.QCheckBox(self.tr('Remove from titles:'))
        self.checkBox.setChecked(True) 
        hLayout.addWidget(self.checkBox)
        hLayout.addStretch()
        self.removeEdit = QtGui.QLineEdit(hintRemove)
        hLayout.addWidget(self.removeEdit)
        self.checkBox.toggled.connect(self.removeEdit.setEnabled)
        layout.addLayout(hLayout)
        
        hLayout = QtGui.QHBoxLayout()
        self.cancelButton = QtGui.QPushButton(self.tr('Cancel'))
        self.okButton = QtGui.QPushButton(self.tr('OK'))
        self.cancelButton.clicked.connect(self.reject)
        self.okButton.clicked.connect(self.accept)
        hLayout.addStretch()
        hLayout.addWidget(self.cancelButton)
        hLayout.addWidget(self.okButton)
        layout.addLayout(hLayout)
        self.setLayout(layout)
    def newTitle(self):
        return self.titleEdit.text()
    def removeString(self):
        return self.removeEdit.text() if self.checkBox.isChecked() else ''