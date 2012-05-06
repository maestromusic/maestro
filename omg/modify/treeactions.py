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

# TODO: Move view-specific treeactions to the corresponding modules
from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import modify, tags, models, logging, database as db
from ..database import write
from . import commands
from ..models import levels
from ..constants import DB, DISK, CONTENTS
#from omg.modify.commands import InsertElementsCommand

logger = logging.getLogger(__name__)
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
        dialog = tageditor.TagEditorDialog(self.parent().level,
                                           self.parent().nodeSelection.elements(self.recursive),
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
            self.setEnabled(all(isinstance(element.parent, models.Wrapper) \
                                    or isinstance(element.parent, models.RootNode)
                                for element in selection.elements()))
        elif self.mode == DB:
            self.setEnabled(self.parent().level == REAL and selection.hasElements())
        elif self.mode == DISK:
            self.setEnabled(self.parent().level == REAL and selection.hasFiles())
        
    def doAction(self):
        if self.mode == CONTENTS:
            rootParents = []
            elementParents = {}
            for wrapper in self.parent().nodeSelection.elements():
                parent = wrapper.parent
                if isinstance(parent, models.RootNode):
                    rootParents.append(wrapper)
                else:
                    if parent.element.id not in elementParents:
                        elementParents[parent.element.id] = []
                    elementParents[parent.element.id].append((wrapper.position, wrapper.element.id))
            
            if len(rootParents) > 0:
                self.parent().model().removeWrappers(rootParents)
            if len(elementParents) > 0:
                modify.stack.push(RemoveElementsCommand(self.parent().model().level,
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
        belowRoot = isinstance(elements[0].parent, models.RootNode)
        dialog = MergeDialog(hintTitle, hintRemove, len(mergeIndices) < numSiblings and not belowRoot,
                             self.parent())
        if dialog.exec_() == QtGui.QDialog.Accepted:
            from ..models import wrappertreemodel
            command = wrappertreemodel.MergeCommand(self.parent().model().level,
                         elements[0].parent,
                         mergeIndices,
                         dialog.newTitle(),
                         dialog.removeString(),
                         dialog.adjustPositions())
            if command.elementParent:
                modify.stack.push(command)
            else:
                modify.stack.beginMacro(self.tr("merge elements"))
                modify.stack.push(command)
                oldContents = [node.element.id for node in self.parent().model().root.contents ]
                newContents = oldContents[:]
                mergedIndexes = [ v[0] for v in command.parentChanges.values() ]
                for idx in sorted(mergedIndexes, reverse = True):
                    del newContents[idx]
                newContents[command.insertIndex:command.insertIndex] = [command.containerID]
                rootChangeCom = wrappertreemodel.ChangeRootCommand(self.parent().model(), oldContents, newContents)
                modify.stack.push(rootChangeCom)
                modify.stack.endMacro()

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

class ChangePositionAction(TreeAction):
    
    def __init__(self, parent, type = "free", *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.type = type
        if type == "free":
            self.setText(self.tr("choose position..."))
        elif type == "+1":
            self.setText(self.tr("increase position"))
        elif type == "-1":
            self.setText(self.tr("decrease position"))
        else:
            raise ValueError("{0} is not a valid ChangePositionAction type".format(type))
    
    def initialize(self):
        selection = self.parent().nodeSelection
        if self.type == "free":
            self.setEnabled(False)
        elif self.type == "+1":
            self.setEnabled(selection.singleElement() and selection.elements()[0].position is not None)
        else:
            self.setEnabled(selection.singleElement()
                            and selection.elements()[0].position is not None 
                            and selection.elements()[0].position> 1)
    
    def doAction(self):
        selection = self.parent().nodeSelection
        element = selection.elements()[0]
        parentId = element.parent.id
        if self.type == "+1":
            modify.push(commands.PositionChangeCommand(self.parent().level,
                                                       parentId, [(element.position, element.position+1)]))
        elif self.type == "-1":
            modify.push(commands.PositionChangeCommand(self.parent().level,
                                                       parentId, [(element.position, element.position-1)]))

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
        modify.stack.push(commands.ChangeMajorFlagCommand(self.parent().model().level,
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
        
class NewContainerAction(TreeAction):
    """Action to create a new container inside an editor. Opens a tag editor dialog
    and then inserts the container."""
    
    def __init__(self, parent):
        super().__init__(parent, shortcut = "Ctrl+N")
        self.setText(self.tr('new container'))
        
    def doAction(self):
        
        self.container = models.Container(id = modify.newEditorId(),
                                     contents = None,
                                     tags = tags.Storage(),
                                     flags = [],
                                     position = None,
                                     major = False )
        
        from ..gui.tageditor import TagEditorDialog
        dialog = TagEditorDialog(EDITOR, [self.container], self.parent())
        modify.dispatcher.changes.connect(self.catchTagEvent) #TODO: omg...
        if dialog.exec_() == QtGui.QDialog.Accepted:
            root = self.parent().model().root
            pos = len(root.contents)
            modify.push(InsertElementsCommand(EDITOR,
                                              {root.id: [(pos, self.container)]},
                                              self.tr('new container')))
        modify.dispatcher.changes.disconnect(self.catchTagEvent)
        
    def catchTagEvent(self, event):
        print(event.ids())
        print(self.container.id)
        if list(event.ids()) == [self.container.id]:
            event.applyTo(self.container)
            
        
            
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
            ans, ok = QtGui.QInputDialog.getItem(self.parent(), self.tr("choose tag type"),
                                       self.tr('tag:'), items)
            if not ok:
                return
            else:
                tag = tags.get(ans)
        else:
            tag = next(iter(self.tagValueSpec))
        TagValuePropertiesWidget.showDialog(tag, self.tagValueSpec[tag])
