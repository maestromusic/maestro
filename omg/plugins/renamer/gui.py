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

from omg import application
from omg.gui import treeview, treeactions, delegates
from omg.gui.delegates import configuration
from omg.models import editor
from omg.core.commands import CommitCommand
from . import plugin

translate = QtCore.QCoreApplication.translate
class RenameFilesAction(treeactions.TreeAction):
    """Action to rename files in a container according to the tags and the container structure."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr('rename files'))
    
    def initialize(self):
        self.setEnabled(self.parent().nodeSelection.hasElements())
    
    def doAction(self):
        dialog = RenameDialog(self.parent(), self.level(),
                              [wrap.element.id for wrap in self.parent().nodeSelection.elements()])
        dialog.exec_()
        if dialog.result() == dialog.Accepted:
            application.stack.push(CommitCommand(dialog.sublevel, dialog.ids, self.tr("rename")))
            

class PathDelegate(delegates.StandardDelegate):
    """Delegate for the editor."""
    configurationType, defaultConfiguration = configuration.createConfigType(
                'path',
                translate("Delegates","PathRename"),
                delegates.StandardDelegate.options,
                [],
                [],
                {"showPaths": True, 'showMajor': False, 'appendRemainingTags': False, 'showAllAncestors': False}
    )
    
class RenameDialog(QtGui.QDialog):
    def __init__(self, parent, level, ids):
        super().__init__(parent)
        
        self.setModal(True)
        self.ids = ids
        self.level = level
        self.setWindowTitle(self.tr("Rename {} containers").format(len(ids)))
        mainLayout = QtGui.QVBoxLayout()
        
        configDisplay = plugin.profileConfig.configurationDisplay()
        mainLayout.addWidget(configDisplay,1)
        configDisplay.temporaryModified.connect(self._handleTempChange)
        configDisplay.profileChanged.connect(self._handleProfileChange)
        self.statusLabel = QtGui.QLabel()
        mainLayout.addWidget(self.statusLabel, 1)
        self.statusLabel.setVisible(False)
        
        self.sublevel = level.subLevel(ids, "rename")
        self.model = editor.EditorModel(self.sublevel, ids)
        self.tree = treeview.TreeView()
        self.tree.setModel(self.model)
        self.delegate = PathDelegate(self.tree)
        self.tree.setItemDelegate(self.delegate)
        self.tree.expandAll()
        
        if configDisplay.currentProfileName() != '':
            self._handleProfileChange(configDisplay.currentProfileName())
        mainLayout.addWidget(self.tree, 100)
        bb = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel | QtGui.QDialogButtonBox.Ok)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        
        mainLayout.addWidget(bb)
        self.setLayout(mainLayout)
        self.resize(800,500)
    
    def _handleProfileChange(self, name):
        profile = plugin.profileConfig[name]
        self._handleTempChange(profile)
        
    def _handleTempChange(self, renamer):
        """handle changes to the format text edit box"""
        try:
            totalResult = dict()
            for id in self.ids:
                result = renamer.renameContainer(self.level, id)
                totalResult.update(result)
            for id, elem in self.sublevel.elements.items():
                if id in totalResult:
                    elem.path = totalResult[id]
            self.statusLabel.hide()
        except plugin.FormatSyntaxError:
            self.statusLabel.setText(self.tr("Syntax error in format string"))
            self.statusLabel.show()
        self.model.modelReset.emit()
        self.tree.expandAll()
        