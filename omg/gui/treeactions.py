# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtGui
from PyQt4.QtCore import Qt

from .. import application, utils, filebackends, config
from ..core import levels, tags, elements
from ..core.nodes import RootNode, Wrapper
from ..models import leveltreemodel
from ..models.browser import BrowserModel
from . import dialogs, widgets

translate = QtGui.QApplication.translate

        
class TreeAction(QtGui.QAction):
    """Super class for TreeActions, i.e. Actions for TreeViews."""
    def __init__(self, parent, text=None, shortcut=None, icon=None, tooltip=None):
        super().__init__(parent)
        if shortcut:
            self.setShortcut(shortcut)
        if icon:
            self.setIcon(icon)
        if tooltip:
            self.setToolTip((tooltip))
        self.triggered.connect(self.doAction)
        self.setShortcutContext(Qt.WidgetShortcut)
    
    def initialize(self, selection):
        pass
    
    def doAction(self):
        raise NotImplementedError()
    
    def level(self):
        """A shorthand function to determine the level of the treeview's model."""
        return self.parent().model().level


class EditTagsAction(TreeAction):
    """Action to edit tags; exists both in a recursive and non-recursive variant, depending on the argument
    to the constructor."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr("Edit tags"))
    
    def initialize(self, selection):
        self.setEnabled(selection.hasWrappers())
    
    def doAction(self):
        """Open a dialog to edit the tags of the currently selected elements (and the children, if
        *recursive* is True). This is called by the edit tags actions in the contextmenu.
        """
        from ..gui import tageditor
        dialog = tageditor.TagEditorDialog(parent=self.parent())
        dialog.useElementsFromSelection(self.parent().selection)
        dialog.exec_()


class ChangeFileUrlsAction(TreeAction):
    """Action to change the URL of a single file or the directory of several files in the same directory."""
    def initialize(self, selection):
        self.setText(self.tr("Change file URLs"))
        self.setEnabled(False)
        if selection.singleWrapper():
            self.setText(self.tr("Change file URL"))
            element = selection.wrappers()[0].element
            if element.isFile() and element.url is not None and element.url.CAN_RENAME:
                self.setEnabled(True)
        elif selection.hasFiles():
            elements = list(selection.files())
            if all(isinstance(el.url, filebackends.filesystem.FileURL) for el in elements):
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
        from ..filebackends.filesystem import FileURL
        selection = self.parent().selection
        if selection.singleWrapper():
            element = next(selection.fileWrappers()).element
            if isinstance(element.url, FileURL):
                self.changeFileUrl(element)
            else: self.changeOtherUrl(element)
        else:
            elements = list(selection.files())
            self.changeElementsDirectory(elements)
    
    def _checkFilePath(self, path, shouldExist, oldPath):
        """Check whether the *path* is valid, not equal to *oldPath* and exists if and only if *shouldExist*
        is True."""
        if path in [None, '', oldPath]:
            return False
        if not shouldExist and os.path.exists(path):
            QtGui.QMessageBox.warning(None, self.tr("Invalid path"),
                                      self.tr("The given path exists already."))
            return False
        elif shouldExist and not os.path.exists(path):
            QtGui.QMessageBox.warning(None, self.tr("Invalid path"),
                                      self.tr("The given path does not exists."))
            return False
        if not path.startswith(config.options.main.collection):
            QtGui.QMessageBox.warning(None, self.tr("Invalid path"),
                                      self.tr("Path must be inside collection directory"))
            return False
        return True
        
    def changeFileUrl(self, element):
        """Ask the user for a new URL for *element* and change the URL. Element must be a filesystem-file."""
        from ..filebackends.filesystem import FileURL
        path = QtGui.QFileDialog.getSaveFileName(None,
                                                 self.tr("Select new file location"),
                                                 element.url.absPath,
                                                 options=QtGui.QFileDialog.DontConfirmOverwrite)
        if self._checkFilePath(path, shouldExist=False, oldPath=element.url.absPath):
            self.level().renameFiles( {element: (element.url, FileURL(path)) })
            
    def changeOtherUrl(self, element):
        """Ask the user for a new URL for *element* and change the URL. For filesystem-files use
        changeFileUrl instead."""
        path, ok = QtGui.QInputDialog.getText(None, self.tr("Change file URL"),
                                              self.tr("Select new file URL:"),
                                              QtGui.QLineEdit.Normal, str(element.url))
        if not ok or path is None or path == '':
            return
        try:
            newUrl = filebackends.BackendURL.fromString(path)
        except ValueError:
            QtGui.QMessageBox.warning(None, self.tr("Invalid URL"), self.tr("Please enter a valid URL."))
            return
        
        self.level().renameFiles( {element: (element.url, newUrl) })
        
    def changeElementsDirectory(self, elements):
        """Given a list of elements from the same directory, ask the user for a new directory and move
        all files to the new directory."""
        dir = self._getDirectory(elements)
        if dir is None:
            return
        path = QtGui.QFileDialog.getExistingDirectory(None,
                                                      self.tr("Select new files directory"),
                                                      utils.absPath(dir))
        if self._checkFilePath(path, shouldExist=True, oldPath=utils.absPath(dir)):
            from ..filebackends.filesystem import FileURL
            changes = {element: (element.url, FileURL(os.path.join(path, os.path.basename(element.url.path))))
                       for element in elements}
            for oldUrl, newUrl in changes.values():
                if os.path.exists(newUrl.absPath):
                    QtGui.QMessageBox.warning(None, self.tr("Path collision"),
                                self.tr("Cannot move '{}' to '{}' because the latter path exists already."
                                        .format(str(oldUrl), str(newUrl))))
                    return
            self.level().renameFiles(changes)


class RemoveFromParentAction(TreeAction):
    """Action to remove selected elements from the parent container or rootnode.
    """
    def __init__(self, parent):
        """Initialize action."""
        super().__init__(parent, shortcut="Del")
        self.setText(self.tr("Remove"))
    
    def initialize(self, selection):
        self.setEnabled(not selection.empty() \
                        and all(isinstance(w.parent, Wrapper) or isinstance(w.parent, RootNode)
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
        
        application.stack.beginMacro("remove")
        if isinstance(model, leveltreemodel.LevelTreeModel):
            for parent, indexes in byParent.items():
                model.removeElements(parent, indexes)
        elif isinstance(model, BrowserModel):
            for parent, indexes in byParent.items():
                self.level().removeContentsAuto(parent.element, indexes=indexes)
        else:
            raise NotImplementedError()
        application.stack.endMacro()


class DeleteAction(TreeAction):
    """Action to delete elements from the database and/or filesystem."""
    
    def __init__(self, parent, text, allowDisk=True, shortcut=None):
        """Initialize the action."""
        super().__init__(parent, shortcut)
        self.setText(text)
        self.allowDisk = allowDisk
            
    def initialize(self, selection):
        self.setEnabled(selection.hasElements())
    
    def doAction(self):
        selection = self.parent().selection
        files = [wrap.element for wrap in selection.fileWrappers()
                              if wrap.element.url.CAN_DELETE]
        self.level().deleteElements(selection.elements())
        if self.allowDisk and len(files) > 0:
            dialog = DeleteDialog(files,self.parent())
            if dialog.exec_() == QtGui.QDialog.Accepted:
                self.level().deleteElements(files, fromDisk=True)
            

class DeleteDialog(QtGui.QDialog):
    """Special dialog to display the files that have been deleted from database and may be deleted from disk.
    It is used in DeleteAction."""
    def __init__(self, files, parent):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Delete files?"))
        self.resize(400,300)
        layout = QtGui.QVBoxLayout(self)
        label = QtGui.QLabel(
                             self.tr("You have deleted the following %n file(s) from OMG. "
                                     "Do you want them deleted completely?<br />\n"
                                     "<b>This cannot be reversed!</b>",
                                     '', len(files)))
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)
        listWidget = QtGui.QListWidget()
        listWidget.addItems([str(file.url) for file in files])
        layout.addWidget(listWidget)
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Yes | QtGui.QDialogButtonBox.No)
        buttonBox.button(QtGui.QDialogButtonBox.No).setDefault(True)
        buttonBox.rejected.connect(self.reject)
        buttonBox.accepted.connect(self.accept)
        layout.addWidget(buttonBox)
        
    
class MergeAction(TreeAction):
    """Action to merge selected elements into a new container."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr("Merge..."))
    
    def initialize(self, selection):
        self.setEnabled(selection.singleParent())

    def doAction(self):
        selection = self.parent().selection
        from ..gui.dialogs import MergeDialog
        nodes = sorted(selection.wrappers(), key=lambda wrap: wrap.parent.contents.index(wrap))
        dialog = MergeDialog(self.parent().model(), nodes, self.parent())
        dialog.exec_()


