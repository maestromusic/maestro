# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2015 Martin Altmayer, Michael Helmling
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

import os.path

from PyQt5 import QtCore, QtGui, QtWidgets

from maestro import stack
from maestro import utils
from maestro.core import elements, nodes, urls, levels
from maestro.models import leveltreemodel
from maestro.gui import actions, dialogs

translate = QtCore.QCoreApplication.translate


class EditTagsAction(actions.TreeAction):
    """Action to edit tags; exists both in a recursive and non-recursive variant, depending on the argument
    to the constructor."""

    label = translate('EditTagsAction', 'Edit tags')

    def initialize(self, selection):
        self.setEnabled(selection.hasWrappers())

    def doAction(self):
        """Open a dialog to edit the tags of the currently selected elements (and the children, if
        *recursive* is True). This is called by the edit tags actions in the contextmenu.
        """
        from maestro.widgets.tageditor import tageditor
        dialog = tageditor.TagEditorDialog(parent=self.parent())
        dialog.useElementsFromSelection(self.parent().selection)
        dialog.exec_()

EditTagsAction.register('editTags', shortcut=translate('QShortcut', 'Ctrl+T'))


class RemoveFromParentAction(actions.TreeAction):
    """Action to remove selected elements from the parent container or rootnode.
    """

    label = translate('RemoveFromParentAction', 'Remove from parent')

    def initialize(self, selection):
        self.setEnabled(not selection.empty()
                        and all(isinstance(w.parent, nodes.Wrapper) or isinstance(w.parent, nodes.RootNode)
                                for w in selection.wrappers()))

    def doAction(self):
        model = self.parent().model()
        byParent = {}
        wrappers = self.parent().selection.wrappers()
        for wrapper in wrappers:
            if any(p in wrappers for p in wrapper.getParents()):
                continue
            parent = wrapper.parent
            if parent not in byParent:
                byParent[parent] = []
            byParent[parent].append(parent.contents.index(wrapper))
        for parent, indexes in byParent.items():
            byParent[parent] = sorted(set(indexes))

        stack.beginMacro('remove')
        from maestro.widgets import browser
        if isinstance(model, leveltreemodel.LevelTreeModel):
            for parent, indexes in byParent.items():
                model.removeElements(parent, indexes)
        elif isinstance(model, browser.model.BrowserModel):
            for parent, indexes in byParent.items():
                self.level().removeContentsAuto(parent.element, indexes=indexes)
        else:
            raise NotImplementedError()
        stack.endMacro()

RemoveFromParentAction.register('remove', shortcut=QtGui.QKeySequence(QtGui.QKeySequence.Delete))


class MergeAction(actions.TreeAction):
    """Action to merge selected elements into a new container."""

    label = translate('MergeAction', 'Merge ...')

    def initialize(self, selection):
        self.setEnabled(selection.singleParent())

    def doAction(self):
        selection = self.parent().selection
        from ..gui.dialogs import MergeDialog
        nodes = sorted(selection.wrappers(), key=lambda wrap: wrap.parent.contents.index(wrap))
        dialog = MergeDialog(self.parent().model(), nodes, self.parent())
        dialog.exec_()

MergeAction.register('merge', description=translate('MergeAction', 'Merge elements into a new container'),
                     shortcut=translate('QShortcut', 'Ctrl+M'))


class FlattenAction(actions.TreeAction):
    """Action to "flatten out" containers, i.e. remove them and replace them by their
    children."""

    label = translate('FlattenAction', 'Flatten container')

    def initialize(self, selection):
        self.setEnabled(not selection.hasFiles() and selection.singleParent(True))

    def doAction(self):
        stack = self.level().stack
        stack.beginMacro(self.tr('flatten container(s)'))
        wrappers = self.parent().selection.wrappers()
        elements = [wrapper.element for wrapper in wrappers]
        positions = [wrapper.position for wrapper in wrappers]
        parent = wrappers[0].parent.element
        indices = sorted([parent.contents.positions.index(pos) for pos in positions], reverse=True)
        for i, index in enumerate(indices, start=1):
            element = self.level().collect(parent.contents.ids[index])
            pos = parent.contents.positions[index]
            children = list(element.getContents())
            self.level().removeContents(parent, [pos])
            self.level().removeContents(element, element.contents.positions)
            if element not in elements[:-i]:
                self.level().removeElements([element])
            self.level().insertContentsAuto(parent, index, children)
        stack.endMacro()

