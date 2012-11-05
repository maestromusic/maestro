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

from .. import application
from ..core import levels, tags
from ..models.leveltreemodel import LevelTreeModel
from ..gui import delegates, treeactions, treeview
from ..gui.delegates import abstractdelegate, editor as editordelegate

import os.path

translate = QtCore.QCoreApplication.translate


class LostFilesDelegate(delegates.StandardDelegate):
    
    def __init__(self, view):
        self.profile = delegates.profiles.DelegateProfile("lostfiles") 
        super().__init__(self.profile)
        self.options['showPaths'] = True
        self.options['showMajer'] = False
        self.options['appendRemainingTags'] = False
        self.options['showAllAncestors'] = True
        self.options['showFlagIcons'] = True
        self.goodPathStyle = abstractdelegate.DelegateStyle(1, False, True, Qt.darkGreen)
        self.badPathStyle = abstractdelegate.DelegateStyle(1, False, True, Qt.red)
        
    def addPath(self, element):
        if element.isFile():
            if os.path.exists(element.url.absPath):
                style = self.goodPathStyle
            else:
                style = self.badPathStyle
            self.addCenter(delegates.TextItem(element.url.path, style))


class SetPathAction(treeactions.TreeAction):
    """Action to rename (or move) a file."""
    
    def __init__(self, parent, text=None, shortcut=None):
        super().__init__(parent, shortcut)
        if text is None:
            self.setText(self.tr('choose path'))
        else:
            self.setText(text)
    
    def initialize(self, selection):
        self.setEnabled(selection.singleWrapper() and \
                        selection.hasFiles() and \
                        not os.path.exists(next(selection.fileWrappers()).element.url.absPath))
    
    def doAction(self):
        """Open a dialog to edit the tags of the currently selected elements (and the children, if
        *recursive* is True). This is called by the edit tags actions in the contextmenu.
        """
        from ..filebackends.filesystem import FileURL
        elem = next(self.parent().nodeSelection.fileWrappers()).element
        path = QtGui.QFileDialog.getOpenFileName(application.mainWindow,
                                                 self.tr("Select new file location"),
                                                 os.path.dirname(elem.url.absPath))
        if path != "":
            newUrl = FileURL(path)
            from .. import database as db
            from ..database import write
            print('changing url: {}->{}'.format(elem.url, newUrl))
            db.write.changeUrls([ (str(newUrl), elem.id) ])
            elem.url = newUrl
            levels.real.emitEvent([elem.id])


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
        super().__init__(application.mainWindow)
        self.setModal(True)
        self.setWindowTitle(self.tr('Missing Files Detected'))
        layout = QtGui.QVBoxLayout()
        label = QtGui.QLabel(self.tr(
                    "The following files were removed from the filesystem by another program. "
                    "Please select those that should also be removed from OMG's database, and "
                    "provide a new path for the others."))
        label.setWordWrap(True)
        layout.addWidget(label)
        
        
        files = [ levels.real.get(id) for id in ids ]
        containers = []
        for pid in set(itertools.chain(*(file.parents for file in files))):
            containers.append(levels.real.get(pid))
        self.model = LevelTreeModel(levels.real, containers)
        
        self.view = treeview.TreeView(levels.real, affectGlobalSelection=False)        
        self.view.setModel(self.model)
        self.view.setItemDelegate(LostFilesDelegate(self.view))
        self.view.expandAll()
        
        self.view.actionConfig.addActionDefinition(
              ((('losttracks', 'setpath')),), SetPathAction)
        self.view.actionConfig.addActionDefinition(
              ((('losttracks', 'delete')),), treeactions.DeleteAction, text=self.tr("delete"), shortcut="Del", allowDisk=False)
        layout.addWidget(self.view)
        
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok)
        buttonBox.accepted.connect(self.accept)
        layout.addWidget(buttonBox)
        
        self.setLayout(layout)
        self.resize(800,400)


class ModifiedTagsDialog(QtGui.QDialog):
    
    def __init__(self, track, dbTags, fsTags):
        super().__init__(application.mainWindow)
        self.track = track
        self.dbTags = dbTags
        self.fsTags = fsTags
        self.setModal(True)
        self.setWindowTitle(self.tr('Modified Tags Detected'))
        layout = QtGui.QGridLayout()
        layout.addWidget(QtGui.QLabel(self.tr("<b>In Database:</b>")), 0, 0)
        layout.addWidget(QtGui.QLabel(self.tr("<b>On Disk:</b>")), 0, 1)
        
        delegateProfile = delegates.profiles.category.getFromStorage(
                                None, editordelegate.EditorDelegate.profileType)
        dbElem = levels.real.get(track.id)
        
        dbModel = LevelTreeModel(levels.real, [dbElem])
        dbTree = treeview.TreeView(levels.real, affectGlobalSelection=False)
        dbTree.setRootIsDecorated(False)
        dbTree.setModel(dbModel)
        dbTree.setItemDelegate(editordelegate.EditorDelegate(dbTree, delegateProfile))
        fsLevel = levels.real.subLevel([dbElem], 'tmp')
        fsElem = fsLevel.get(track.id)
        fsElemTags = fsElem.tags
        nonPrivateTags = [tag for tag in fsElemTags if not tag.private]
        for tag in nonPrivateTags:
            del fsElemTags[tag]
        for tag, values in fsTags.items():
            fsElemTags[tag] = values
        fsModel = LevelTreeModel(fsLevel, [fsLevel.get(track.id)])
        fsTree = treeview.TreeView(fsLevel, affectGlobalSelection=False)
        fsTree.setRootIsDecorated(False)
        fsTree.setModel(fsModel)
        fsTree.setItemDelegate(editordelegate.EditorDelegate(fsTree, delegateProfile))
        
        layout.addWidget(dbTree, 1, 0)
        layout.addWidget(fsTree, 1, 1)
        
        dbButton = QtGui.QPushButton(self.tr("use DB tags"))
        fsButton = QtGui.QPushButton(self.tr("use disk tags"))
        
        layout.addWidget(dbButton, 2, 0)
        layout.addWidget(fsButton, 2, 1)
        
        dbButton.clicked.connect(self.useDBTags)
        fsButton.clicked.connect(self.useFSTags)
        
        self.setLayout(layout)
        
    def useDBTags(self):
        self.choice = 'DB'
        self.accept()
    
    def useFSTags(self):
        self.choice = 'FS'
        self.accept()