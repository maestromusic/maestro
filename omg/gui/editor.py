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

from collections import OrderedDict
from ..gui import mainwindow
from ..models import editor, Container, Element, RootNode
from . import treeview
from .. import logging, modify, tags
from ..modify import commands
from ..constants import EDITOR


translate = QtCore.QCoreApplication.translate
logger = logging.getLogger("gui.editor")


class EditorTreeView(treeview.TreeView):
    
    level = EDITOR
    
    def __init__(self, parent = None):
        treeview.TreeView.__init__(self, parent)
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.setModel(editor.EditorModel())
        
        self.viewport().setMouseTracking(True)
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
        self.model().dropFromOutside = not isinstance(event.source(), EditorTreeView)
        treeview.TreeView.dropEvent(self, event)
    
    def _expandInsertedRows(self, parent, start, end):
        for row in range(start, end+1):
            child = self.model().index(row, 0, parent)
            self.expand(child)
    
    def setAutoExpand(self, state):
        if state:
            self.model().rowsInserted.connect(self._expandInsertedRows)
        else:
            try:
                self.model().rowsInserted.disconnect(self._expandInsertedRows)
            except TypeError:
                pass # was not connected
               
class EditorWidget(QtGui.QDockWidget):
    def __init__(self, parent = None, state = None, location = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('editor'))
        widget = QtGui.QWidget()
        self.setWidget(widget)
        vb = QtGui.QVBoxLayout(widget)
        try:
            guess, expand = state
        except:
            guess = True
            expand = True
        self.editor = EditorTreeView()
        self.editor.model().setGuessAlbums(guess)
        self.editor.setAutoExpand(expand)
        vb.addWidget(self.editor)
        hb = QtGui.QHBoxLayout()
        vb.addLayout(hb)
        
        self.clearButton = QtGui.QPushButton(self.tr("clear"))
        self.clearButton.clicked.connect(self.editor.model().clear)
        hb.addWidget(self.clearButton)
        
        self.newContainerButton = QtGui.QPushButton(self.tr("new container"))
        self.newContainerButton.clicked.connect(self.newContainerDialog)
        hb.addWidget(self.newContainerButton)
        self.albumGuesserCheckbox = QtGui.QCheckBox(self.tr('guess albums'))
        self.albumGuesserCheckbox.stateChanged.connect(self.editor.model().setGuessAlbums)
        self.albumGuesserCheckbox.setChecked(guess)
        hb.addWidget(self.albumGuesserCheckbox)
        
        self.autoExpandCheckbox = QtGui.QCheckBox(self.tr('auto expand'))
        self.autoExpandCheckbox.setChecked(expand)
        self.autoExpandCheckbox.stateChanged.connect(self.editor.setAutoExpand)
        self.autoExpandCheckbox.setToolTip(self.tr('auto expand dropped containers'))
        hb.addWidget(self.autoExpandCheckbox)
        
        hb.addStretch()
        self.commitButton = QtGui.QPushButton(self.tr('commit'))
        hb.addWidget(self.commitButton)
        self.commitButton.clicked.connect(modify.commitEditors)

    
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
        return (self.albumGuesserCheckbox.isChecked(), self.autoExpandCheckbox.isChecked())
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

def activeEditorModels():
    """Returns a list containing the models of all open editor models."""
    return [dock.editor.model() for dock in mainwindow.mainWindow.getWidgets('editor')]
    