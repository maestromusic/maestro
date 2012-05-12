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

from omg.modify import treeactions
from omg import profiles
from omg.gui import treeview, delegates, editor as editorG
from omg.gui.delegates import configuration, editor as editorD
from omg.models import editor
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
        dialog = RenameDialog(self.parent(), self.parent().model().level,
                              [wrap.element.id for wrap in self.parent().nodeSelection.elements()])
        dialog.exec_()

class PathDelegate(delegates.StandardDelegate):
    """Delegate for the editor."""
    
    configurationType, defaultConfiguration = configuration.createConfigType(
                'path',
                translate("Delegates","Rename"),
                delegates.StandardDelegate.options,
                [],
                [],
                {"showPaths": True, 'showMajor': False, 'appendRemainingTags': False, 'showAllAncestors': False}
    )  
class RenameDialog(QtGui.QDialog):
    def __init__(self, parent, level, ids):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(self.tr("Rename {} containers").format(len(ids)))
        mainLayout = QtGui.QVBoxLayout()
        
        mainLayout.addWidget(profiles.ProfileComboBox(plugin.profileConfig))
        
        self.model = editor.EditorModel(level)
        self.model.insertElements(self.model.root, 0, ids)
        self.tree = treeview.TreeView()
        self.tree.setModel(self.model)
        self.tree.expandAll()
        dele = PathDelegate(self.tree)
        self.tree.setItemDelegate(dele)
        mainLayout.addWidget(self.tree)
        bb = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel | QtGui.QDialogButtonBox.Ok)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        
        mainLayout.addWidget(bb)
        self.setLayout(mainLayout)