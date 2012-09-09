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

from PyQt4 import QtGui
from PyQt4.QtCore import Qt

from .. import application, utils, filebackends
from ..core import levels, tags, commands
from ..core.nodes import RootNode, Wrapper
from ..models import leveltreemodel
from ..models.browser import BrowserModel
from . import dialogs

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
    
    def __init__(self, parent, recursive):
        super().__init__(parent)
        self.setText(self.tr('edit tags (recursively)') if recursive
                         else self.tr('edit tags'))
        self.recursive = recursive
    
    def initialize(self, selection):
        self.setEnabled(selection.hasWrappers())
    
    def doAction(self):
        """Open a dialog to edit the tags of the currently selected elements (and the children, if
        *recursive* is True). This is called by the edit tags actions in the contextmenu.
        """
        from ..gui import tageditor
        dialog = tageditor.TagEditorDialog(self.parent().model().level,
                                           self.parent().nodeSelection.elements(self.recursive),
                                           self.parent())
        dialog.exec_()
   
   
class RemoveFromParentAction(TreeAction):
    """Action to remove selected elements from the parent container or rootnode.
    """
    
    def __init__(self, parent):
        """Initialize action."""
        super().__init__(parent, shortcut="Del")
        self.setText(self.tr("remove"))
    
    def initialize(self, selection):
        self.setEnabled(not selection.empty() \
                        and all(isinstance(w.parent, Wrapper) or isinstance(w.parent, RootNode)
                                for w in selection.wrappers()))
        
    def doAction(self):
        model = self.parent().model()
        byParent = {}
        for wrapper in self.parent().nodeSelection.wrappers():
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
    
    def __init__(self, parent, text):
        """Initialize the action."""
        super().__init__(parent)
        self.setText(text)
            
    def initialize(self, selection):
        if self.level() is levels.real:
            self.setEnabled(selection.hasElements())
        else:
            self.setEnabled(selection.hasFiles())
    
    def doAction(self):
        pass

class MergeAction(TreeAction):
    """Action to merge selected elements into a new container."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr("merge..."))
    
    def initialize(self, selection):
        self.setEnabled(selection.singleParent())

    def doAction(self):
        selection = self.parent().nodeSelection
        from ..gui.dialogs import MergeDialog
        nodes = sorted(selection.wrappers(), key=lambda wrap: wrap.parent.contents.index(wrap))
        dialog = MergeDialog(self.parent().model(), nodes, self.parent())
        dialog.exec_()


class ClearTreeAction(TreeAction):
    """This action clears a tree model using a simple ChangeRootCommand."""
    
    def __init__(self, parent):
        super().__init__(parent, shortcut = "Shift+Del")
        self.setIcon(utils.getIcon("clear_playlist.png"))
        self.setText(self.tr('clear'))
    
    def initialize(self, selection):
        self.setEnabled(self.parent().model().root.getContentsCount() > 0)
    
    def doAction(self):
        model = self.parent().model()
        application.stack.push(leveltreemodel.ChangeRootCommand(model, [], self.tr('clear')))


class CommitTreeAction(TreeAction):
    """Commit the contents of a LevelTreeModel."""
    
    def __init__(self, parent):
        super().__init__(parent, shortcut="Shift+Enter")
        self.setIcon(QtGui.qApp.style().standardIcon(QtGui.QStyle.SP_DialogSaveButton))
        self.setText(self.tr('commit this tree'))
        
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
        self.setText(self.tr("flatten..."))
        
    def initialize(self, selection):
        self.setEnabled(selection.hasContainers())
        
    def doAction(self):
        from ..gui.dialogs import FlattenDialog
        dialog = FlattenDialog(parent = self.parent())
        if dialog.exec_() == QtGui.QDialog.Accepted:
            flatten(self.parent().level, self.parent().nodeSelection.wrappers(), dialog.recursive())
            

class ChangePositionAction(TreeAction):
    
    def __init__(self, parent, mode = "free", *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.mode = mode
        if mode == "free":
            self.setText(self.tr("choose position..."))
        elif mode == "+1":
            self.setText(self.tr("increase position"))
        elif mode == "-1":
            self.setText(self.tr("decrease position"))
        else:
            raise ValueError("{0} is not a valid ChangePositionAction mode".format(mode))
    
    def initialize(self, selection):
        if self.mode == "free":
            self.setEnabled(False)
        else:
            self.setEnabled(selection.singleParent(True))
        
    def doAction(self):
        from ..gui.dialogs import warning
        selection = self.parent().nodeSelection
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
                                               self.parent().nodeSelection.wrappers(),
                                               self.parent())
        dialog.exec_()

class ToggleMajorAction(TreeAction):
    """This action toggles the "major" attribute of an element."""
    
    def __init__(self, parent):
        super().__init__(parent, shortcut = "Ctrl+M")
        self.setText(self.tr('major?'))
        self.setCheckable(True)
        
    def initialize(self, selection):
        self.setEnabled(selection.hasContainers())
        self.setChecked(all(elem.major for elem in selection.elements() if elem.isContainer()))
        self.state = self.isChecked()
        self.selection = selection
        
    def doAction(self):
        changes = {el:(not self.state) for el in self.selection.elements()
                                       if el.isContainer() and el.major == self.state}
        self.level().setMajorFlags(changes)
        self.toggle()


class RemoveFromPlaylistAction(TreeAction):
    """This action removes selected elements from a playlist."""
    
    def __init__(self, parent):
        super().__init__(parent, shortcut = "Del")
        self.setText(self.tr('remove from playlist'))
    
    def initialize(self, selection):
        self.setDisabled(selection.empty())
    
    def doAction(self):
        self.parent().removeSelected()


class ClearPlaylistAction(TreeAction):
    """This action clears a playlist."""
    
    def __init__(self, parent):
        super().__init__(parent, shortcut="Shift+Del")
        self.setText(self.tr('clear playlist'))
        
    def initialize(self, selection):
        self.setEnabled(self.parent().model().root.hasContents() > 0)
        
    def doAction(self):
        self.parent().backend.clearPlaylist()
        
            
class TagValueAction(TreeAction):
    """This action triggers a dialog to edit the tag value (set sort value, hidden flag, and rename
    the value in all occurences)."""
    
    def initialize(self, selection):
        node = self.parent().currentNode()
        from ..models.browser import ValueNode
        if not isinstance(node, ValueNode):
            self.setText(self.tr('edit tagvalue'))
            self.setEnabled(False)
            return
        self.setEnabled(True)
        self.value = node.values[0]
        self.tagValueSpec = { tags.get(tagId): valueId for tagId, valueId in node.valueIds.items() }
        self.setText(self.tr('edit tagvalue "{}"').format(self.value))
    
    def doAction(self):
        from ..gui.tagwidgets import TagValuePropertiesWidget
        if len(self.tagValueSpec) > 1:
            items = list(map(str, self.tagValueSpec.keys()))
            ans, ok = QtGui.QInputDialog.getItem(self.parent(), self.tr("choose tag mode"),
                                       self.tr('tag:'), items)
            if not ok:
                return
            else:
                tag = tags.get(ans)
        else:
            tag = next(iter(self.tagValueSpec))
        TagValuePropertiesWidget.showDialog(tag, self.tagValueSpec[tag])