FlattenAction.register('flatten', shortcut=translate('QShortcut', 'Ctrl+F'))


class ChangePositionAction(actions.TreeAction):

    def __init__(self, parent, mode='*', **kwargs):
        super().__init__(parent, **kwargs)
        self.mode = mode
        if mode == '*':
            self.setText(self.tr('Choose ...'))
        elif mode == '+':
            self.setText(self.tr('Increase position by 1'))
        else:
            self.setText(self.tr('Decrease position by 1'))

    def initialize(self, selection):
        if self.mode == '*':
            self.setEnabled(False)
        else:
            self.setEnabled(selection.singleParent(True))

    def doAction(self):
        selection = self.parent().selection
        positions = [wrap.position for wrap in selection.wrappers()]
        parent = selection.wrappers()[0].parent.element
        try:
            self.level().shiftPositions(parent, positions, 1 if self.mode == '+' else -1)
        except levels.ConsistencyError as e:
            from .dialogs import warning
            warning(self.tr('error'), str(e))

    @staticmethod
    def addSubmenu(actionTree):
        """Create a submenu in the given action configuration with entries for each type."""
        subTree = actionTree.addSubTree(translate('ChangePositionAction', 'Change position ...'), 'elements')
        for mode in '+', '-', '*':
            subTree.addActionDefinition('changePos' + mode)

ChangePositionAction.register('changePos*',
                              description=translate('ChangePositionAction', 'Change position'),
                              shortcut=translate('QShortcut', 'Ctrl+P'), mode='*')
ChangePositionAction.register('changePos+',
                              description=translate('ChangePositionAction', 'Increase position by 1'),
                              shortcut=translate('QShortcut', '+'), mode='+',)
ChangePositionAction.register('changePos-',
                              description=translate('ChangePositionAction', 'Decrease position by 1'),
                              shortcut=translate('QShortcut', '-'), mode='-',)


class SetElementTypeAction(actions.TreeAction):
    """Action to set the element type of one or more elements."""

    def __init__(self, parent, type, **kwargs):
        """Constructor. *type* is one of elements.ContainerType."""
        super().__init__(parent, **kwargs)
        self.type = type
        self.setText(type.title())

    def initialize(self, selection):
        self.selection = selection
        allMyType = all(c.type == self.type for c in selection.containers())
        self.setEnabled(selection.hasContainers() and not allMyType)
        self.setCheckable(selection.hasContainers() and allMyType)
        self.setChecked(selection.hasContainers() and allMyType)

    def doAction(self):
        self.level().setTypes({container: self.type for container in self.selection.containers()})

    @staticmethod
    def addSubmenu(actionTree):
        """Create a submenu in the given action configuration with entries for each type."""
        subTree = actionTree.addSubTree(translate('SetElementTypeAction', 'Set element type ...'), 'elements')
        for type in elements.ContainerType:
            subTree.addActionDefinition('setType' + type.name)


typeDesc = translate('SetElementTypeAction', 'Set type to "{}"')
for type in elements.ContainerType:
    SetElementTypeAction.register('setType' + type.name, description=typeDesc.format(type.title()),
                                  type=type)


