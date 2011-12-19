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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import modify, tags, models, logging
from ..modify import commands
from ..constants import DB, DISK, CONTENTS, REAL, EDITOR
from omg.modify.commands import RemoveElementsCommand

logger = logging.getLogger(__name__)
translate = QtGui.QApplication.translate


class NamedList(list):
    def __init__(self, name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name
        
class TreeAction(QtGui.QAction):
    """Super class for TreeActions, i.e. Actions for TreeViews."""
    def __init__(self, parent, text = None, shortcut = None, icon = None, tooltip = None):
        super().__init__(parent)
        if shortcut:
            self.setShortcut(shortcut)
        if icon:
            self.setIcon(icon)
        if tooltip:
            self.setToolTip((tooltip))
        self.triggered.connect(self.doAction)
        self.setShortcutContext(Qt.WidgetShortcut)
    
    def initialize(self):
        pass
    
    def doAction(self):
        raise NotImplementedError()

class EditTagsAction(TreeAction):
    """Action to edit tags; exists both in a recursive and non-recursive variant, depending on the argument
    to the constructor."""
    
    def __init__(self, parent, recursive):
        super().__init__(parent)
        self.setText(self.tr('edit tags (recursively)') if recursive
                         else self.tr('edit tags'))
        self.recursive = recursive
    
    def initialize(self):
        self.setEnabled(self.parent().nodeSelection.hasElements())
    
    def doAction(self):
        """Open a dialog to edit the tags of the currently selected elements (and the children, if
        *recursive* is True). This is called by the edit tags actions in the contextmenu.
        """
        from ..gui import tageditor
        dialog = tageditor.TagEditorDialog(self.parent().level,
                                           self.parent().nodeSelection.elements(self.recursive),
                                           self.parent())
        dialog.exec_()

class EditTagsSingleAction(EditTagsAction):
    
    def __init__(self, parent):
        super().__init__(parent, False)
        
class EditTagsRecursiveAction(EditTagsAction):
    
    def __init__(self, parent):
        super().__init__(parent, True)
        
class DeleteAction(TreeAction):
    """Action to remove selected elements."""
    modeText = { DB: translate( __name__, 'delete (from database)' ),
                 CONTENTS: translate( __name__, 'delete (from parent)'),
                 DISK: translate( __name__, 'delete (from disk)')}
    
    def __init__(self, parent, mode, *args, **kwargs):
        """Initialize action with the given *mode* which must be one of DISK, DB, CONTENTS."""
        super().__init__(parent, *args, **kwargs)
        self.setText(self.modeText[mode])
        self.mode = mode
    
    def initialize(self):
        selection = self.parent().nodeSelection
        if self.mode == CONTENTS:
            self.setEnabled(selection.hasElements())
        elif self.mode == DB:
            self.setEnabled(self.parent().level == REAL and selection.hasElements())
        elif self.mode == DISK:
            self.setEnabled(self.parent().level == REAL and selection.hasFiles())
        
    def doAction(self):
        if self.mode == DISK:
            from ..gui.dialogs import question
            if not question(self.tr('WARNING'),
                        self.tr('Removing files from disk cannot be made undone and will clear your undo stack.\n'+
                        'Are you absolutely sure?')):
                return False
        command = RemoveElementsCommand(self.parent().level,
                                        self.parent().nodeSelection.elements(),
                                        self.mode,
                                        text=self.modeText[self.mode])
        modify.push(command)
        if self.mode == DISK:
            modify.stack.clearBoth()

class DeleteFromParentAction(DeleteAction):    
    def __init__(self, parent):
        super().__init__(parent, CONTENTS, shortcut = "Del")

class DeleteFromDatabaseAction(DeleteAction):    
    def __init__(self, parent):
        super().__init__(parent, DB)
        
class DeleteFromDiskAction(DeleteAction):    
    def __init__(self, parent):
        super().__init__(parent, DISK)
             
class MergeAction(TreeAction):
    """Action to merge selected elements into a new container."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr("merge..."))
    
    def initialize(self):
        self.setEnabled(self.parent().nodeSelection.singleParent())
    
    @staticmethod    
    def createMergeHint(elements):
        from functools import reduce
        from ..strutils import longestSubstring
        import string
        
        hintRemove = reduce(longestSubstring,
                   ( ", ".join(elem.tags[tags.TITLE]) for elem in elements )
                 )
        return hintRemove.strip(string.punctuation + string.whitespace), hintRemove
    
    def doAction(self):
        selection = self.parent().nodeSelection
        from ..gui.dialogs import MergeDialog
        elements = selection.elements()
        hintTitle, hintRemove = self.createMergeHint(elements)
        mergeIndices = sorted(elem.parent.index(elem) for elem in elements)
        numSiblings = len(elements[0].parent.contents)
        belowRoot = isinstance(elements[0].parent, models.RootNode)
        dialog = MergeDialog(hintTitle, hintRemove, len(mergeIndices) < numSiblings and not belowRoot,
                             self.parent())
        if dialog.exec_() == QtGui.QDialog.Accepted:
            modify.commands.merge(self.parent().level,
                         elements[0].parent,
                         mergeIndices,
                         dialog.newTitle(),
                         dialog.removeString(),
                         dialog.adjustPositions())

class FlattenAction(TreeAction):
    """Action to "flatten out" containers, i.e. remove them and replace them by their
    children."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr("flatten..."))
        
    def initialize(self):
        self.setEnabled(self.parent().nodeSelection.hasContainers())
        
    def doAction(self):
        from ..gui.dialogs import FlattenDialog
        dialog = FlattenDialog(parent = self.parent())
        if dialog.exec_() == QtGui.QDialog.Accepted:
            modify.commands.flatten(self.parent().level,
                                    self.parent().nodeSelection.elements(),
                                    dialog.recursive()
                                    )

class CommitAction(TreeAction):
    """Action to commit all current editors."""
    def __init__(self, parent):
        super().__init__(parent, shortcut = 'Ctrl+Return')
        self.setText(self.tr("commit (all editors)"))
        
    def doAction(self):
        modify.push(modify.commands.CommitCommand())

class MatchTagsFromFilenamesAction(TreeAction):
    """An action to trigger a dialog that matches tags from file names. Will be enabled only if at least
    one file is selected."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr('match tags from filename'))
    
    def initialize(self):
        self.setEnabled(self.parent().nodeSelection.hasFiles())
        
    def doAction(self):
        """Open a TagMatchDialog for the selected elements."""
        from ..gui import tagmatchdialog
        dialog = tagmatchdialog.TagMatchDialog(self.parent().level,
                                               self.parent().nodeSelection.elements(),
                                               self.parent())
        dialog.exec_()

class ToggleMajorAction(TreeAction):
    """This action toggles the "major" attribute of an element."""
    
    def __init__(self, parent):
        super().__init__(parent, shortcut = "Ctrl+M")
        self.setText(self.tr('major?'))
        self.setCheckable(True)
        
    def initialize(self):
        selection = self.parent().nodeSelection
        self.setEnabled(selection.hasElements())
        self.setChecked(all(element.major for element in selection.elements()))
        self.state = self.isChecked()
        self.selection = selection
        
    def doAction(self):
        for element in self.selection.elements():
            if element.major == self.state:
                modify.push(commands.ChangeMajorFlagCommand(self.parent().level, element))
        self.toggle()
                

class RemoveFromPlaylistAction(TreeAction):
    """This action removes selected elements from a playlist."""
    
    def __init__(self, parent):
        super().__init__(parent, shortcut = "Del")
        self.setText(self.tr('remove from playlist'))
    
    def initialize(self):
        self.setDisabled(self.parent().nodeSelection.empty())
    
    def doAction(self):
        self.parent().removeSelected()
        
class ClearPlaylistAction(TreeAction):
    """This action clears a playlist."""
    
    def __init__(self, parent):
        super().__init__(parent, shortcut = "Shift+Del")
        self.setText(self.tr('clear playlist'))
        
    def initialize(self):
        self.setEnabled(len(self.parent().backend.paths) > 0)
        
    def doAction(self):
        self.parent().backend.clearPlaylist()

class ClearEditorAction(TreeAction):
    """This action clears an editor."""
    
    def __init__(self, parent):
        super().__init__(parent, shortcut = "Shift+Del")
        self.setText(self.tr('clear editor'))
    
    def initialize(self):
        self.setEnabled(len(self.parent().model().root.contents) > 0)
    
    def doAction(self):
        modify.push(RemoveElementsCommand(EDITOR, self.parent().model().root.contents, CONTENTS,
                                  self.tr('clear editor')))
            
#class TagValueAction(TreeAction):
#    """This action triggers a dialog to edit the tag value (set sort value, hidden flag, and rename
#    the value in all occurences)."""
#    
#    text = translate(__name__, 'edit value')
#    
#    def __init__(self, tag, value, valueId, multiple = False):
#        super().__init__()
#        if multiple:
#            self.setText(self.tr('as {}').format(tag))
#        else:
#            self.setText(self.tr('edit {} value "{}"').format(tag, value))
#        self.valueId = valueId
#        self.tag = tag
#    
#    def initialize(self, *args):
#        pass
#       
#    def doAction(self):
#        from ..gui.tagwidgets import TagValuePropertiesWidget
#        TagValuePropertiesWidget.showDialog(self.tag, self.valueId)

#class TagValueHybridAction(HybridTreeAction):
#    
#    def initialize(self, selection, treeview):
#        if selection.empty():
#            self.visible = False
#            return
#        from ..models.browser import ValueNode
#        valueNode = None
#        for node in selection.nodes():
#            while not isinstance(node, ValueNode):
#                node = node.parent
#                if valueNode or node.parent is None:
#                    # Either there is more than one ValueNode or none
#                    # (the latter happens for elements sorted under a Various/Unknown node
#                    self.visible = False
#                    return
#            else:
#                valueNode = node
#        self.visible = True
#        self.actions = []
#        multiple = len(valueNode.valueIds) > 1
#        
#        for tagId, valueId in valueNode.valueIds.items():
#            self.actions.append(TagValueAction(tags.get(tagId), valueNode.values[0], valueId, multiple))
#        if multiple:
#            subActions = self.actions
#            self.actions = [NamedList(translate(__name__,'edit value "{}"').format(valueNode.values[0]), subActions)]