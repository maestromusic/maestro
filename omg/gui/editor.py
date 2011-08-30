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
from ..models import editor, Container, Element, RootNode
from . import treeview
from .. import logging, modify, tags
from ..modify import commit

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
        
        self.tagMatchAction = QtGui.QAction(self.tr('Match tags from filenames...'), self)
        self.tagMatchAction.triggered.connect(self.openTagMatchDialog)
        
        self.removeSelectedAction = QtGui.QAction(self.tr('Remove'), self)
        self.removeSelectedAction.triggered.connect(self.removeSelected)
        self.removeSelectedAction.setShortcut(Qt.Key_Delete)
        
        self.increasePositionAction = QtGui.QAction(self.tr('Increase position(s)'), self)
        self.increasePositionAction.triggered.connect(self.increasePositions)
        self.increasePositionAction.setShortcut(Qt.Key_Plus)
        
        self.decreasePositionAction = QtGui.QAction(self.tr('Decrease position(s)'), self)
        self.decreasePositionAction.triggered.connect(self.decreasePositions)
        self.decreasePositionAction.setShortcut(Qt.Key_Minus)
        self.selectionModel().selectionChanged.connect(self._handleSelectionChanged)
    
    def _handleSelectionChanged(self, selected, deselected):
        """Change the global selection if some any elements are selected in any views."""
        globalSelection = []
        for index in self.selectionModel().selectedIndexes():
            node = self.model().data(index)
            # The browser does not load tags automatically
            if isinstance(node,Element):
                globalSelection.append(node)
        if len(globalSelection):
            mainwindow.setGlobalSelection(globalSelection,self)
             
    def contextMenuProvider(self, actions, currentIndex):
        s = set( index.parent() for index in self.selectedIndexes() )
        if len(s) == 1:
            actions.append(self.mergeAction)
            if tuple(s)[0].internalPointer() is not None:
                actions.append(self.increasePositionAction)
                actions.append(self.decreasePositionAction)
        actions.append(self.removeSelectedAction)
        actions.append(self.tagMatchAction)
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
    
    def increasePositions(self):
        self.model().shiftPositions([index.internalPointer() for index in self.selectedIndexes()], 1)
    
    def decreasePositions(self):
        self.model().shiftPositions([index.internalPointer() for index in self.selectedIndexes()], -1)
            
    def removeSelected(self):
        if len(self.selectedIndexes()) == 0:
            return
        modify.push(
            modify.RemoveElementsCommand(modify.EDITOR, [s.internalPointer() for s in self.selectedIndexes()]))
        
    def mergeSelected(self):
        mergeIndexes = self.selectedIndexes()
        hintTitle, hintRemove = self.model().createMergeHint(mergeIndexes)
        mergePositions = sorted(idx.row() for idx in mergeIndexes)
        numSiblings = self.model().rowCount(mergeIndexes[0].parent())
        dialog = MergeDialog(hintTitle, hintRemove, len(mergePositions) < numSiblings, self)
        if dialog.exec_() == QtGui.QDialog.Accepted:
            modify.merge(modify.EDITOR,
                         mergeIndexes[0].internalPointer().parent,
                         mergePositions,
                         dialog.newTitle(),
                         dialog.removeString(),
                         dialog.adjustPositions())
    
    def openTagMatchDialog(self):
        from . import tagmatchdialog
        dialog = tagmatchdialog.TagMatchDialog([s.internalPointer() for s in self.selectedIndexes()], self)
        dialog.exec_()
            
    def editTags(self,recursive):
        """Reimplement TreeView.editTags so that tags are edited on the EDITOR-level instead."""
        from . import tageditor
        dialog = tageditor.TagEditorDialog(modify.EDITOR,self.getSelectedElements(recursive),self)
        dialog.exec_()
            
               
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
        self.editor.model().setGuessAlbums(checkState)
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
        hb.addStretch()
        self.commitButton = QtGui.QPushButton(self.tr('commit all editors'))
        hb.addWidget(self.commitButton)
        self.commitButton.clicked.connect(commit.commitEditors)

    
    def newContainerDialog(self):
        title, ok = QtGui.QInputDialog.getText(self, "Title", "Title of the container:")
        if not ok:
            return
        changes = OrderedDict()
        c_tags = tags.Storage()
        c_tags[tags.TITLE] = [title]
        container = Container(id = modify.newEditorId(), tags = c_tags, contents = None, position = None )
        oldRoot = self.editor.model().root
        newRoot = oldRoot.copy()
        newRoot.contents.append(container)
        container.setParent(newRoot)
        changes[oldRoot.id] = (oldRoot, newRoot)
        comm = modify.UndoCommand(modify.EDITOR, changes, contentsChanged = True, text=self.tr('new container'))
        modify.push(comm)
        
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
    """This dialog is shown if the user requests to merge some children into a new intermediate container."""
    
    def __init__(self, hintTitle, hintRemove, askForPositionAdjusting, parent = None):
        super().__init__(parent)
        layout = QtGui.QGridLayout()
        label = QtGui.QLabel(self.tr('Title of new container:'))
        layout.addWidget(label, 0, 0)
        self.titleEdit = QtGui.QLineEdit(hintTitle)
        layout.addWidget(self.titleEdit, 0, 1)
        self.checkBox = QtGui.QCheckBox(self.tr('Remove from titles:'))
        self.checkBox.setChecked(True)
        layout.addWidget(self.checkBox, 1, 0)
        self.removeEdit = QtGui.QLineEdit(hintRemove)
        layout.addWidget(self.removeEdit, 1, 1)
        self.checkBox.toggled.connect(self.removeEdit.setEnabled)
        
        if askForPositionAdjusting:
            self.positionCheckBox = QtGui.QCheckBox(self.tr('Auto-adjust positions'))
            self.positionCheckBox.setChecked(True)
            layout.addWidget(self.positionCheckBox, 2, 0, 1, 2)
        hLayout = QtGui.QHBoxLayout()
        self.cancelButton = QtGui.QPushButton(self.tr('Cancel'))
        self.okButton = QtGui.QPushButton(self.tr('OK'))
        self.cancelButton.clicked.connect(self.reject)
        self.okButton.clicked.connect(self.accept)
        hLayout.addStretch()
        hLayout.addWidget(self.cancelButton)
        hLayout.addWidget(self.okButton)
        layout.addLayout(hLayout, 3 if askForPositionAdjusting else 2, 0, 1, 2)
        layout.setColumnStretch(1, 1)
        self.setLayout(layout)
    def newTitle(self):
        return self.titleEdit.text()
    def removeString(self):
        return self.removeEdit.text() if self.checkBox.isChecked() else ''
    def adjustPositions(self):
        if hasattr(self, 'positionCheckBox'):
            return self.positionCheckBox.isChecked()
        else:
            return False
