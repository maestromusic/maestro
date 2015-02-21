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

from PyQt4 import QtCore, QtGui
from maestro.core import tags
from maestro.gui import actions

translate = QtCore.QCoreApplication.translate


class TagValueAction(actions.TreeAction):
    """This action triggers a dialog to edit the tag value (set sort value, hidden flag, and rename
    the value in all occurences)."""

    label = translate('TagValueAction', 'Manage tag value')

    def initialize(self, selection):
        node = self.parent().currentNode()
        from ..models.browser import TagNode
        if not isinstance(node, TagNode):
            self.setText(self.tr('Manage tag value'))
            self.setEnabled(False)
            return
        self.setEnabled(True)
        self.value = node.getValues()[0]
        self.tagIds = list(node.tagIds)
        self.setText(self.tr('Manage tag value "{}" ...').format(self.value))

    def doAction(self):
        from ..gui.tagwidgets import TagValuePropertiesWidget
        if len(self.tagIds) > 1:
            tagNames = [tags.get(tagId).name for tagId, valueId in self.tagIds]
            answer, ok = QtGui.QInputDialog.getItem(self.parent(), self.tr("Choose tag mode"),
                                                    self.tr('Tag:'), tagNames)
            if not ok:
                return
            else:
                tagName, valueId = self.tagIds[tagNames.index(answer)]
        else:
            tagName, valueId = self.tagIds[0]
        TagValuePropertiesWidget.showDialog(tags.get(tagName), valueId)

TagValueAction.register('tagValue', context='browser')


class ExpandOrCollapseAllAction(actions.TreeAction):
    """Expand or collapse (depending on second parameter) all selected nodes that have contents."""

    def __init__(self, parent, identifier, expand):
        super().__init__(parent, identifier)
        self.expand = expand
        if expand:
            self.setText(self.tr('Expand all'))
        else:
            self.setText(self.tr('Collapse all'))

    def initialize(self, selection):
        self.setEnabled(any(node.hasContents() for node in selection.nodes()))

    def doAction(self):
        view = self.parent()
        method = view.expand if self.expand else view.collapse
        for node in view.selection.nodes():
            if node.hasContents():
                method(view.model().getIndex(node))

ExpandOrCollapseAllAction.register('expandAll', context='browser', expand=True,
                                   description=translate('ExpandOrCollapseAllAction', 'Expand all nodes'),
                                   shortcut=translate('ExpandOrCollapseAllAction', 'Ctrl++'))
ExpandOrCollapseAllAction.register('collapseAll', context='browser', expand=False,
                                   description=translate('ExpandOrCollapseAllAction', 'Collapse all nodes'),
                                   shortcut=translate('ExpandOrCollapseAllAction', 'Ctrl+-'))
