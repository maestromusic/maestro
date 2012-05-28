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

import itertools

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from .. import application, constants, database as db, utils
from ..core import commands, levels, elements
from .. import models
from ..models.rootedtreemodel import RootedTreeModel, RootNode
from ..gui import mainwindow, treeview
from ..gui.delegates.editor import EditorDelegate


class MissingFilesDialog(QtGui.QDialog):
    """A dialog that notifies the user about missing files.
    
    When OMG detects that files were deleted from outside OMG, this
    dialog is shown which asks what to do, i.e., decide which of
    the missing elements should also be deleted from the database. If
    this leads to empty containers, the user is asked if they should
    be removed, too.
    """
    def __init__(self, ids):
        """Open the dialog for the files given by *ids*, a list of file IDs."""
        super().__init__(mainwindow.mainWindow)
        self.setModal(True)
        self.setWindowTitle(self.tr('Detected Missing Files'))
        layout = QtGui.QVBoxLayout()
        label = QtGui.QLabel(self.tr("The following files were removed from the filesystem with another program. "
                             "Please select those that should also be removed from OMG's database, and "
                             "provide a new path for the others."))
        label.setWordWrap(True)
        layout.addWidget(label)
        self.filemodel = RootedTreeModel(levels.real)
        
        elements = [ levels.real.get(id) for id in sorted(ids)]
        self.candidateContainers = []
        for pid in set(itertools.chain(*(element.parents for element in elements))):
            container = levels.real.get(pid)
            if all (cid in ids for cid in container.contents.ids):
                self.candidateContainers.append(container)
        self.filemodel.root.setContents(elements)
        
        self.fileview = treeview.TreeView()        
        self.fileview.setModel(self.filemodel)
        self.fileview.setItemDelegate(EditorDelegate(self.fileview, EditorDelegate.defaultConfiguration))
        self.fileview.selectionModel().selectionChanged.connect(self.updateEmptyContainers)
        self.fileview.doubleClicked.connect(self.startFileSelection)
        layout.addWidget(self.fileview)
        
        label = QtGui.QLabel(self.tr("After deleting those files, the following containers will be empty. "
                                     "Please select which of them are also to be deleted."))
        label.setWordWrap(True)
        layout.addWidget(label)
        self.containermodel = RootedTreeModel(levels.real)
        self.containerview = treeview.TreeView()
        self.containerview.setModel(self.containermodel)
        self.containerview.setItemDelegate(EditorDelegate(self.fileview, EditorDelegate.defaultConfiguration))
        layout.addWidget(self.containerview)
        buttonLayout = QtGui.QHBoxLayout()
        
        self.cancelButton = QtGui.QPushButton(self.tr('Cancel'))
        self.deleteButton = QtGui.QPushButton(self.tr('Delete selected'))
        buttonLayout.addStretch()
        buttonLayout.addWidget(self.cancelButton)
        buttonLayout.addWidget(self.deleteButton)
        
        self.cancelButton.clicked.connect(self.reject)
        self.deleteButton.clicked.connect(self.deleteElements)
        layout.addLayout(buttonLayout)
        self.setLayout(layout)
        self.resize(400,600)
        self.exec_()
        
    def deleteElements(self):
        files = self.fileview.nodeSelection.elements()
        containers = self.containerview.nodeSelection.elements()
        application.push(commands.RemoveElementsCommand(constants.REAL, files + containers, constants.DB,
                                                        self.tr('remove deleted files from DB')))
        self.accept()
        
    def startFileSelection(self, index):
        import os
        file = index.internalPointer()
        newPath = utils.relPath(QtGui.QFileDialog.getOpenFileName(self, self.tr("Select new file location"),
                                                    utils.absPath(os.path.dirname(file.path))))
        if newPath != "":
            db.write.changeFilePath(file.id, newPath)
            self.filemodel.remove(self.filemodel.root, [file.iPosition()])
            

    def updateEmptyContainers(self, *args):
        selectedFileIds = [elem.id for elem in self.fileview.nodeSelection.elements()]
        root = self.containermodel.root
        for container in self.candidateContainers:
            empty = all( id in selectedFileIds for id in container.check_ids)
            index = root.find(container, True)
            if empty and index == -1:
                self.containermodel.insert(root,  [(len(root.contents), container)])
            elif (not empty) and index >= 0:
                self.containermodel.remove(root, [index] )
                
            