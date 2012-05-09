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

# TODO: Move view-specific treeactions to the corresponding modules
from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import commands
from .. import application, database as db
from ..constants import DB, DISK, CONTENTS
from ..core import levels, tags
from ..core.nodes import RootNode, Wrapper

translate = QtGui.QApplication.translate


class NamedList(list):
    #TODO: comment
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
        dialog = tageditor.TagEditorDialog(self.parent().model().level,
                                           [w.element for w in self.parent().nodeSelection.elements(self.recursive)],
                                           self.parent())
        dialog.exec_()

class RemoveElementsCommand(QtGui.QUndoCommand):
    
    def __init__(self, level, removals, text):
        super().__init__()
        self.setText(text)
        self.level = level
        self.removals = removals
        
        
    def redo(self):
        if self.level is levels.real:
            db.transaction()
        for parentId, removals in self.removals.items():
            for pos,id in removals:
                self.level.removeChild(parentId, pos)
            if self.level is levels.real:
                db.write.removeContents([ (parentId, pos) for pos,id in removals])
        if self.level is levels.real:
            db.commit()
        self.level.emitEvent(contentIds= list(self.removals.keys()))
    
    def undo(self):
        if self.level is levels.real:
            db.transaction()
        for parentId, removals in self.removals.items():
            for pos,id in removals:
                self.level.insertChild(parentId, pos, id)
            if self.level is levels.real:
                db.write.addContents([ (parentId, pos, id) for pos,id in removals])
        if self.level is levels.real:
            db.commit()
        self.level.emitEvent(contentIds= list(self.removals.keys()))
   
class DeleteAction(TreeAction):
    """Action to remove selected elements. Works for editor and browser.
    
    The deletion mode (CONTENTS, DB, or DISK) has to be passed to the constructor. The
    behavior is as follows:
    - CONTENTS: remove elements from their parents. If the parent is an element, the level
                gets updated. If the parent is the RootNode, the element is removed there,
                leaving the level untouched.
    - DB (only in 'real' level): remove selected elements from the database
    - DISK: remove selected files from disk. If the files are contained in the DB, they
            are also removed from there."""
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
            self.setEnabled(not selection.empty() and all(isinstance(element.parent, Wrapper) \
                                    or isinstance(element.parent, RootNode)
                                for element in selection.elements()))
        elif self.mode == DB:
            self.setEnabled(self.parent().level == REAL and selection.hasElements())
        elif self.mode == DISK:
            self.setEnabled(self.parent().level == REAL and selection.hasFiles())
        
    def doAction(self):
        model = self.parent().model()
        if self.mode == CONTENTS:
            rootParents = []
            elementParents = {}
            for wrapper in self.parent().nodeSelection.elements():
                parent = wrapper.parent
                if isinstance(parent, RootNode):
                    rootParents.append(parent.contents.index(wrapper))
                else:
                    if parent.element.id not in elementParents:
                        elementParents[parent.element.id] = []
                    elementParents[parent.element.id].append((wrapper.position, wrapper.element.id))
            
            if len(rootParents) > 0:
                from ..models.rootedtreemodel import ChangeRootCommand
                newContents = model.root.contents[:]
                for idx in sorted(rootParents, reverse = True):
                    del newContents[idx]
                application.stack.push(ChangeRootCommand(model, model.root.contents, newContents))
            if len(elementParents) > 0:
                application.stack.push(RemoveElementsCommand(self.parent().model().level,
                                                             elementParents,
                                                             text=self.modeText[self.mode]))
        else:
            raise NotImplementedError()

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
        hintTitle, hintRemove = self.createMergeHint([wrap.element for wrap in elements])
        mergeIndices = sorted(elem.parent.index(elem) for elem in elements)
        numSiblings = len(elements[0].parent.contents)
        belowRoot = isinstance(elements[0].parent, RootNode)
        dialog = MergeDialog(hintTitle, hintRemove, len(mergeIndices) < numSiblings and not belowRoot,
                             self.parent())
        if dialog.exec_() == QtGui.QDialog.Accepted:
            from ..models import rootedtreemodel
            command = rootedtreemodel.MergeCommand(self.parent().model().level,
                         elements[0].parent,
                         mergeIndices,
                         dialog.newTitle(),
                         dialog.removeString(),
                         dialog.adjustPositions())
            if command.elementParent:
                application.stack.push(command)
            else:
                application.stack.beginMacro(self.tr("merge elements"))
                application.stack.push(command)
                oldContents = [node.element.id for node in self.parent().model().root.contents ]
                newContents = oldContents[:]
                mergedIndexes = [ v[0] for v in command.parentChanges.values() ]
                for idx in sorted(mergedIndexes, reverse = True):
                    del newContents[idx]
                newContents[command.insertIndex:command.insertIndex] = [command.containerID]
                rootChangeCom = rootedtreemodel.ChangeRootCommand(self.parent().model(), oldContents, newContents)
                application.stack.push(rootChangeCom)
                application.stack.endMacro()

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
            application.commands.flatten(self.parent().level,
                                         self.parent().nodeSelection.elements(),
                                         dialog.recursive()
                                         )

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
    
    def initialize(self):
        selection = self.parent().nodeSelection
        if self.mode == "free":
            self.setEnabled(False)
        else:
            self.setEnabled(selection.singleParent(True))
        
    def doAction(self):
        from ..gui.dialogs import warning
        selection = self.parent().nodeSelection
        positions = [wrap.position for wrap in selection.elements()]
        parentId = selection.elements()[0].parent.element.id
        try:
            application.stack.push(commands.ChangePositionsCommand(self.parent().model().level,
                                                                   parentId, positions,
                                                                   1 if self.mode == "+1" else -1))
        except levels.ConsistencyError as e:
            warning(self.tr('error'), str(e))

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
        self.setChecked(all(w.isContainer() and w.element.major for w in selection.elements()))
        self.state = self.isChecked()
        self.selection = selection
        
    def doAction(self):
        application.stack.push(commands.ChangeMajorFlagCommand(self.parent().model().level,
                        [w.element.id for w in self.selection.elements() if w.element.major == self.state]))
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
        
            
class TagValueAction(TreeAction):
    """This action triggers a dialog to edit the tag value (set sort value, hidden flag, and rename
    the value in all occurences)."""
    
    def initialize(self):
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
