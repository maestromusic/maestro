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

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from maestro import database as db, stack
from maestro.core import tags
from maestro.gui import actions


class TagValueAction(actions.TreeAction):
    """This action triggers a dialog to edit the tag value (set sort value, hidden flag, and rename
    the value in all occurences)."""

    label = translate('TagValueAction', 'Manage tag value')

    def initialize(self, selection):
        node = self.parent().currentNode()
        from maestro.widgets.browser.nodes import TagNode
        if not isinstance(node, TagNode):
            self.setText(self.tr('Manage tag value'))
            self.setEnabled(False)
            return
        self.setEnabled(True)
        self.value = node.getValues()[0]
        self.tagIds = list(node.tagIds)
        self.setText(self.tr('Manage tag value "{}" ...').format(self.value))

    def doAction(self):
        from maestro.gui.tagwidgets import TagValuePropertiesWidget
        if len(self.tagIds) > 1:
            tagNames = [tags.get(tagId).name for tagId, valueId in self.tagIds]
            answer, ok = QtWidgets.QInputDialog.getItem(self.parent(), self.tr("Choose tag mode"),
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
                                   shortcut=translate('QShortcut', 'Ctrl++'))
ExpandOrCollapseAllAction.register('collapseAll', context='browser', expand=False,
                                   description=translate('ExpandOrCollapseAllAction', 'Collapse all nodes'),
                                   shortcut=translate('QShortcut', 'Ctrl+-'))


class AddToPlaylistAction(actions.TreeAction):
    """Action to play back elements selected in a browser."""

    def __init__(self, parent, identifier, replace):
        super().__init__(parent, identifier)
        self.replace = replace
        if replace:
            self.setText(self.tr('Playback'))
        else:
            self.setText(self.tr('Append to playlist'))

    def doAction(self):
        from maestro.widgets import browser
        mimeData = browser.model.BrowserMimeData(self.parent().selection)
        wrappers = [w.copy() for w in mimeData.wrappers()]
        from maestro.gui import playlist
        playlist.appendToDefaultPlaylist(wrappers, replace=self.replace)

AddToPlaylistAction.register('appendToPL', context='playback',
                             description=translate('AddToPlaylistAction', 'Append selection to playlist'),
                             shortcut=QtGui.QKeySequence(Qt.Key_Enter | Qt.SHIFT), replace=False)
AddToPlaylistAction.register('replacePL', context='playback',
                             description=translate('AddToPlaylistAction', 'Playback selected elements'),
                             shortcut=QtGui.QKeySequence(Qt.Key_P), replace=True)


class GlobalSearchAction(actions.GlobalAction):
    """Global action that jumps to the most current browser's search box."""
    identifier = 'gSearch'
    label = translate('GlobalSearchAction', 'Jump to browser search')

    def doAction(self):
        from maestro import widgets
        browser = widgets.current('browser')
        if browser is not None:
            browser.containingWidget().raise_()
            browser.searchBox.setFocus()

GlobalSearchAction.register('navigation', shortcut=QtGui.QKeySequence.Find)


class CompleteContainerAction(actions.TreeAction):
    """This action replaces the contents of a container wrapper by all contents of the corresponding element.
    """

    label = translate('CompleteContainerAction', 'Complete container')

    def initialize(self, selection):
        self.setEnabled(any(w.isContainer()
                                and (w.contents is None or len(w.contents) < len(w.element.contents))
                            for w in selection.wrappers()))
    
    def doAction(self):
        treeView = self.parent()
        model = treeView.model()
        for wrapper in treeView.selection.wrappers():
            if wrapper.isContainer() and (wrapper.contents is None 
                                            or len(wrapper.contents) < len(wrapper.element.contents)):
                model.beginRemoveRows(model.getIndex(wrapper), 0, len(wrapper.contents)-1)
                wrapper.setContents([])
                model.endRemoveRows()
                model.beginInsertRows(model.getIndex(wrapper), 0, len(wrapper.element.contents)-1)
                wrapper.loadContents(recursive=True)
                model.endInsertRows()

CompleteContainerAction.register('completeContainer', context='browser',
                                 description=translate('CompleteContainerAction', 'Load complete container'))


