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
from PyQt4.QtCore import Qt
from maestro.gui import actions


class ShortcutSettings(QtGui.QWidget):
    """Configuration widget for action shortcuts. Shows a tree of registered actions, grouped by context.
    """
    def __init__(self, dialog, panel):
        super().__init__(panel)
        tree = QtGui.QTreeWidget()
        tree.setColumnCount(2)
        tree.setHeaderLabels([self.tr('Action description'), self.tr('Shortcut')])
        contextItems = {}  # the first-layer tree items according to shortcut contexts
        for context, label in actions.contextLabels.items():
            item = QtGui.QTreeWidgetItem(tree, [label])
            item.setData(0, Qt.UserRole, context)
            contextItems[context] = item
        for action in actions.manager.actions.values():
            item = QtGui.QTreeWidgetItem(contextItems[action.context],
                        [action.description, action.shortcut.toString(QtGui.QKeySequence.NativeText)])
            item.setData(0, Qt.UserRole, action)
        tree.expandAll()
        tree.itemActivated.connect(self.handleActivate)
        tree.header().setResizeMode(0, QtGui.QHeaderView.Stretch)
        layout = QtGui.QVBoxLayout()
        layout.addWidget(tree)
        self.setLayout(layout)

    def handleActivate(self, item, column):
        if item.parent() is None:
            return  # clicked on a context item
        action = item.data(0, Qt.UserRole)
        dialog = ShortcutEditDialog(self, action)
        if dialog.exec_():
            sequence = dialog.chooser.keySequence()
            actions.manager.setShortcut(action.identifier, sequence)
            item.setText(1, sequence.toString(QtGui.QKeySequence.NativeText))


class ShortcutEdit(QtGui.QLineEdit):
    """A line edit that displays shortcuts when the user presses one."""

    def __init__(self, current):
        super().__init__()
        if current:
            self.setText(current.toString(QtGui.QKeySequence.NativeText))

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_AltGr, Qt.Key_Meta):
            return
        modifiers = event.modifiers()
        if modifiers & Qt.ShiftModifier:
            key += Qt.SHIFT
        if modifiers & Qt.ControlModifier:
            key += Qt.CTRL
        if modifiers & Qt.AltModifier:
            key += Qt.ALT
        if modifiers & Qt.MetaModifier:
            key += Qt.META
        self.setText(QtGui.QKeySequence(key).toString(QtGui.QKeySequence.NativeText))

    def keySequence(self):
        return QtGui.QKeySequence(self.text())


class ShortcutEditDialog(QtGui.QDialog):
    """Dialog for setting a shortcut of a given action. Displays a short information text, a ShortcutEdit,
    and a number of buttons.
    """
    def __init__(self, parent, action: actions.ActionDefinition):
        super().__init__(parent)
        self.action = action
        #self.resize(130, 50)
        layout = QtGui.QVBoxLayout()
        self.setWindowTitle(self.tr('Enter shortcut'))
        layout.addWidget(QtGui.QLabel(self.tr('Enter shortcut for "{}"').format(action.description)))
        self.chooser = ShortcutEdit(action.shortcut)
        layout.addWidget(self.chooser)
        bbx = QtGui.QDialogButtonBox()
        bbx.addButton(bbx.Cancel)
        bbx.addButton(bbx.Ok)
        removeButton = bbx.addButton(self.tr('Clear'), bbx.ActionRole)
        removeButton.clicked.connect(self.chooser.clear)
        resetButton = bbx.addButton(bbx.Reset)
        resetButton.clicked.connect(self.reset)
        layout.addWidget(bbx)
        bbx.rejected.connect(self.reject)
        bbx.accepted.connect(self.accept)
        self.setLayout(layout)
        self.chooser.setFocus()

    def reset(self):
        self.chooser.setText(self.action.defaultShortcut.toString(QtGui.QKeySequence.NativeText))
