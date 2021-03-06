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
#

import itertools
import os.path

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt

from maestro import application, database as db, stack, utils, profiles
from maestro.core import levels, tags, urls
from maestro.models.leveltreemodel import LevelTreeModel
from maestro.gui import actions, delegates, treeview
from maestro.gui.delegates import abstractdelegate
from maestro.widgets.editor import delegate as editordelegate

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
            if os.path.exists(element.url.path):
                style = self.goodPathStyle
            else:
                style = self.badPathStyle
            self.addCenter(delegates.TextItem(element.url.path, style))


class SetPathAction(actions.TreeAction):
    """Action to change the URL of a file without any undo/redo.
    
    Used by the LostFilesDialog to correct URLs of files moved outside of Maestro.
    """

    label = translate('SetPathAction', 'Choose path')
    
    def initialize(self, selection):
        self.setEnabled(selection.singleWrapper() and \
                        selection.hasFiles() and \
                        not os.path.exists(next(selection.fileWrappers()).element.url.path))
    
    def doAction(self):
        elem = next(self.parent().selection.fileWrappers()).element
        path = QtWidgets.QFileDialog.getOpenFileName(
            application.mainWindow,
            self.tr('Select new location of the missing file'),
            os.path.dirname(elem.url.path))[0]
        if path != '':
            newUrl = urls.URL.fileURL(path)
            from maestro.filesystem import getNewfileHash
            db.query('UPDATE {p}files SET url=?,hash=? WHERE element_id=?',
                     str(newUrl), getNewfileHash(newUrl), elem.id)
            elem.url = newUrl
            levels.real.emitEvent(dataIds=(elem.id,))
            

class RemoveMissingFilesAction(actions.TreeAction):
    """Action to remove elements from the database which are missing on the filesystem."""

    label = translate('RemoveMissingFilesAction', 'Remove')
            
    def initialize(self, selection):
        self.setEnabled(selection.hasElements())
    
    def doAction(self):
        model = self.parent().model()
        selection = self.parent().selection
        belowRoot = [wrap.parent.index(wrap) for wrap in selection.wrappers()
                     if wrap.parent is self.parent().model().root]
        elements = selection.elements()
        if len(belowRoot) > 0:
            for row in sorted(belowRoot, reverse=True):
                model._removeContents(QtCore.QModelIndex(), row, row)
        levels.real.deleteElements(elements)


class MissingFilesTreeView(treeview.TreeView):

    def __init__(self, model):
        super().__init__(level=levels.real, affectGlobalSelection=False)
        self.setModel(model)


class MissingFilesDialog(QtWidgets.QDialog):
    """A dialog that notifies the user about missing files.
    
    When Maestro detects that files were deleted from outside Maestro, this
    dialog is shown which asks what to do, i.e., decide which of
    the missing elements should also be deleted from the database. If
    this leads to empty containers, the user is asked if they should
    be removed, too.

    :param ids: List of file IDs.
    """
    def __init__(self, ids):
        super().__init__(application.mainWindow)
        self.setModal(True)
        self.setWindowTitle(self.tr('Missing Files Detected'))
        layout = QtWidgets.QVBoxLayout()
        label = QtWidgets.QLabel(self.tr(
            "Some files from Maestro's database could not be found anymore in your "
            "filesystem. They are shown in red below. For each file, you can either "
            "provide a new path manually or delete it from the database."))
        label.setWordWrap(True)
        layout.addWidget(label)
        
        files = [levels.real.collect(id) for id in ids]
        containers = []
        for pid in set(itertools.chain(*(file.parents for file in files))):
            containers.append(levels.real.collect(pid))
        for container in containers:
            for file in container.getAllFiles():
                if file in files:
                    files.remove(file)
        self.model = LevelTreeModel(levels.real, containers + files)
        
        self.view = MissingFilesTreeView(self.model)
        self.view.setItemDelegate(LostFilesDelegate(self.view))
        self.view.expandAll()
        layout.addWidget(self.view)
        
        toolbar = QtWidgets.QToolBar()
        toolbar.addAction(self.view.treeActions['filesystem-setPath'])
        toolbar.addAction(self.view.treeActions['filesystem-removeMissing'])
        buttonLayout = QtWidgets.QHBoxLayout()
        buttonLayout.addStretch()
        buttonLayout.addWidget(toolbar)
        self.closeButton = QtWidgets.QPushButton()
        buttonLayout.addWidget(self.closeButton)
        self.closeButton.clicked.connect(self.accept)
        layout.addLayout(buttonLayout)
        self.setLayout(layout)
        self.updateCloseButton()
        levels.real.connect(self.updateCloseButton)
        self.resize(800, 400)
    
    def updateCloseButton(self):
        numProblem = len([f for f in self.model.root.getAllFiles() if not os.path.exists(f.element.url.path)])
        if numProblem == 0:
            self.accept()
        self.closeButton.setText(self.tr("Close (%n files still missing)", None, numProblem))