class ClearTreeAction(TreeAction):
    """This action clears a tree model."""
    
    def __init__(self, parent):
        super().__init__(parent, shortcut = "Shift+Del")
        self.setIcon(utils.getIcon("clear_playlist.png"))
        self.setText(self.tr('Clear'))
    
    def initialize(self, selection):
        self.setEnabled(self.parent().model().root.getContentsCount() > 0)
    
    def doAction(self):
        self.parent().model().clear()


class CommitTreeAction(TreeAction):
    """Commit the contents of a LevelTreeModel."""
    
    def __init__(self, parent):
        super().__init__(parent, shortcut="Shift+Enter")
        self.setIcon(QtGui.qApp.style().standardIcon(QtGui.QStyle.SP_DialogSaveButton))
        self.setText(self.tr('Commit'))
        
    def initialize(self, selection):
        self.setEnabled(len(self.parent().model().root.contents) > 0)
        
    def doAction(self):
        model = self.parent().model()
        if not model.containsExternalTags():
            try:
                model.commit()
            except filebackends.TagWriteError as e:
                e.displayMessage()
        else:
            dialogs.warning(self.tr("No commit possible"),
                            self.tr("While the editor contains external tags, no commit is possible. "
                                    "Delete those tags or add their tagtype to the database."))

        
