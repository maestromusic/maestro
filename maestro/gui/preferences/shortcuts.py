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

    def __init__(self, dialog, panel):
        super().__init__(panel)

        tree = QtGui.QTreeWidget()
        tree.setColumnCount(2)
        tree.setHeaderLabels([self.tr('Action'), self.tr('Keys')])
        contextItems = {}
        for context, label in actions.contextLabels.items():
            item = QtGui.QTreeWidgetItem(tree, [label])
            item.setData(0, Qt.UserRole, context)
            contextItems[context] = item
        for action in actions.manager.actions.values():
            item = QtGui.QTreeWidgetItem(contextItems[action.context], [action.description,
                                                                        action.shortcut.toString()])
            item.setData(1, Qt.UserRole, action.shortcut)
            item.setData(0, Qt.UserRole, action.identifier)
        tree.expandAll()
        tree.itemDoubleClicked.connect(self.handleDoubleClick)
        tree.header().setResizeMode(0, QtGui.QHeaderView.Stretch)
        layout = QtGui.QVBoxLayout()
        layout.addWidget(tree)
        self.setLayout(layout)

    def handleDoubleClick(self, item, column):
        if item.parent() is None:
            return  # category clicked
        dialog = ChooseShortcutDialog(self)
        seq = dialog.exec_()
        if seq:
            identifier = item.data(0, Qt.UserRole)
            actions.manager.setShortcut(identifier, seq)


class ShortcutCaptureWidget(QtGui.QLabel):

    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr('Enter keyboard shortcut ...'))
        self.keySequence = None

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_AltGr, Qt.Key_Meta):
            return
        if key == Qt.Key_Escape:
            self.parent().reject()
        else:
            modifiers = event.modifiers()
            if modifiers & Qt.ShiftModifier:
                key += Qt.SHIFT
            if modifiers & Qt.ControlModifier:
                key += Qt.CTRL
            if modifiers & Qt.AltModifier:
                key += Qt.ALT
            if modifiers & Qt.MetaModifier:
                key += Qt.META
            self.keySequence = QtGui.QKeySequence(key)
            self.parent().accept()


class ChooseShortcutDialog(QtGui.QDialog):

    def __init__(self, parent):
        super().__init__(parent)
        self.resize(130, 50)
        self.keySequence = None
        layout = QtGui.QVBoxLayout()
        self.chooser = ShortcutCaptureWidget(self)
        layout.addWidget(self.chooser)
        bbx = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel)
        layout.addWidget(bbx)
        bbx.rejected.connect(self.reject)
        self.setLayout(layout)
        self.chooser.setFocus()

    def exec_(self):
        if super().exec_():
            return self.chooser.keySequence