class ModifiedTagsDialog(QtWidgets.QDialog):
    """A dialog displayed when modification of tags has been detected on the filesystem.

    Allows user to choose between tags from Maestro's database and the tags in the file.
    """
    def __init__(self, file, dbTags, fsTags):
        super().__init__(application.mainWindow)
        self.file = file
        self.dbTags = dbTags
        self.fsTags = fsTags
        self.setModal(True)

        self.setWindowTitle(self.tr('Detected Modified Tags on Disk'))
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(QtWidgets.QLabel(self.tr(
            'Maestro has detected that the tags of <center><i>{}</i>'
            '</center> do not match Maestro\'s database. Please choose which version to keep:')
            .format(self.file.url.path)
        ))
        viewLayout = QtWidgets.QHBoxLayout()
        leftLayout = QtWidgets.QVBoxLayout()
        rightLayout = QtWidgets.QVBoxLayout()
        midLayout = QtWidgets.QVBoxLayout()
        leftLayout.addWidget(QtWidgets.QLabel(self.tr('<b>In Maestro\'s database:</b>')))
        rightLayout.addWidget(QtWidgets.QLabel(self.tr('<b>In the file:</b>')))
        
        delegateProfile = profiles.category('delegates').getFromStorage(
            None, profiles.category('delegates').getType('editor')
        )
        delegateProfile.options['showPaths'] = False
        dbElem = levels.real.collect(file.id)
        
        dbModel = LevelTreeModel(levels.real, [dbElem])
        dbTree = treeview.TreeView(levels.real, affectGlobalSelection=False)
        dbTree.setRootIsDecorated(False)
        dbTree.setModel(dbModel)
        dbTree.setItemDelegate(editordelegate.EditorDelegate(dbTree, delegateProfile))
        fsLevel = levels.Level('tmp', levels.real, [dbElem])
        fsElem = fsLevel[file.id]
        fsElemTags = fsElem.tags
        nonPrivateTags = [tag for tag in fsElemTags if not tag.private]
        for tag in nonPrivateTags:
            del fsElemTags[tag]
        for tag, values in fsTags.items():
            fsElemTags[tag] = values
        fsModel = LevelTreeModel(fsLevel, [fsLevel[file.id]])
        fsTree = treeview.TreeView(fsLevel, affectGlobalSelection=False)
        fsTree.setRootIsDecorated(False)
        fsTree.setModel(fsModel)
        fsTree.setItemDelegate(editordelegate.EditorDelegate(fsTree, delegateProfile))
        leftLayout.addWidget(dbTree)
        rightLayout.addWidget(fsTree)

        dbButton = QtWidgets.QPushButton(utils.images.icon('go-next'), '')
        dbButton.setToolTip(self.tr('Write database tags to file'))
        fsButton = QtWidgets.QPushButton(utils.images.icon('go-previous'), '')
        fsButton.setToolTip(self.tr('Store tags from file into database'))

        dbButton.clicked.connect(self.useDBTags)
        fsButton.clicked.connect(self.useFSTags)

        midLayout.setAlignment(Qt.AlignVCenter)
        midLayout.addWidget(dbButton)
        midLayout.addWidget(fsButton)
        viewLayout.addLayout(leftLayout)
        viewLayout.addLayout(midLayout)
        viewLayout.addLayout(rightLayout)
        layout.addLayout(viewLayout)
        bbx = QtWidgets.QDialogButtonBox()
        bbx.addButton(self.tr('Cancel (ignore for now)'), bbx.RejectRole)
        bbx.rejected.connect(self.reject)
        layout.addWidget(bbx)
        self.setLayout(layout)
        
    def useDBTags(self):
        backendFile = self.file.url.backendFile()
        backendFile.readTags()
        backendFile.tags = self.dbTags.withoutPrivateTags()
        try:
            backendFile.saveTags()
            self.accept()
        except OSError as e:
            from maestro.gui.dialogs import warning
            warning(self.tr('Unable to save tags'), 'Could not save tags:\n{}'.format(e))
            self.reject()
    
    def useFSTags(self):
        """Use the tags from filesystem. Here, we need to first check if there are any not-in-DB
        tags in the file. In that case, we display a dialog to add those to the database.
        """
        while True:
            newTags = [tag for tag in self.fsTags if not tag.isInDb()]
            if len(newTags) == 0:
                break
            from ..gui.tagwidgets import AddTagTypeDialog
            for tag in newTags:
                ans = AddTagTypeDialog.addTagType(tag, text=self.tr('Please configure the new tag '
                    '"{}" found in this file'.format(tag)))
                if not ans:
                    return
                elif ans != tag:
                    # user has renamed tag -> restart the check from the beginning of the while loop
                    self.fsTags[ans] = self.fsTags[tag]
                    del self.fsTags[tag]
                    break
        stack.clear()
        diff = tags.TagStorageDifference(self.dbTags.withoutPrivateTags(), self.fsTags)
        levels.real._changeTags({levels.real.collect(self.file.id): diff}, dbOnly=True)
        self.accept()