class ClearTreeAction(actions.TreeAction):
    """This action clears a tree model."""

    def __init__(self, parent, identifier):
        super().__init__(parent, identifier)
        self.setIcon(utils.images.icon('edit-clear-list'))
        self.setText(self.tr('Clear'))

    def initialize(self, selection):
        self.setEnabled(self.parent().model().root.getContentsCount() > 0)

    def doAction(self):
        self.parent().model().clear()

ClearTreeAction.register('clearTree', context='misc',
                         description=translate('ClearTreeAction', 'Clear (empty) all contents'),
                         shortcut=translate('QShortcut', 'Shift+Del'))


class CommitTreeAction(actions.TreeAction):
    """Commit the contents of a LevelTreeModel."""

    def __init__(self, parent, identifier):
        super().__init__(parent, identifier)
        self.setIcon(utils.images.icon('document-save'))
        self.setText(self.tr('Store'))

    def initialize(self, selection):
        self.setEnabled(len(self.parent().model().root.contents) > 0)

    def doAction(self):
        model = self.parent().model()
        if not model.containsExternalTags():
            try:
                model.commit()
            except urls.TagWriteError as e:
                e.displayMessage()
            except levels.RenameFilesError as e:
                e.displayMessage()
        else:
            dialogs.warning(self.tr('No commit possible'),
                            self.tr("Can't commit while editor contains external tags."))

CommitTreeAction.register('commit', context='misc',
                          description=translate('CommitTreeAction', 'Store all changes made in this view'),
                          shortcut=translate('QShortcut', 'Shift+Enter'))


class DeleteAction(actions.TreeAction):
    """Action to delete elements from the database and/or filesystem.

    When the selected elements contain files, after the deletion from Maestro's database a dialog is
    displayed that asks the user if the files should also be deleted from disk.

    In the special case that an "intermediate container" (i.e., container with a parent container)
    and existing children) is selected, another dialog is presented which offers to attach the now
    pending children to the deleted container's parent.
    """

    label = translate('DeleteAction', 'Remove from database')

    def __init__(self, parent, identifier, allowDisk=True):
        """Initialize the action."""
        super().__init__(parent, identifier=identifier)

        self.allowDisk = allowDisk

    def initialize(self, selection):
        self.setEnabled(selection.hasElements())

    def doAction(self):
        selection = self.parent().selection
        insertPending = False
        self.level().stack.beginMacro(self.tr('delete elements'))
        files = list(selection.files())
        if selection.singleWrapper() and selection.hasContainers():
            container = selection.wrappers()[0]
            container.loadContents(recursive=True)
            if container.parent and container.parent.isContainer() and container.hasContents():
                ans = dialogs.question(self.tr('Replace by children?'),
                                 self.tr('You have selected to remove an intermediate container. '
                                 'Do you want to append its children to its parent?'))
                if ans:
                    insertPos = container.position
                    insertParent = container.parent.element
                    insertIndex = insertParent.contents.positions.index(insertPos)
                    insertChildren = [wrapper.element for wrapper in container.contents]
                    insertPending = True
        self.level().deleteElements(selection.elements())
        if insertPending:
            self.level().insertContentsAuto(insertParent, insertIndex, insertChildren)
        self.level().stack.endMacro()
        if self.allowDisk and len(files) > 0:
            from maestro.gui.dialogs import DeleteDialog
            dialog = DeleteDialog(files, self.parent())
            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                self.level().deleteElements(files, fromDisk=True)

DeleteAction.register('delete', shortcut=translate('QShortcut', 'Ctrl+Del'))


