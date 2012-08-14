# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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
translate = QtCore.QCoreApplication.translate

from . import treeview, mainwindow
from .. import profiles
from ..models import editor as editormodel, albumguesser
from .treeactions import *
from .delegates import editor as editordelegate, configuration as delegateconfig

        
class EditorTreeView(treeview.TreeView):
    """This is the main widget of an editor: The tree view showing the current element tree."""

    actionConfig = treeview.TreeActionConfiguration()
    sect = translate(__name__, "elements")
    actionConfig.addActionDefinition(((sect, 'editTags'),), EditTagsAction, recursive = False)
    actionConfig.addActionDefinition(((sect, 'editTagsR'),), EditTagsAction, recursive = True)
    actionConfig.addActionDefinition(((sect, 'remove'),), DeleteAction, mode = CONTENTS, shortcut = "Del")
    actionConfig.addActionDefinition(((sect, 'merge'),), MergeAction)
    actionConfig.addActionDefinition(((sect, 'major?'),), ToggleMajorAction)
    actionConfig.addActionDefinition(((sect, 'position+'),), ChangePositionAction, mode = "+1")
    actionConfig.addActionDefinition(((sect, 'position-'),), ChangePositionAction, mode = "-1")
    sect = translate(__name__, "editor")
    
    actionConfig.addActionDefinition(((sect, 'clearEditor'),), ClearTreeAction)

    def __init__(self, parent = None):
        super().__init__(levels.editor,parent)
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.setModel(editormodel.EditorModel())
        self.setItemDelegate(editordelegate.EditorDelegate(self))
        self.viewport().setMouseTracking(True)
        

    def dragEnterEvent(self, event):
        if event.source() is self:
            event.setDropAction(Qt.MoveAction)
        else:
            event.setDropAction(Qt.CopyAction)
        event.acceptProposedAction()
        super().dragEnterEvent(event)
        
    def dragMoveEvent(self, event):
        if isinstance(event.source(), EditorTreeView):
            if event.keyboardModifiers() & Qt.ShiftModifier:
                event.setDropAction(Qt.MoveAction)
            elif event.keyboardModifiers() & Qt.ControlModifier:
                event.setDropAction(Qt.CopyAction)
        super().dragMoveEvent(event)
        
    def dropEvent(self, event):
        # workaround due to bug #67
        if event.mouseButtons() & Qt.LeftButton:
            event.ignore()
            return
        if isinstance(event.source(), EditorTreeView):
            if event.keyboardModifiers() & Qt.ShiftModifier:
                event.setDropAction(Qt.MoveAction)
            elif event.keyboardModifiers() & Qt.ControlModifier:
                event.setDropAction(Qt.CopyAction)
            elif event.source() is self:
                event.setDropAction(Qt.MoveAction)
            else:
                event.setDropAction(Qt.CopyAction)
        super().dropEvent(event)
        
    
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
    """The editor is a dock widget for editing elements and their structure. It provides methods to "guess"
    the album structure of new files that are dropped from the filesystem."""
    
    def __init__(self, parent = None, state = None, location = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('editor'))
        widget = QtGui.QWidget()
        self.setWidget(widget)
        vb = QtGui.QVBoxLayout(widget)
        try:
            expand,guessProfile = state
        except:
            expand = True
            guessProfile = None
            
        self.splitter = QtGui.QSplitter(Qt.Vertical)
        vb.addWidget(self.splitter)
        
        self.editor = EditorTreeView()
        self.editor.setAutoExpand(expand)
        
        self.externalTagsWidget = ExternalTagsWidget(self.editor.model())
        
        self.splitter.addWidget(self.externalTagsWidget)
        self.splitter.addWidget(self.editor)
        self.splitter.setStretchFactor(0,0)
        self.splitter.setStretchFactor(1,1)
        
        hb = QtGui.QHBoxLayout()
        vb.addLayout(hb)
        
        self.autoExpandCheckbox = QtGui.QCheckBox(self.tr('auto expand'))
        self.autoExpandCheckbox.setChecked(expand)
        self.autoExpandCheckbox.stateChanged.connect(self.editor.setAutoExpand)
        self.autoExpandCheckbox.setToolTip(self.tr('auto expand dropped containers'))
        hb.addWidget(self.autoExpandCheckbox)
        
        self.guessCheck = QtGui.QCheckBox()
        self.guessProfileCombo = profiles.ProfileComboBox(albumguesser.profileConfig, guessProfile)
        self.guessCheck.toggled.connect(self.guessProfileCombo.setEnabled)
        self.guessCheck.toggled.connect(self._handleProfileCheck)
        self.guessCheck.setChecked(guessProfile is not None)
        self.guessProfileCombo.setDisabled(guessProfile is None)
        if guessProfile is not None:
            self.guessProfileCombo.setCurrentProfile(guessProfile)
        self.editor.model().guessProfile = guessProfile
        self.guessProfileCombo.setToolTip(self.tr("select album guessing profile"))
        self.guessProfileCombo.profileChosen.connect(self._handleProfileCombo)
        
        hb.addWidget(self.guessCheck)
        hb.addWidget(self.guessProfileCombo)
        
        hb.addWidget(QtGui.QLabel(self.tr("Item Display:")))
        hb.addWidget(delegateconfig.ConfigurationCombo(editordelegate.EditorDelegate.configurationType,
                                                       [self.editor]))
        hb.addStretch()
        
        self.toolbar = QtGui.QToolBar(self)
        self.toolbar.addAction(self.editor.treeActions['clearEditor'])
        commitAction = CommitTreeAction(self.editor)
        self.addAction(commitAction)
        self.toolbar.addAction(commitAction)
        hb.addWidget(self.toolbar)

    def _handleProfileCheck(self, state):
        """Handle toggling of the guess checkbox."""
        if state:
            self.editor.model().guessProfile = self.guessProfileCombo.currentProfileName()
        else:
            self.editor.model().guessProfile = None
    
    def _handleProfileCombo(self, name):
        """Handles changes of the current name of the guess profile combobox."""
        self.editor.model().guessProfile = name
    
    def saveState(self):
        if self.guessCheck.isChecked():
            profile = self.guessProfileCombo.currentProfileName()
        else:
            profile = None
        return (self.autoExpandCheckbox.isChecked(),profile)


