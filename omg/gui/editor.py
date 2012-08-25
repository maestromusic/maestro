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

from . import treeview, mainwindow, tagwidgets, dialogs
from .. import profiles, application
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
        self.autoExpand = True
        self.model().rowsInserted.connect(self._expandInsertedRows)

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
        if self.autoExpand:
            for row in range(start, end+1):
                child = self.model().index(row, 0, parent)
                self.expand(child)

        
class EditorWidget(QtGui.QDockWidget):
    """The editor is a dock widget for editing elements and their structure. It provides methods to "guess"
    the album structure of new files that are dropped from the filesystem."""
    def __init__(self, parent = None, state = None, location = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('Editor'))
        widget = QtGui.QWidget()
        self.setWidget(widget)
        layout = QtGui.QVBoxLayout(widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        
        try:
            expand,guessProfile = state
        except:
            expand = True
            guessProfile = None
        
        buttonLayout = QtGui.QHBoxLayout()
        # buttonLayout is filled below, when the editor exists 
        layout.addLayout(buttonLayout)
        
        self.splitter = QtGui.QSplitter(Qt.Vertical)
        layout.addWidget(self.splitter)
        
        self.editor = EditorTreeView()
        self.editor.autoExpand = expand
        self.editor.model().guessProfile = guessProfile
        
        self.externalTagsWidget = ExternalTagsWidget(self.editor)
        
        self.splitter.addWidget(self.externalTagsWidget)
        self.splitter.addWidget(self.editor)
        self.splitter.setStretchFactor(0,0)
        self.splitter.setStretchFactor(1,1)
        
        # Fill buttonLayout
        self.toolbar = QtGui.QToolBar(self)
        self.toolbar.addAction(self.editor.treeActions['clearEditor'])
        commitAction = CommitTreeAction(self.editor)
        self.addAction(commitAction)
        self.toolbar.addAction(commitAction)
        buttonLayout.addWidget(self.toolbar)
        
        buttonLayout.addStretch()
        
        self.optionButton = QtGui.QPushButton()
        self.optionButton.setIcon(utils.getIcon('options.png'))
        self.optionButton.clicked.connect(self._handleOptionButton)
        buttonLayout.addWidget(self.optionButton)

    def _handleOptionButton(self):
        """Open the option dialog."""
        dialog = OptionDialog(self.optionButton,self.editor)
        dialog.show()
        
    def saveState(self):
        return (self.editor.autoExpand, self.editor.model().guessProfile)


class OptionDialog(dialogs.FancyPopup):
    """Option dialog for an Editor."""
    def __init__(self,parent,editor):
        super().__init__(parent)
        self.editor = editor
        layout = QtGui.QFormLayout(self)
        
        autoExpandBox = QtGui.QCheckBox()
        autoExpandBox.setChecked(editor.autoExpand)
        autoExpandBox.stateChanged.connect(self._handleAutoExpandBox)
        layout.addRow(self.tr("Auto expand"),autoExpandBox)
        
        albumGuessLayout = QtGui.QHBoxLayout()
        albumGuessCheckBox = QtGui.QCheckBox()
        albumGuessCheckBox.setChecked(self.editor.model().guessProfile is not None)
        albumGuessCheckBox.setToolTip(self.tr("Auto expand dropped containers"))
        albumGuessCheckBox.toggled.connect(self._handleAlbumGuessCheckBox)
        # the checkbox will also be connected to control the combobox' visibility 
        albumGuessLayout.addWidget(albumGuessCheckBox)
        
        self.albumGuessComboBox = profiles.ProfileComboBox(albumguesser.profileConfig,
                                                           self.editor.model().guessProfile)
        self.albumGuessComboBox.setToolTip(self.tr("Select album guessing profile"))
        self.albumGuessComboBox.setDisabled(self.editor.model().guessProfile is None)
        albumGuessCheckBox.toggled.connect(self.albumGuessComboBox.setEnabled)
        self.albumGuessComboBox.profileChosen.connect(self._handleAlbumGuessComboBox)
        albumGuessLayout.addWidget(self.albumGuessComboBox,1)
        layout.addRow(self.tr("Guess albums"),albumGuessLayout)
        
        itemDisplayCombo = delegateconfig.ConfigurationCombo(editordelegate.EditorDelegate.configurationType,
                                                             [self.editor])
        layout.addRow(self.tr("Item display"),itemDisplayCombo)
        
    def _handleAutoExpandBox(self,state):
        """Handle toggling the auto expand checkbox."""
        self.editor.autoExpand = state == Qt.Checked
        
    def _handleAlbumGuessCheckBox(self,checked):
        """Handle toggling of the guess checkbox."""
        self.editor.model().guessProfile = self.albumGuessComboBox.currentProfileName() if checked else None
        
    def _handleAlbumGuessComboBox(self,name):
        """Handles changes of the current name of the guess profile combobox."""
        self.editor.model().guessProfile = name
    

class ExternalTagsWidget(QtGui.QScrollArea):
    """This widget displays information about external tags in the editor (including automatically performed
    tag processing)."""
    def __init__(self,editor):
        super().__init__()
        self.editor = editor
        self.editor.model().extTagInfosChanged.connect(self.updateText)
        
        self.label = QtGui.QLabel()
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setWidget(self.label)
        self.setWidgetResizable(True)
        self.label.setWordWrap(False)
        self.label.setContentsMargins(5,2,5,2)
        self.label.linkActivated.connect(self._handleLink)
        
        self.updateText()
    
    def _createLink(self,index,action,text):
        """Create an HTML-link."""
        return '<a href="{}:{}" style="text-decoration:none">[{}]</a>'.format(action,index,text)
    
    def updateText(self):
        lines = []
        
        for i,info in enumerate(self.editor.model().extTagInfos):
            if info.type == 'deleted':
                lines.append(self.tr("Tag '{}' was deleted from %n element(s) {} {}",'',len(info.elements))
                                .format(info.tag.name,
                                        self._createLink(i,'select',self.tr('Select')),
                                        self._createLink(i,'undo',self.tr('Undo'))
                                ))
            elif info.type == 'replaced':
                lines.append(self.tr("Tag '{}' was replaced by '{}' in %n element(s) {} {}",'',
                                                               len(info.elements))
                                .format(info.tag.name,
                                        info.newTag.name,
                                        self._createLink(i,'select',self.tr('Select')),
                                        self._createLink(i,'undo',self.tr('Undo'))
                                ))
        
            elif info.type == 'external':
                lines.append(self.tr("External tag '{}' found in %n element(s) {} {} {}",'',
                                                                len(info.elements))
                                .format(info.tag.name,
                                        self._createLink(i,'select',self.tr('Select')),
                                        self._createLink(i,'add',self.tr('Add to database')),
                                        self._createLink(i,'delete',self.tr('Delete'))
                                ))
            
        self.label.setText('<br>'.join(lines))
        self.setHidden(len(lines) == 0)
        
    def _handleLink(self,link):
        """Handle a link in the text."""
        action, index = link.split(':',1)
        index = int(index)
        info = self.editor.model().extTagInfos[index]
        
        if action == 'add':
            tagwidgets.AddTagTypeDialog.addTagType(info.tag)
        elif action == 'delete':
            levels.editor.removeTag(info.tag,info.elements)
        elif action == 'undo':
            self.editor.model().undoExtTagInfo(info)
        elif action == 'select':
            # Construct a QItemSelection storing the whole selection and add it to the model at once.
            # Otherwise a selectionChanged signal would be emitted after each selected wrapper. 
            itemSelection = QtGui.QItemSelection()
            for wrapper in self.editor.model().root.getAllNodes(skipSelf=True):
                if wrapper.element in info.elements:
                    index = self.editor.model().getIndex(wrapper)
                    itemSelection.select(index,index)
            self.editor.selectionModel().select(itemSelection,QtGui.QItemSelectionModel.ClearAndSelect)       


# register this widget in the main application
widgetData = mainwindow.WidgetData(id = "editor",
                             name = translate("Editor","editor"),
                             theClass = EditorWidget,
                             central = True,
                             dock = True,
                             default = True,
                             unique = False,
                             preferredDockArea = Qt.RightDockWidgetArea)
mainwindow.addWidgetData(widgetData)
