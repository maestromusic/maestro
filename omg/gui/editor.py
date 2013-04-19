# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

from . import treeactions, treeview, mainwindow, tagwidgets, dialogs, profiles as profilesgui, delegates
from .. import utils
from ..core import levels, tags
from ..models import albumguesser
from ..models.editor import EditorModel
from .delegates import editor as editordelegate

        
class EditorTreeView(treeview.DraggingTreeView):
    """This is the main widget of an editor: The tree view showing the current element tree."""

    actionConfig = treeview.TreeActionConfiguration()
    sect = translate("EditorTreeView", "elements")
    actionConfig.addActionDefinition(((sect, 'editTags'),), treeactions.EditTagsAction, recursive=False)
    actionConfig.addActionDefinition(((sect, 'editTagsR'),), treeactions.EditTagsAction, recursive=True)
    actionConfig.addActionDefinition(((sect, 'remove'),), treeactions.RemoveFromParentAction)
    actionConfig.addActionDefinition(((sect, 'merge'),), treeactions.MergeAction)
    #actionConfig.addActionDefinition(((sect, 'major?'),), treeactions.ToggleMajorAction)
    actionConfig.addActionDefinition(((sect, 'position+'),), treeactions.ChangePositionAction, mode="+1")
    actionConfig.addActionDefinition(((sect, 'position-'),), treeactions.ChangePositionAction, mode="-1")
    sect = translate("EditorTreeView", "editor")
    
    actionConfig.addActionDefinition(((sect, 'clearEditor'),), treeactions.ClearTreeAction)
    actionConfig.addActionDefinition(((sect, 'commit'),), treeactions.CommitTreeAction)

    def __init__(self, delegateProfile):
        super().__init__(levels.editor)
        self.setModel(EditorModel())
        self.setItemDelegate(editordelegate.EditorDelegate(self, delegateProfile))
        self.autoExpand = True
        self.model().rowsInserted.connect(self._expandInsertedRows)
       
    def _expandInsertedRows(self, parent, start, end):
        if self.autoExpand:
            for row in range(start, end+1):
                child = self.model().index(row, 0, parent)
                self.expand(child)

    