class FlattenAction(TreeAction):
    """Action to "flatten out" containers, i.e. remove them and replace them by their
    children."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr("Flatten..."))
        
    def initialize(self, selection):
        self.setEnabled(selection.hasContainers())
        
    def doAction(self):
        from ..gui.dialogs import FlattenDialog
        dialog = FlattenDialog(parent = self.parent())
        if dialog.exec_() == QtGui.QDialog.Accepted:
            flatten(self.parent().level, self.parent().selection.wrappers(), dialog.recursive())
            

class ChangePositionAction(TreeAction):
    
    def __init__(self, parent, mode="free", *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.mode = mode
        if mode == "free":
            self.setText(self.tr("Choose position..."))
        elif mode == "+1":
            self.setText(self.tr("Increase position"))
        elif mode == "-1":
            self.setText(self.tr("Decrease position"))
        else:
            raise ValueError("{0} is not a valid ChangePositionAction mode".format(mode))
    
    
    def initialize(self, selection):
        if self.mode == "free":
            self.setEnabled(False)
        else:
            self.setEnabled(selection.singleParent(True))
        
        
    def doAction(self):
        selection = self.parent().selection
        positions = [wrap.position for wrap in selection.wrappers()]
        parent = selection.wrappers()[0].parent.element
        try:
            self.level().shiftPositions(parent, positions, 1 if self.mode == "+1" else -1)
        except levels.ConsistencyError as e:
            from omg.gui.dialogs import warning
            warning(self.tr('error'), str(e))


    @staticmethod
    def addSubmenu(actionConfig, section):
        """Create a submenu in the given action configuration with entries for each type.""" 
        typeSection = translate("TreeActions", "change position ...")
        for mode in "+1", "-1", "free":
            actionConfig.addActionDefinition(((section, typeSection), 
                                              (typeSection, "changePos{}".format(mode))),
                                             ChangePositionAction, mode=mode)


class MatchTagsFromFilenamesAction(TreeAction):
    """An action to trigger a dialog that matches tags from file names. Will be enabled only if at least
    one file is selected."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr('match tags from filename'))
    
    def initialize(self, selection):
        self.setEnabled(selection.hasFiles())
        
    def doAction(self):
        """Open a TagMatchDialog for the selected elements."""
        from ..gui import tagmatchdialog
        dialog = tagmatchdialog.TagMatchDialog(self.parent().level,
                                               self.parent().selection.wrappers(),
                                               self.parent())
        dialog.exec_()


