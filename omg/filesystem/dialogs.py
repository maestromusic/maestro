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

import itertools

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from .. import application
from ..core import levels
from ..models.leveltreemodel import LevelTreeModel
from ..gui import delegates, treeactions, treeview
from ..gui.delegates import abstractdelegate, editor as editordelegate

import os.path

translate = QtCore.QCoreApplication.translate


class LostFilesDelegate(delegates.StandardDelegate):
    
    def __init__(self, view):
        self.profile = delegates.profiles.DelegateProfile("lostfiles") 
        super().__init__(view, self.profile)
        self.profile.options['showPaths'] = True
        self.profile.options['showMajer'] = False
        self.profile.options['appendRemainingTags'] = False
        self.profile.options['showAllAncestors'] = True
        self.profile.options['showFlagIcons'] = True
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
    """Action to change the URL of a file without any undo/redo.
    
    Used by the LostFilesDialog to correct URLs of files moved outside of OMG.
    """
    
    def __init__(self, parent, text=None, shortcut=None):
        super().__init__(parent, shortcut)
        if text is None:
            self.setText(self.tr('choose path'))
        else:
            self.setText(text)
        self.setPaths = []
    
    def initialize(self, selection):
        self.setEnabled(selection.singleWrapper() and \
                        selection.hasFiles() and \
                        not os.path.exists(next(selection.fileWrappers()).element.url.absPath))
    
    def doAction(self):
        """Open a dialog to edit the tags of the currently selected elements (and the children, if
        *recursive* is True). This is called by the edit tags actions in the contextmenu.
        """
        from ..filebackends.filesystem import FileURL
        elem = next(self.parent().selection.fileWrappers()).element
        path = QtGui.QFileDialog.getOpenFileName(application.mainWindow,
                                                 self.tr("Select new file location"),
                                                 os.path.dirname(elem.url.absPath))
        if path != "":
            newUrl = FileURL(path)
            from .. import database as db
            from ..database import write
            db.write.changeUrls([ (str(newUrl), elem.id) ])
            self.setPaths.append( (elem.url, newUrl) )
            elem.url = newUrl
            levels.real.emitEvent(dataIds=(elem.id,))
            elem.problem = False


class RemoveMissingFilesAction(treeactions.TreeAction):
    """Action to remove elements from the database which are missing on the filesystem."""
    
    def __init__(self, parent):
        """Initialize the action."""
        super().__init__(parent)
        self.setShortcut(self.tr("Del"))
        self.setText(self.tr("Remove"))
        self.removedURLs = []
            
    def initialize(self, selection):
        self.setEnabled(selection.hasElements())
    
    def doAction(self):
        model = self.parent().model()
        selection = self.parent().selection
        belowRoot = [wrap.parent.index(wrap) for wrap in selection.wrappers()
                     if wrap.parent is self.parent().model().root]
        self.removedURLs.extend(wrapper.element.url for wrapper in selection.fileWrappers())
        elements = selection.elements()
        if len(belowRoot) > 0:
            for row in sorted(belowRoot, reverse=True):
                model._removeContents(QtCore.QModelIndex(), row, row)
        levels.real.deleteElements(elements)


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
                    "Some files from OMG's database could not be found anymore in your "
                    "filesystem. They are shown in red below. For each file, you can either "
                    "provide a new path manually or delete it from the database."))
        label.setWordWrap(True)
        layout.addWidget(label)
        
        files = [ levels.real.collect(id) for id in ids ]
        for file in files:
            file.problem = True
        containers = []
        for pid in set(itertools.chain(*(file.parents for file in files))):
            containers.append(levels.real.collect(pid))
        for container in containers:
            for file in container.getAllFiles():
                if file in files:
                    files.remove(file)
        self.model = LevelTreeModel(levels.real, containers + files)
        # TODO: containerless files don't disappear in view after deleting
        
        self.view = treeview.TreeView(levels.real, affectGlobalSelection=False)        
        self.view.setModel(self.model)
        self.view.setItemDelegate(LostFilesDelegate(self.view))
        self.view.expandAll()
        
        self.setPathAction = SetPathAction(self.view)
        self.deleteAction = RemoveMissingFilesAction(self.view)
        self.view.addLocalAction(self.setPathAction)
        self.view.addLocalAction(self.deleteAction)
        layout.addWidget(self.view)
        
        toolbar = QtGui.QToolBar()
        toolbar.addAction(self.setPathAction)
        toolbar.addAction(self.deleteAction)
        buttonLayout = QtGui.QHBoxLayout()
        buttonLayout.addStretch()
        buttonLayout.addWidget(toolbar)
        self.closeButton = QtGui.QPushButton()
        buttonLayout.addWidget(self.closeButton)
        self.closeButton.clicked.connect(self.accept)
        layout.addLayout(buttonLayout)
        self.setLayout(layout)
        self.updateCloseButton()
        levels.real.connect(self.updateCloseButton)
        self.resize(800,400)
    
    def updateCloseButton(self):
        numProblem = sum(hasattr(f.element, "problem") for f in self.model.root.getAllFiles())
        self.closeButton.setText(self.tr("Close (%n files still missing)", None, numProblem))


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
        fsLevel = levels.Level('tmp', levels.real, [dbElem])
        fsElem = fsLevel[track.id]
        fsElemTags = fsElem.tags
        nonPrivateTags = [tag for tag in fsElemTags if not tag.private]
        for tag in nonPrivateTags:
            del fsElemTags[tag]
        for tag, values in fsTags.items():
            fsElemTags[tag] = values
        fsModel = LevelTreeModel(fsLevel, [fsLevel[track.id]])
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
