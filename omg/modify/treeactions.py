# -*- coding: utf-8 -*-
# Copyright 2011 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ..gui import mainwindow
from .. import modify, tags
from ..modify import commands
from ..constants import *

translate = QtGui.QApplication.translate

class TreeAction(QtGui.QAction):
    """Super class for TreeActions, i.e. Actions on TreeViews that can be called by a context menu."""
    text = 'changeme'
    def __init__(self, text = None):
        super().__init__(text or self.text, mainwindow.mainWindow)
        self.triggered.connect(self.doAction)
        
    def initialize(self, selectionProperties, treeview):
        raise NotImplementedError()
    
    def doAction(self):
        raise NotImplementedError()
    
class EditTagsAction(TreeAction):
    """Action to edit tags; exists both in a recursive and non-recursive variant, depending on the argument
    to the constructor."""
    
    def __init__(self, recursive):
        super().__init__(translate(__name__, 'edit tags (recursively)') if recursive
                         else translate(__name__, 'edit tags'))
        self.recursive = recursive
    
    def initialize(self, selection, treeview):
        self.setEnabled(selection.hasElements())
        self.selection = selection
        self.treeview = treeview
    
    def doAction(self):
        """Open a dialog to edit the tags of the currently selected elements (and the children, if
        *recursive* is True). This is called by the edit tags actions in the contextmenu.
        """
        from ..gui import tageditor
        dialog = tageditor.TagEditorDialog(self.treeview.level,
                                           self.selection.elements(self.recursive),
                                           self.treeview)
        dialog.exec_()

class DeleteAction(TreeAction):
    """Action to remove selected elements."""
    
    textForMode = {DB:translate(__name__, 'delete from database'),
                     DISK:translate(__name__, 'delete from disk'),
                     CONTENTS:translate(__name__, 'delete from parent')}
    def __init__(self, mode):
        """Initialize action with the given *mode* which must be one of DISK, DB, CONTENTS."""
        super().__init__(self.textForMode[mode])
        self.mode = mode
    
    def initialize(self, selection, treeview):
        if self.mode == CONTENTS:
            self.setEnabled(selection.hasElements())
        elif self.mode == DB:
            self.setEnabled(treeview.level == REAL and selection.hasElements())
        elif self.mode == DISK:
            self.setEnabled(treeview.level == REAL and selection.hasFiles())
        self.selection = selection
        self.level = treeview.level
        
    def doAction(self):
        from .. import modify
        from ..modify.commands import RemoveElementsCommand
        command = RemoveElementsCommand(self.level, self.selection.elements(), self.mode, text=self.textForMode[self.mode])
        modify.push(command)
        
class MergeAction(TreeAction):
    """Action to merge selected elements into a new container."""
    
    text = translate(__name__, 'merge...')
    
    def initialize(self, selection, treeview):
        self.setEnabled(selection.singleParent())
        self.selection = selection
        self.treeview = treeview
    
    @staticmethod    
    def createMergeHint(elements):
        from functools import reduce
        from ..utils import longestSubstring
        import string
        
        hintRemove = reduce(longestSubstring,
                   ( ", ".join(elem.tags[tags.TITLE]) for elem in elements )
                 )
        return hintRemove.strip(string.punctuation + string.whitespace), hintRemove
    
    def doAction(self):
        from .tagwidgets import MergeDialog
        elements = self.selection.elements()
        hintTitle, hintRemove = self.createMergeHint(elements)
        mergeIndices = sorted(elem.parent.index(elem) for elem in elements)
        numSiblings = len(elements[0].parent.contents)
        belowRoot = isinstance(elements[0].parent, models.RootNode)
        dialog = MergeDialog(hintTitle, hintRemove, len(mergeIndices) < numSiblings and not belowRoot, self.treeview)
        if dialog.exec_() == QtGui.QDialog.Accepted:
            modify.merge(self.treeview.level,
                         elements[0].parent,
                         mergeIndices,
                         dialog.newTitle(),
                         dialog.removeString(),
                         dialog.adjustPositions())
            
class MatchTagsFromFilenamesAction(TreeAction):
    """An action to trigger a dialog that matches tags from file names. Will be enabled only if at least
    one file is selected."""
     
    text = translate(__name__, 'match tags from filename')
    
    def initialize(self, selection, treeview):
        self.setEnabled(selection.hasFiles())
        self.selection = selection
        self.treeview = treeview
        
    def doAction(self):
        """Open a TagMatchDialog for the selected elements."""
        from . import tagmatchdialog
        dialog = tagmatchdialog.TagMatchDialog(self.treeview.level, self.selection.elements(unique = True), self.treeview)
        dialog.exec_()

class ToggleMajorAction(TreeAction):
    """This action toggles the "major" attribute of an element."""
    
    text = translate(__name__, 'major?')
    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        
    def initialize(self, selection, treeview):
        self.setEnabled(selection.hasElements())
        self.setChecked(all(element.major for element in selection.elements()))
        self.state = self.isChecked()
        self.selection = selection
        self.level = treeview.level
        
    def doAction(self):
        for element in self.selection.elements():
            if element.major == self.state:
                modify.push(commands.ChangeMajorFlagCommand(self.level, element)) 
                

class TagValueAction(TreeAction):
    """This action triggers a dialog to edit the tag value (set sort value, hidden flag, and rename
    the value in all occurences)."""
    
    text = translate(__name__, 'edit value')
    
    def initialize(self, selection, treeview):
        from ..models.browser import ValueNode
        if len(selection.nodes()) == 1 and isinstance(selection.nodes()[0], ValueNode):
            self.setEnabled(True)
            node = selection.nodes()[0]
            print(node.valueIds)
            tagID = list(node.valueIds.keys())[0] #TODO: handle multiple value IDs
            self.valueId = node.valueIds[tagID]
            self.tag = tags.get(tagID)
            self.setText(self.tr('edit value [as {}]'.format(self.tag))) 
        else:
            self.setEnabled(False)
            self.setText(self.tr('edit value'))
        
    def doAction(self):
        from ..gui.tagwidgets import TagValuePropertiesWidget
        TagValuePropertiesWidget.showDialog(self.tag, self.valueId)