class HideTagValuesAction(actions.TreeAction):
    """Hide all tag values which appear only below a single selected container (not tags of the container
    itself!). Only tags which appear in a TagLayer of the browser are considered.
    Before tags are hidden a HideTagValuesDialog is displayed, which explains the action and allows the
    user to save some values from being hidden.
    """
    label = translate('HideTagValuesAction', "Hide tag values...")
    
    def initialize(self, selection):
        self.setEnabled(selection.hasContainers())
    
    def doAction(self):
        treeView = self.parent()
        
        # Collect tags
        tags = set()
        from maestro.widgets.browser.model import TagLayer
        for layer in treeView.model().layers:
            if isinstance(layer, TagLayer):
                tags.update(layer.tagList)
        
        # Collect values
        valuesToHide = {tag: [] for tag in tags}
        for wrapper in treeView.selection.wrappers():
            if not wrapper.isContainer():
                continue
            
            # Collect all children ids and tag values 
            wrapper.loadContents(recursive=True)
            ids = []
            allValues = {tag: set() for tag in tags}
            for child in wrapper.getAllNodes(skipSelf=True):
                element = child.element
                ids.append(element.id)
                for tag in tags:
                    if tag in element.tags:
                        allValues[tag].update(db.tags.id(tag, value) for value in element.tags[tag])
                    
            # Check which tag values appear outside the children ids (thus possibly in wrapper itself)
            for tag, vids in allValues.items():
                if len(vids) > 0:
                    result = db.query("""
                        SELECT value_id
                        FROM {p}tags
                        WHERE tag_id=? AND element_id NOT IN ({elids}) AND value_id IN ({vids})
                        GROUP BY value_id
                        """, tag.id, elids=db.csList(ids), vids=db.csList(vids))
                    # We will not hide the values returned from the query because they appear elsewhere
                    vids.difference_update(result.getSingleColumn())
                    # these lists should be disjoint for different wrappers
                    # (unless one is an ancestor of the other one)
                    valuesToHide[tag].extend(vids)
            
            dialog = HideTagValuesDialog(treeView, valuesToHide)
            dialog.exec_()
                
HideTagValuesAction.register('hideTagValues', context='browser',
                 description=translate('HideTagValuesAction',
                                       'Hide tag values which appear only below this container'))


class HideTagValuesDialog(QtWidgets.QDialog):
    """This dialog is shown when the HideTagValuesAction is executed. It displays all values that will
    be hidden to the user and allows him to unselect some of them. In the end, only the selected values
    will be hidden. Values are displayed in a QTreeWidget, grouped by tags.
    """
    def __init__(self, parent, valuesToHide):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(self.tr("The following tag values appear only below a single selected"
                                         " container. You might wish to hide them."))
        label.setWordWrap(True)
        layout.addWidget(label)
            
        # Treeview          
        self.treeWidget = QtWidgets.QTreeWidget()
        self.treeWidget.setHeaderHidden(True)
        layout.addWidget(self.treeWidget)

        tagItems = []
        for tag, valueIds in valuesToHide.items():
            if len(valueIds) > 0:
                tagItem = QtWidgets.QTreeWidgetItem()
                tagItem.setText(0, tag.title)
                tagItem.setData(0, Qt.UserRole, tag)
                # Note: Due to a bug in Qt5 it is possible for the user to select the "partial" state.
                # https://bugreports.qt.io/browse/QTBUG-40060
                tagItem.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsTristate)
                tagItem.setCheckState(0, Qt.Checked)
                valueItems = []
                for vid in valueIds:
                    valueItem = QtWidgets.QTreeWidgetItem()
                    valueItem.setText(0, db.tags.value(tag, vid))
                    valueItem.setData(0, Qt.UserRole, vid)
                    valueItem.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                    valueItem.setCheckState(0, Qt.Checked)
                    valueItems.append(valueItem)
                valueItems.sort(key=lambda item: item.text(0))
                tagItem.addChildren(valueItems)
                tagItems.append(tagItem)
        tagItems.sort(key=lambda item: item.text(0))
        self.treeWidget.addTopLevelItems(tagItems)
        self.treeWidget.expandAll()
        
        # Buttons
        buttonBox = QtWidgets.QDialogButtonBox()
        layout.addWidget(buttonBox)
        buttonBox.addButton(self.tr("Hide values"), QtWidgets.QDialogButtonBox.AcceptRole)
        buttonBox.addButton(QtWidgets.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.close)
        
    def accept(self):
        stack.beginMacro(self.tr("Hide values"), transaction=True)
        from maestro.core import tagcommands
        for i in range(self.treeWidget.topLevelItemCount()):
            tagItem = self.treeWidget.topLevelItem(i)
            tag = tagItem.data(0, Qt.UserRole)
            vids = []
            if tagItem.checkState(0) != Qt.Unchecked:
                for j in range(tagItem.childCount()):
                    valueItem = tagItem.child(j)
                    if valueItem.checkState(0) == Qt.Checked:
                        vids.append(valueItem.data(0, Qt.UserRole))
            if len(vids) > 0:
                stack.push(tagcommands.HiddenAttributeCommand(tag, vids, True))
        stack.endMacro()
        self.close()
