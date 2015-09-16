# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from maestro import logging, profiles
from maestro.gui import actions, treeview, delegates
from maestro.gui.delegates import abstractdelegate
from maestro.gui.preferences import profiles as profileprefs
from maestro.models import leveltreemodel
from maestro.core import levels
from . import plugin


class RenameFilesAction(actions.TreeAction):
    """Action to rename files in a container according to the tags and the container structure."""

    label = translate('RenameFilesAction', 'Rename files by pattern')
    
    def doAction(self):
        elements = self.parent().selection.elements()
        dialog = RenameDialog(self.parent(), self.level(), elements)
        if dialog.exec_():
            try:
                dialog.sublevel.commit()
            except levels.RenameFilesError as e:
                e.displayMessage()


class PathDelegate(delegates.StandardDelegate):
    """Delegate for the rename preview; shows old and new path color-coded.
    """
    def __init__(self, view): 
        # Because it should not be configurable, this profile is not contained in the profile category
        self.profile = delegates.profiles.DelegateProfile('renamer')
        super().__init__(view, self.profile)
        self.newPathStyleNew = abstractdelegate.DelegateStyle(1, False, True, Qt.darkGreen)
        self.newPathStyleOld = abstractdelegate.DelegateStyle(1, False, True, Qt.red)
        self.unchangedStyle = abstractdelegate.DelegateStyle(1, False, True, Qt.gray)
        self.result = {}
        
    def addPath(self, element):
        if element.isFile():
            if not element.inParentLevel():
                logging.warning(__name__, '{} not in parent level'.format(element))
                return
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
            
    
class RenameDialog(QtWidgets.QDialog):
    """A dialog for pattern-based file renaming.
    
    Shows a tree view with the selected containers, which acts as a preview for renaming. The
    view uses the PathDelegate so that old and new paths of elements are shown.
    
    Uses ProfileActionWidget in the top area to allow temporary changes to renamer profiles.
    """
    
    def __init__(self, parent, level, elements):
        super().__init__(parent)
        self.setModal(True)
        elements = list(elements)
        self.level = level
        self.setWindowTitle(self.tr("Rename {} containers").format(len(elements)))
        mainLayout = QtWidgets.QVBoxLayout()

        self.profileActionWidget = profileprefs.ProfileActionWidget('renamer')
        mainLayout.addWidget(self.profileActionWidget, 1)
        self.statusLabel = QtWidgets.QLabel()
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
        self.tree.setItemDelegate(PathDelegate(self.tree))
        self.tree.expandAll()
        
        self.bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Ok)
        self.bb.accepted.connect(self.checkAccept)
        self.bb.rejected.connect(self.reject)
        
        mainLayout.addWidget(self.tree, 100)
        mainLayout.addWidget(self.statusLabel, 1)
        mainLayout.addWidget(self.bb)
        
        self.setLayout(mainLayout)
        self.resize(800, 700)
        self.previewProfile = None
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.updatePreview)
        self.timer.start(1000)

    def updatePreview(self):
        profile = self.profileActionWidget.profile
        if profile != self.previewProfile:
            try:
                totalResult = dict()
                for element in self.elementsParent:
                    result = profile.renameContainer(self.level, element)
                    totalResult.update(result)
                for elem, newPath in totalResult.items():
                    if elem.id in self.sublevel:
                        subelem = self.sublevel[elem.id]
                        subelem.url = subelem.url.copy(path=newPath)
                if len(set(totalResult.values())) != len(totalResult): # duplicate paths!
                    self.bb.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)
                    self.statusLabel.setText(self.tr("New paths are not unique! Please fix"))
                    self.statusLabel.show()
                else:
                    self.statusLabel.hide()
                    self.bb.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(True)
            except plugin.FormatSyntaxError:
                self.statusLabel.setText(self.tr("Syntax error in format string"))
                self.statusLabel.show()
                self.bb.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)
            self.model.modelReset.emit()
            self.tree.expandAll()
            self.previewProfile = profile.copy()
    
    def checkAccept(self):
        self.profileActionWidget.askSaveIfModified()
        self.accept()


class GrammarConfigurationWidget(profileprefs.ProfileConfigurationWidget):
    """This widget is used in two places to configure grammar profiles:
    
        - as configuration widget of the profiles (and thus used in the standard ProfileDialog),
        - to configure the temporary profile in the RenameDialog.
    """
    
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.setMinimumWidth(600)
        layout = QtWidgets.QVBoxLayout(self)

        self.formatEdit = QtWidgets.QTextEdit()
        self.replaceCharsEdit = QtWidgets.QLineEdit()
        self.replaceByEdit = QtWidgets.QLineEdit()
        self.removeCharsEdit = QtWidgets.QLineEdit()

        self.setProfile(profile)
        self.formatEdit.textChanged.connect(self.updateProfile)
        for edit in self.replaceCharsEdit, self.replaceByEdit, self.removeCharsEdit:
            edit.textEdited.connect(self.updateProfile)
        
        layout.addWidget(self.formatEdit)
        
        hLayout = QtWidgets.QHBoxLayout()
        layout.addLayout(hLayout)
        hLayout.addWidget(QtWidgets.QLabel(self.tr("Replace:")))
        hLayout.addWidget(self.replaceCharsEdit)
        hLayout.addWidget(QtWidgets.QLabel(self.tr("By:")))
        hLayout.addWidget(self.replaceByEdit)
        hLayout.addWidget(QtWidgets.QLabel(self.tr("And remove:")))
        hLayout.addWidget(self.removeCharsEdit)

    def updateProfile(self):
        self.profile.formatString = self.formatEdit.toPlainText()
        self.profile.replaceChars = self.replaceCharsEdit.text()
        self.profile.replaceBy = self.replaceByEdit.text()
        self.profile.removeChars = self.removeCharsEdit.text()

    def setProfile(self, profile):
        """Set the profile that can be modified by this widget."""
        self.profile = profile
        self.formatEdit.setText(profile.formatString)
        self.replaceCharsEdit.setText(profile.replaceChars)
        self.replaceByEdit.setText(profile.replaceBy)
        self.removeCharsEdit.setText(profile.removeChars)
