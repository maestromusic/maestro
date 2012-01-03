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

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from .. import models
from ..models.rootedtreemodel import RootedTreeModel, RootNode
from ..gui import mainwindow, treeview

class MissingFilesDialog(QtGui.QDialog):
    """A dialog that notifies the user about missing files.
    
    When OMG detects that files were deleted from outside OMG, this
    dialog is shown which asks what to do, i.e., decide which of
    the missing elements should also be deleted from the database. If
    this leads to empty containers, the user is asked if they should
    be removed, too.
    """
    def __init__(self, paths):
        super().__init__(mainwindow.mainWindow)
        self.setModal(True)
        self.model = RootedTreeModel(RootNode())
        elements = [ models.File.fromFilesystem(path) for path in sorted(paths)]
        self.model.root.setContents(elements)
        
        self.treeview = treeview.TreeView()
        self.treeview.setModel(self.model)
        
        
        layout = QtGui.QVBoxLayout()
        layout.addWidget(self.treeview)
        buttonLayout = QtGui.QHBoxLayout()
        
        self.cancelButton = QtGui.QPushButton(self.tr('Cancel'))
        self.deleteSelectedButton = QtGui.QPushButton(self.tr('Delete selected'))
        buttonLayout.addStretch()
        buttonLayout.addWidget(self.cancelButton)
        buttonLayout.addWidget(self.deleteSelectedButton)
        
        self.cancelButton.clicked.connect(self.reject)
        layout.addLayout(buttonLayout)
        self.setLayout(layout)
        self.exec_()