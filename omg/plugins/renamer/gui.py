# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from ... import config, logging
from ...gui import treeview, treeactions, delegates
from ...gui.delegates import abstractdelegate
from ...gui.preferences import profiles as profilesgui
from ...models import leveltreemodel
from ...core import levels
from . import plugin


class RenameFilesAction(treeactions.TreeAction):
    """Action to rename files in a container according to the tags and the container structure."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr("Rename files"))
    
    def initialize(self, selection):
        for fileW in selection.fileWrappers(True):
            if fileW.element.url.CAN_RENAME:
                self.setEnabled(True)
                return
        self.setEnabled(False)
    
    def doAction(self):
        def check(element):
            """Check if all files under this parent can be renamed."""
            for file in element.getAllFiles():
                if not file.url.CAN_RENAME:
                    return False
            return True
        elements = [elem for elem in self.parent().selection.elements() if check(elem)]
        dialog = RenameDialog(self.parent(), self.level(), elements)
        dialog.exec_()
        if dialog.result() == dialog.Accepted:
            try:
                dialog.sublevel.commit()
            except levels.RenameFilesError as e:
                e.displayMessage()


class PathDelegate(delegates.StandardDelegate):
    """Delegate for the rename preview; shows old and new path color-coded.
    """
    def __init__(self, view): 
        # Because it should not be configurable, this profile is not contained in the profile category
        self.profile = delegates.profiles.DelegateProfile("renamer")
        super().__init__(view, self.profile)
        self.newPathStyleNew = abstractdelegate.DelegateStyle(1, False, True, Qt.darkGreen)
        self.newPathStyleOld = abstractdelegate.DelegateStyle(1, False, True, Qt.red)
        self.unchangedStyle = abstractdelegate.DelegateStyle(1, False, True, Qt.gray)
        self.result = {}
        
    def addPath(self, element):
        if element.isFile():
            oldPath = element.inParentLevel().url.path
            newPath = element.url.path
            if oldPath != newPath:
                    self.addCenter(delegates.TextItem(self.tr("From: {}").format(oldPath),
                                                      self.newPathStyleOld))
                    self.newRow()
                    self.addCenter(delegates.TextItem(self.tr("To: {}").format(newPath),
                                                  self.newPathStyleNew))
            else:
                self.addCenter(delegates.TextItem(self.tr("Unchanged: {}").format(oldPath),
                                                  self.unchangedStyle))
            
    
class RenameDialog(QtGui.QDialog):
    """A dialog for pattern-based file renaming.
    
    Shows a tree view with the selected containers, which acts as a preview for renaming. The
    view uses the PathDelegate so that old and new paths of elements are shown.
    
    In the top area of the dialog, the configuration widget is included that can be used to choose one of
    the available grammar profiles and to configure a temporary copy of it. This allows the user to have
    a set of stored profiles and to modify them (their temporary copies actually) without saving as
    necessary for a concrete renaming.
    """
    
    def __init__(self, parent, level, elements):
        super().__init__(parent)
        self.setModal(True)
        elements = list(elements)
        self.level = level
        self.setWindowTitle(self.tr("Rename {} containers").format(len(elements)))
        mainLayout = QtGui.QVBoxLayout()
        
        profile = plugin.profileCategory.getFromStorage(config.storage.renamer.current_profile)
        self.configDisplay = GrammarConfigurationWidget(temporary=True, profile=profile)
        mainLayout.addWidget(self.configDisplay, 1)
        self.configDisplay.temporaryChanged.connect(self._handleTemporaryChanged)
        self.statusLabel = QtGui.QLabel()
        self.statusLabel.setVisible(False)
        f = self.statusLabel.font()
        f.setBold(True)
        pal = self.statusLabel.palette()
        pal.setColor(self.statusLabel.backgroundRole(), Qt.red)
        self.statusLabel.setFont(f)
        self.statusLabel.setAutoFillBackground(True)
        self.statusLabel.setPalette(pal)
        
        self.sublevel = levels.Level("Rename", self.level, elements)
        self.elementsParent = elements
        self.elementsSub = [self.sublevel[element.id] for element in elements]
        self.model = leveltreemodel.LevelTreeModel(self.sublevel, self.elementsSub)
        self.tree = treeview.TreeView(self.sublevel, affectGlobalSelection=False)
        self.tree.setModel(self.model)
        self.delegate = PathDelegate(self.tree)
        self.tree.setItemDelegate(self.delegate)
        self.tree.expandAll()
        
        self.bb = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel | QtGui.QDialogButtonBox.Ok)
        self.bb.accepted.connect(self.checkAccept)
        self.bb.rejected.connect(self.reject)
        
        mainLayout.addWidget(self.tree, 100)
        mainLayout.addWidget(self.statusLabel,1)
        mainLayout.addWidget(self.bb)
        
        self.setLayout(mainLayout)
        self.resize(800,700)
        self._handleTemporaryChanged()
        
    def _handleTemporaryChanged(self):
        """Handle changes to the temporary profile of self.configDisplay."""
        profile = self.configDisplay.tempProfile
        try:
            totalResult = dict()
            for element in self.elementsParent:
                result = profile.renameContainer(self.level, element)
                totalResult.update(result)
            for elem, newPath in totalResult.items():
                if elem.id in self.sublevel:
                    subelem = self.sublevel[elem.id]
                    subelem.url = subelem.url.renamed(newPath)
            if len(set(totalResult.values())) != len(totalResult): # duplicate paths!
                self.bb.button(QtGui.QDialogButtonBox.Ok).setEnabled(False)
                self.statusLabel.setText(self.tr("New paths are not unique! Please fix"))
                self.statusLabel.show()
            else:
                self.statusLabel.hide()
                self.bb.button(QtGui.QDialogButtonBox.Ok).setEnabled(True)
        except plugin.FormatSyntaxError:
            self.statusLabel.setText(self.tr("Syntax error in format string"))
            self.statusLabel.show()
            self.bb.button(QtGui.QDialogButtonBox.Ok).setEnabled(False)
        self.model.modelReset.emit()
        self.tree.expandAll()
    
    def checkAccept(self):
        if self.configDisplay.tempProfile != self.configDisplay.profile \
                    and self.configDisplay.profile is not None:
            from ...gui.dialogs import question
            if question(self.tr("Profile Changed"),
                        self.tr("Save modified profile {}?").format(self.configDisplay.profile.name)):
                self.configDisplay._handleSave()
        self.accept()
    
    
class GrammarConfigurationWidget(QtGui.QWidget):
    """This widget is used in two places to configure grammar profiles:
    
        - as configuration widget of the profiles (and thus used in the standard ProfileDialog),
        - to configure the temporary profile in the RenameDialog. 
       
    Depending on the mode (i.e. the argument *temporary*) the widget looks slightly different: In temporary
    mode, it contains a profileChooser to choose a profile which can then be (temporarily) modified.
    Additionally it contains a menu with actions to save the temporary state.
    If *temporary* is False, the widget will contain two buttons to save or reset the profile.
    """
    temporaryChanged = QtCore.pyqtSignal()
    
    def __init__(self, temporary, profile=None):
        super().__init__()
        self.setMinimumWidth(600)
        self.temporary = temporary
        self.profile = profile
        
        if temporary:
            if profile is not None:
                self.tempProfile = profile.copy()
            else: self.tempProfile = plugin.GrammarRenamer('temp')
        else: self.tempProfile = None
        
        layout = QtGui.QVBoxLayout(self)
        
        if temporary:
            topLayout = QtGui.QHBoxLayout()
            layout.addLayout(topLayout)
            topLayout.addWidget(QtGui.QLabel(self.tr("Choose a profile:")))
            self.profileChooser = profilesgui.ProfileComboBox(plugin.profileCategory)
            self.profileChooser.profileChosen.connect(self.setProfile)
            if profile is not None:
                self.profileChooser.setCurrentProfile(profile)
            topLayout.addWidget(self.profileChooser)
            
            self.menuButton = QtGui.QPushButton(self.tr("Actions"))
            self._makeMenu()
            topLayout.addWidget(self.menuButton)
            topLayout.addStretch(1)
            
        self.edit = QtGui.QTextEdit()
        self.replaceCharsEdit = QtGui.QLineEdit()
        self.replaceByEdit = QtGui.QLineEdit()
        self.removeCharsEdit = QtGui.QLineEdit()
       
        p = self.tempProfile if temporary else self.profile
        if p is not None:
            self.edit.setText(p.formatString)
            self.replaceCharsEdit.setText(p.replaceChars)
            self.replaceByEdit.setText(p.replaceBy)
            self.removeCharsEdit.setText(p.removeChars)
        self.edit.textChanged.connect(self._handleChange)
        for edit in self.replaceCharsEdit, self.replaceByEdit, self.removeCharsEdit:
            edit.textEdited.connect(self._handleChange)
        
        layout.addWidget(self.edit)
        
        hLayout = QtGui.QHBoxLayout()
        layout.addLayout(hLayout)
        hLayout.addWidget(QtGui.QLabel(self.tr("Replace:")))
        hLayout.addWidget(self.replaceCharsEdit)
        hLayout.addWidget(QtGui.QLabel(self.tr("By:")))
        hLayout.addWidget(self.replaceByEdit)
        hLayout.addWidget(QtGui.QLabel(self.tr("And remove:")))
        hLayout.addWidget(self.removeCharsEdit)
            
        if not temporary:
            buttonLayout = QtGui.QHBoxLayout()
            layout.addLayout(buttonLayout)
            saveButton = QtGui.QPushButton(self.tr("Save"))
            saveButton.clicked.connect(self._handleSave)
            buttonLayout.addWidget(saveButton)
            resetButton = QtGui.QPushButton(self.tr("Reset"))
            resetButton.clicked.connect(self._handleReset)
            buttonLayout.addWidget(resetButton)
            buttonLayout.addStretch(1)
    
    def setProfile(self,profile):
        """Set the profile that can be modified by this widget."""
        if profile != self.profile:
            self._setProfile(profile)
            
    def _setProfile(self,profile):
        """As set profile but works also if profile == self.profile (for reset actions)."""
        self.profile = profile
        if self.temporary:
            self.profileChooser.setCurrentProfile(profile)
            # In temporary mode save the selected profile for the next time the RenameDialog is opened.
            config.storage.renamer.current_profile = profile.name
        self.edit.setPlainText(self.profile.formatString)
        self.replaceCharsEdit.setText(self.profile.replaceChars)
        self.replaceByEdit.setText(self.profile.replaceBy)
        self.removeCharsEdit.setText(self.profile.removeChars) 
        # Via _handleChange these lines will also change self.tempProfile
        self._makeMenu()
    
    def _makeMenu(self):
        """Fill the menu (only in temporary mode). This is necessary if the name of the current profile
        changes."""
        menu = QtGui.QMenu()
        if self.profile is not None:
            saveAction = menu.addAction(self.tr("Save as profile {}").format(self.profile.name))
            saveAction.triggered.connect(self._handleSave)
        else:
            saveAction = menu.addAction(self.tr("Save profile"))
            saveAction.setEnabled(False)
        saveAsAction = menu.addAction(self.tr("Save as new profile..."))
        saveAsAction.triggered.connect(self._handleSaveAs)
        if self.profile is not None:
            resetAction = menu.addAction(self.tr("Reset to profile {}").format(self.profile.name))
            resetAction.triggered.connect(self._handleReset)
        else:
            resetAction = menu.addAction(self.tr("Reset profile"))
            resetAction.setEnabled(False)
            
        menu.addSeparator()
        configureAction = menu.addAction(self.tr("Configure profiles..."))
        self.menuButton.setMenu(menu)
        
    def _handleChange(self):
        """Change the temporary profile and emit temporaryChanged (only in temporary mode)."""
        if self.tempProfile is not None:
            self.tempProfile.formatString = self.edit.toPlainText()
            self.tempProfile.replaceChars = self.replaceCharsEdit.text()
            self.tempProfile.replaceBy = self.replaceByEdit.text()
            self.tempProfile.removeChars = self.removeCharsEdit.text()
            self.temporaryChanged.emit()
            
    def _handleSave(self):
        """Handle the save button/action: Save the configuration in the text fields as stored profile."""
        self.profile.formatString = self.edit.toPlainText()
        self.profile.replaceChars = self.replaceCharsEdit.text()
        self.profile.replaceBy = self.replaceByEdit.text()
        self.profile.removeChars = self.removeCharsEdit.text()
        plugin.profileCategory.profileChanged.emit(self.profile)
        
    def _handleSaveAs(self):
        """Save the temporary profile as a stored profile."""
        text,ok = QtGui.QInputDialog.getText(self,
                                     self.tr("Add new profile"),
                                     self.tr("Choose a profile name"),
                                     QtGui.QLineEdit.Normal,
                                     plugin.profileCategory.suggestProfileName())
        if len(text) > 0 and ok:
            if plugin.profileCategory.get(text) is None:
                profile = plugin.profileCategory.addProfile(text,None,self.tempProfile.save())
                self.setProfile(profile)
            else:
                dialogs.warning(self.tr("Invalid name"),self.tr("There is already a profile of this name."))
    
    def _handleReset(self):
        """Reset the text fields to the chosen stored profile."""
        self._setProfile(self.profile)   