class ExternalTagsWidget(QtGui.QScrollArea):
    def __init__(self,model):
        super().__init__()
        self.model = model
        model.externalTagInfosChanged.connect(self.updateText)
        
        self.label = QtGui.QLabel()
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setWidget(self.label)
        self.setWidgetResizable(True)
        self.label.setWordWrap(False)
        self.label.setContentsMargins(5,2,5,2)
        
        self.updateText()
    
    def _createButton(self,link,text):
        return '<a href="{}" style="text-decoration:none">[{}]</a>'.format(link,text)
    
    def updateText(self):
        lines = []
        
        for infoList in self.model.externalTagInfos.values():
            for info in infoList:
                if info.type == 'delete':
                    lines.append(self.tr("Tag '{}' was deleted from %n element(s) {} {}",'',
                                                                    info.elementCount())
                                    .format(info.tag.name,
                                            self._createButton('select',self.tr('Select')),
                                            self._createButton('undo',self.tr('Undo'))
                                    ))
                elif info.type == 'replace':
                    lines.append(self.tr("Tag '{}' was replaced by '{}' in %n element(s) {} {}",'',
                                                                    info.elementCount())
                                    .format(info.tag.name,
                                            info.newTag.name,
                                            self._createButton('select',self.tr('Select')),
                                            self._createButton('undo',self.tr('Undo'))
                                    ))
            
                elif info.type == 'unknown':
                    lines.append(self.tr("Unknown tag '{}' found in %n element(s) {} {} {}",'',
                                                                    info.elementCount())
                                    .format(info.tag.name,
                                            self._createButton('select',self.tr('Select')),
                                            self._createButton('add',self.tr('Add to database')),
                                            self._createButton('delete',self.tr('Delete'))
                                    ))
            
        self.label.setText('<br>'.join(lines))
        self.setVisible(len(self.model.externalTagInfos) > 0)


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
