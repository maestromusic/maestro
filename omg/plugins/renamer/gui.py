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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg.gui import treeview, treeactions, delegates
from omg.gui.delegates import configuration, abstractdelegate
from omg.models import leveltreemodel
from omg.core.levels import RenameFilesError
from . import plugin

translate = QtCore.QCoreApplication.translate

class RenameFilesAction(treeactions.TreeAction):
    """Action to rename files in a container according to the tags and the container structure."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr('rename files'))
    
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
        elements = [elem for elem in self.parent().nodeSelection.elements() if check(elem)]
        dialog = RenameDialog(self.parent(), self.level(), elements)
        dialog.exec_()
        if dialog.result() == dialog.Accepted:
            try:
                dialog.sublevel.commit()
            except RenameFilesError as e:
                e.displayMessage()


class PathDelegate(delegates.StandardDelegate):
    """Delegate for the rename preview; shows old and new path color-coded.
    """
    
    configurationType, defaultConfiguration = configuration.createConfigType(
                'path',
                translate("Delegates","PathRename"),
                delegates.StandardDelegate.options,
                [],
                [],
                {"showPaths": True, 'showMajor': False, 
                 'appendRemainingTags': False, 'showAllAncestors': False,
                 'showFlagIcons' : False}
    )
    
    def __init__(self, view): 
        super().__init__(view) 
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
    
    In the top area of the dialog, the configuration widget for renaming profiles is included.
    """
    
    def __init__(self, parent, level, elements):
        super().__init__(parent)
        self.setModal(True)
        elements = list(elements)
        self.level = level
        self.setWindowTitle(self.tr("Rename {} containers").format(len(elements)))
        mainLayout = QtGui.QVBoxLayout()
        
        configDisplay = plugin.profileConfig.configurationDisplay()
        mainLayout.addWidget(configDisplay,1)
        configDisplay.temporaryModified.connect(self._handleTempChange)
        configDisplay.profileChanged.connect(self._handleProfileChange)
        self.statusLabel = QtGui.QLabel()
        self.statusLabel.setVisible(False)
        f = self.statusLabel.font()
        f.setBold(True)
        pal = self.statusLabel.palette()
        pal.setColor(self.statusLabel.backgroundRole(), Qt.red)
        self.statusLabel.setFont(f)
        self.statusLabel.setAutoFillBackground(True)
        self.statusLabel.setPalette(pal)
        
        self.sublevel = level.subLevel(elements, "rename")
        self.elementsParent = elements
        self.elementsSub = [self.sublevel.get(element.id) for element in elements]
        self.model = leveltreemodel.LevelTreeModel(self.sublevel, self.elementsSub)
        self.tree = treeview.TreeView(self.sublevel,affectGlobalSelection=False)
        self.tree.setModel(self.model)
        self.delegate = PathDelegate(self.tree)
        self.tree.setItemDelegate(self.delegate)
        self.tree.expandAll()
        
        self.bb = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel | QtGui.QDialogButtonBox.Ok)
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)
        
        if configDisplay.currentProfileName() != '':
            self._handleProfileChange(configDisplay.currentProfileName())
        mainLayout.addWidget(self.tree, 100)
        mainLayout.addWidget(self.statusLabel,1)
        mainLayout.addWidget(self.bb)
        
        self.setLayout(mainLayout)
        self.resize(800,700)
    
    def _handleProfileChange(self, name):
        profile = plugin.profileConfig[name]
        self._handleTempChange(profile)
        
    def _handleTempChange(self, renamer):
        """handle changes to the format text edit box"""
        try:
            totalResult = dict()
            for element in self.elementsParent:
                result = renamer.renameContainer(self.level, element)
                totalResult.update(result)
            for elem, newPath in totalResult.items():
                if elem.id in self.sublevel:
                    subelem = self.sublevel.get(elem.id)
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
        
