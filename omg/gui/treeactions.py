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

from PyQt4 import QtGui
from PyQt4.QtCore import Qt

from .. import application, utils, filebackends
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


class RenameAction(TreeAction):
    """Action to rename (or move) a file."""
    def __init__(self, parent, text=None, shortcut=None):
        super().__init__(parent, shortcut)
        if text is None:
            self.setText(self.tr('Rename'))
        else:
            self.setText(text)
    
    def initialize(self, selection):
        self.setEnabled(selection.singleWrapper() and selection.hasFiles())
    
    def doAction(self):
        import os.path
        from ..filebackends.filesystem import FileURL
        elem = next(self.parent().selection.fileWrappers()).element
        path = QtGui.QFileDialog.getOpenFileName(self, self.tr("Select new file location"),
                                                 (os.path.dirname(elem.url.path)))
        if path != "":
            newUrl = FileURL(path)
            self.level().renameFiles( {elem: (elem.url, newUrl) })
   
   
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
    
    def __init__(self, parent, mode = "free", *args, **kwargs):
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
        from ..gui.dialogs import warning
        selection = self.parent().selection
        positions = [wrap.position for wrap in selection.wrappers()]
        parent = selection.wrappers()[0].parent.element
        try:
            self.level().shiftPositions(parent, positions, 1 if self.mode == "+1" else -1)
        except levels.ConsistencyError as e:
            warning(self.tr('error'), str(e))


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


class ChangeElementTypeAction(TreeAction):
    """This action allows to change the element type."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr("Change type"))
        
    def initialize(self, selection):
        self.selection = selection
        self.setEnabled(selection.hasContainers())
    
    def doAction(self):
        ChangeTypeDialog(self.level(), list(self.selection.containers())).exec_()
        

class ChangeTypeDialog(QtGui.QDialog):
    """Small dialog to change the element type of the given containers on *level*."""
    def __init__(self, level, containers):
        super().__init__()
        self.level = level
        self.containers = containers
        layout = QtGui.QVBoxLayout(self)
        layout.addWidget(QtGui.QLabel(self.tr("Choose the type for %n container(s):", '',
                                              len(containers))))
        currentType = containers[0].type
        if any(container.type != currentType for container in containers):
            currentType = None
            
        self.typeBox = widgets.ContainerTypeBox(currentType)
        layout.addWidget(self.typeBox)
        
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self._handleOk)
        buttonBox.rejected.connect(self.close)
        layout.addWidget(buttonBox)
    
    def _handleOk(self):
        """Save the chosen type and close the dialog."""
        type = self.typeBox.currentType()
        self.level.setTypes({container: type for container in self.containers})
        self.close()


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