class SetElementTypeAction(TreeAction):
    """Action to set the element type of one or more elements."""
    
    def __init__(self, parent, type):
        """Constructor. *type* is one of elements.CONTAINER_TYPES."""
        super().__init__(parent)
        self.type = type
        self.setText(elements.getTypeTitle(type))
        
    
    def initialize(self, selection):
        self.selection = selection
        allMyType = all(c.type == self.type for c in selection.containers())
        self.setEnabled(selection.hasContainers() and not allMyType)
        self.setCheckable(selection.hasContainers() and allMyType)
        self.setChecked(selection.hasContainers() and allMyType)
    
    def doAction(self):
        self.level().setTypes({container: self.type for container in self.selection.containers()})

    @staticmethod
    def addSubmenu(actionConfig, section):
        """Create a submenu in the given action configuration with entries for each type.""" 
        typeSection = translate("TreeActions", "set element type ...")
        for type in elements.CONTAINER_TYPES:
            actionConfig.addActionDefinition(((section, typeSection), 
                                              (typeSection, "setType{}".format(type))),
                                             SetElementTypeAction, type)



class RemoveFromPlaylistAction(TreeAction):
    """This action removes selected elements from a playlist."""
    
    def __init__(self, parent):
        super().__init__(parent, shortcut = "Del")
        self.setText(self.tr('Remove from playlist'))
    
    def initialize(self, selection):
        self.setDisabled(selection.empty())
    
    def doAction(self):
        self.parent().removeSelected()


class ClearPlaylistAction(TreeAction):
    """This action clears a playlist."""
    
    def __init__(self, parent):
        super().__init__(parent, shortcut="Shift+Del")
        self.setText(self.tr('Clear playlist'))
        
    def initialize(self, selection):
        self.setEnabled(self.parent().model().root.hasContents() > 0)
        
    def doAction(self):
        self.parent().model().clear()
        
            
class TagValueAction(TreeAction):
    """This action triggers a dialog to edit the tag value (set sort value, hidden flag, and rename
    the value in all occurences)."""
    
    def initialize(self, selection):
        node = self.parent().currentNode()
        from ..models.browser import TagNode
        if not isinstance(node, TagNode):
            self.setText(self.tr('Edit tagvalue'))
            self.setEnabled(False)
            return
        self.setEnabled(True)
        self.value = node.values[0]
        self.tagPairs = node.tagPairs
        self.setText(self.tr('Edit tagvalue "{}"').format(self.value))
    
    def doAction(self):
        from ..gui.tagwidgets import TagValuePropertiesWidget
        if len(self.tagPairs) > 1:
            tagNames = [tags.get(tagId).name for tagId, valueId in self.tagPairs]
            answer, ok = QtGui.QInputDialog.getItem(self.parent(), self.tr("Choose tag mode"),
                                                    self.tr('Tag:'), tagNames)
            if not ok:
                return
            else:
                tagName, valueId = self.tagPairs[tagNames.index(answer)]
        else:
            tagName, valueId = self.tagPairs[0]
        TagValuePropertiesWidget.showDialog(tags.get(tagName), valueId)


class ExpandOrCollapseAllAction(TreeAction):
    """Expand or collapse (depending on second parameter) all selected nodes that have contents."""
    def __init__(self, parent, expand):
        super().__init__(parent)
        self.expand = expand
        if expand:
            self.setText(self.tr("Expand all"))
        else: self.setText(self.tr("Collapse all"))
        
    def initialize(self, selection):
        self.setEnabled(any(node.hasContents() for node in selection.nodes()))

    def doAction(self):
        view = self.parent()
        method = view.expand if self.expand else view.collapse
        for node in view.selection.nodes():
            if node.hasContents():
                method(view.model().getIndex(node))
            