class EditorWidget(mainwindow.DockWidget):
    """The editor is a dock widget for editing elements and their structure. It provides methods to "guess"
    the album structure of new files that are dropped from the filesystem."""
    def __init__(self, parent=None, state=None, location=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('Editor'))
        widget = QtGui.QWidget()
        self.setWidget(widget)
        layout = QtGui.QVBoxLayout(widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        
        if state is None:
            state = {}
        expand = 'expand' not in state or state['expand'] # by default expand
        guessingEnabled = 'guessingEnabled' not in state or state['guessingEnabled'] # by default guess 
        guessProfile = albumguesser.profileCategory.getFromStorage(state.get('guessProfile'))
        delegateProfile = delegates.profiles.category.getFromStorage(
                                                    state.get('delegate'),
                                                    editordelegate.EditorDelegate.profileType)
        
        buttonLayout = QtGui.QHBoxLayout()
        # buttonLayout is filled below, when the editor exists 
        layout.addLayout(buttonLayout)
        
        self.splitter = QtGui.QSplitter(Qt.Vertical)
        layout.addWidget(self.splitter)
        
        self.editor = EditorTreeView(delegateProfile)
        self.editor.autoExpand = expand
        self.editor.model().guessingEnabled = guessingEnabled
        self.editor.model().guessProfile = guessProfile
        
        self.externalTagsWidget = ExternalTagsWidget(self.editor)
        
        self.splitter.addWidget(self.externalTagsWidget)
        self.splitter.addWidget(self.editor)
        self.splitter.setStretchFactor(0,0)
        self.splitter.setStretchFactor(1,1)
        
        # Fill buttonLayout
        self.toolbar = QtGui.QToolBar(self)
        self.toolbar.addAction(self.editor.treeActions['clearEditor'])
        
        self.toolbar.addAction(self.editor.treeActions["commit"])
        buttonLayout.addWidget(self.toolbar)
        buttonLayout.addStretch()
        self.newStreamButton = QtGui.QPushButton("HTTP")
        buttonLayout.addWidget(self.newStreamButton)
        self.newStreamButton.clicked.connect(self._handleNewStreamButton)
        
        self.optionButton = QtGui.QToolButton()
        self.optionButton.setIcon(utils.getIcon('options.png'))
        self.optionButton.setIconSize(QtCore.QSize(14, 14))
        self.optionButton.clicked.connect(self._handleOptionButton)
        self.addTitleWidget(self.optionButton)

    def _handleNewStreamButton(self):
        url, ok = QtGui.QInputDialog.getText(self, "stream", "URL:")
        if not ok or not url.startswith("http://"):
            return
        from ..filebackends import BackendURL
        url = BackendURL.fromString(url)
        elem = self.editor.level.collect(url)
        model = self.editor.model()
        model.insertElements(model.root, len(model.root.contents), [elem])
    
    def _handleOptionButton(self):
        """Open the option dialog."""
        dialog = OptionDialog(self.optionButton,self.editor)
        dialog.show()
        
    def saveState(self):
        guessProfile = self.editor.model().guessProfile
        return {'expand': self.editor.autoExpand,
                'guessingEnabled': self.editor.model().guessingEnabled,
                'guessProfile': guessProfile.name if guessProfile is not None else None, 
                'delegate': self.editor.itemDelegate().profile.name # a delegate's profile is never None
                }
    
    def okToClose(self):
        if self.editor.model().containsUncommitedData():
            return dialogs.question(self.tr("Unsaved changes"),
                self.tr("The editor contains uncommited changes. Really close?"))
        return True


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
        albumGuessCheckBox.setChecked(self.editor.model().guessingEnabled)
        albumGuessCheckBox.setToolTip(self.tr("Auto expand dropped containers"))
        albumGuessCheckBox.toggled.connect(self._handleAlbumGuessCheckBox)
        albumGuessLayout.addWidget(albumGuessCheckBox)
        
        self.albumGuessComboBox = profilesgui.ProfileComboBox(albumguesser.profileCategory,
                                                              default=self.editor.model().guessProfile)
        self.albumGuessComboBox.setToolTip(self.tr("Select album guessing profile"))
        self._handleAlbumGuessCheckBox(albumGuessCheckBox.isChecked()) # initialize enabled/disabled
        self.albumGuessComboBox.profileChosen.connect(self._handleAlbumGuessComboBox)
        albumGuessLayout.addWidget(self.albumGuessComboBox,1)
        layout.addRow(self.tr("Guess albums"),albumGuessLayout)
        
        delegateType = editordelegate.EditorDelegate.profileType
        delegateChooser = profilesgui.ProfileComboBox(delegates.profiles.category,
                                                     restrictToType=delegateType,
                                                     default=self.editor.itemDelegate().profile)
        delegateChooser.profileChosen.connect(self.editor.itemDelegate().setProfile)
        layout.addRow(self.tr("Item display"),delegateChooser)
        
    def _handleAutoExpandBox(self,state):
        """Handle toggling the auto expand checkbox."""
        self.editor.autoExpand = state == Qt.Checked
        
    def _handleAlbumGuessCheckBox(self,checked):
        """Handle toggling of the guess checkbox."""
        self.editor.model().guessingEnabled = checked
        if len(albumguesser.profileCategory.profiles) > 0:
            self.albumGuessComboBox.setEnabled(checked)
        else: self.albumGuessComboBox.setEnabled(True) # the box contains only 'Configure...'
        
    def _handleAlbumGuessComboBox(self,profile):
        """Handles changes of the current name of the guess profile combobox."""
        self.editor.model().guessProfile = profile
    

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
            levels.editor.changeTags({el: tags.SingleTagDifference(info.tag,removals=el.tags[info.tag])
                                      for el in info.elements})
        elif action == 'undo':
            self.editor.model().undoExtTagInfo(info)
        elif action == 'select':
            # Construct a QItemSelection storing the whole selection and add it to the model at once.
            # Otherwise a selectionChanged signal would be emitted after each selected wrapper. 
            itemSelection = QtGui.QItemSelection()
            for wrapper in self.editor.model().getAllNodes():
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