class ChangeFileUrlsAction(actions.TreeAction):
    """Action to change the URL of a single file or the directory of several files in the same directory."""

    label = translate('ChangeFileUrlsAction', 'Change URLs (rename)')

    def initialize(self, selection):
        self.setText(self.tr('Change file URLs'))
        self.setEnabled(False)
        if selection.singleWrapper():
            self.setText(self.tr("Change file URL"))
            element = selection.wrappers()[0].element
            if element.isFile():
                self.setEnabled(True)
        elif selection.hasFiles():
            elements = list(selection.files())
            if all(el.url.scheme == 'file' for el in elements):
                dir = self._getDirectory(elements)
                if dir is not None:
                    self.setEnabled(True)

    def _getDirectory(self, elements):
        """Return the common directory (relative to the collection directory) of *elements* (or None)."""
        paths = [element.url.path for element in elements]
        dir = None
        for path in paths:
            # make sure all files are in the same directory
            if dir is None:
                dir = os.path.dirname(path)
            elif dir != os.path.dirname(path):
                return None
        return dir if len(dir) > 0 else None

    def doAction(self):
        selection = self.parent().selection
        if selection.singleWrapper():
            element = next(selection.fileWrappers()).element
            if element.url.scheme == 'file':
                self.changeFileUrl(element)
            else:
                self.changeOtherUrl(element)
        else:
            elements = list(selection.files())
            self.changeElementsDirectory(elements)

    def _checkFilePath(self, path, shouldExist, oldPath):
        """Check whether the *path* is valid, not equal to *oldPath* and exists if and only if *shouldExist*
        is True."""
        from maestro.core import domains
        if path in [None, '', oldPath]:
            return False
        if not shouldExist and os.path.exists(path):
            QtWidgets.QMessageBox.warning(None, self.tr("Invalid path"),
                                      self.tr("The given path exists already."))
            return False
        elif shouldExist and not os.path.exists(path):
            QtWidgets.QMessageBox.warning(None, self.tr("Invalid path"),
                                      self.tr("The given path does not exists."))
            return False
        source = domains.getSource(oldPath)
        if not path.startswith(source.path):
            QtWidgets.QMessageBox.warning(None, self.tr("Invalid path"),
                                      self.tr("Path must be inside collection directory"))
            return False
        return True

    def changeFileUrl(self, element):
        """Ask the user for a new URL for *element* and change the URL. Element must be a filesystem-file."""
        path = QtGui.QFileDialog.getSaveFileName(None,
                                                 self.tr("Select new file location"),
                                                 element.url.path,
                                                 options=QtGui.QFileDialog.DontConfirmOverwrite)
        if self._checkFilePath(path, shouldExist=False, oldPath=element.url.path):
            self.level().renameFiles( {element: (element.url, urls.URL.fileURL(path)) })

    def changeOtherUrl(self, element):
        """Ask the user for a new URL for *element* and change the URL. For filesystem-files use
        changeFileUrl instead."""
        path, ok = QtWidgets.QInputDialog.getText(None, self.tr("Change file URL"),
                                              self.tr("Select new file URL:"),
                                              QtWidgets.QLineEdit.Normal, str(element.url))
        if not ok or path is None or path == '':
            return
        try:
            newUrl = urls.URL(path)
        except ValueError:
            QtWidgets.QMessageBox.warning(None, self.tr("Invalid URL"), self.tr("Please enter a valid URL."))
            return

        self.level().renameFiles({element: (element.url, newUrl)})

    def changeElementsDirectory(self, elements):
        """Given a list of elements from the same directory, ask the user for a new directory and move
        all files to the new directory."""
        dir = self._getDirectory(elements)
        if dir is None:
            return
        path = QtGui.QFileDialog.getExistingDirectory(None, self.tr("Select new files directory"), dir)
        if self._checkFilePath(path, shouldExist=True, oldPath=dir):
            changes = {element: (element.url, urls.URL.fileURL(os.path.join(path, os.path.basename(element.url.path))))
                       for element in elements}
            for oldUrl, newUrl in changes.values():
                if os.path.exists(newUrl.path):
                    QtWidgets.QMessageBox.warning(None, self.tr("Path collision"),
                                self.tr("Cannot move '{}' to '{}' because the latter path exists already."
                                        .format(str(oldUrl), str(newUrl))))
                    return
            self.level().renameFiles(changes)

ChangeFileUrlsAction.register('changeURLs')
