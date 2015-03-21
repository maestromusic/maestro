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

from maestro import database as db, config, search
from maestro.core import levels, elements


class AddStackAction(QtWidgets.QAction):
    """Display a CreateStackDialog and create a new stack with the configuration from the dialog."""
    def __init__(self, scene, position, parent):
        super().__init__(translate('AddStackAction', 'Add stack...'), parent)
        self.triggered.connect(self._triggered)
        self.scene = scene
        self.position = position
        
    def _triggered(self):
        self.dialog = CreateStackDialog(self.scene, self.position, self.parent())
        self.dialog.exec_()
        
               
class DeleteItemAction(QtWidgets.QAction):
    """Delete the given item from the scene."""
    def __init__(self, item, parent):
        super().__init__(translate('DeleteItemAction', 'Delete item'), parent)
        self.item = item
        self.triggered.connect(self._triggered)
        
    def _triggered(self):
        self.item.scene().removeItem(self.item)
    
    
class ChangeStackTitleAction(QtWidgets.QAction):
    """Let the user change the title of the given stack."""
    def __init__(self, stack, parent):
        super().__init__(translate('ChangeStackTitleAction', 'Change title...'), parent)
        self.item = item
        self.triggered.connect(self._triggered)
        
    def _triggered(self):
        from maestro.gui import dialogs
        title = dialogs.getText(self.tr('Change title'), self.tr('Title: '), self.parent(), self.item.title)
        self.item.title = title
        self.item.update()


class CreateStackDialog(QtWidgets.QDialog):
    """This dialog is used to let the user configure a new stack."""
    def __init__(self, scene, position, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.position = position
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(self.tr("Initial stack contents:")))
        self.emptyButton = QtWidgets.QRadioButton(self.tr("Empty"))
        self.emptyButton.setChecked(True)
        layout.addWidget(self.emptyButton)
        self.allButton = QtWidgets.QRadioButton(self.tr("All elements"))
        layout.addWidget(self.allButton)
        searchLayout = QtWidgets.QHBoxLayout()
        searchLayout.setContentsMargins(0,0,0,0)
        self.searchButton = QtWidgets.QRadioButton(self.tr("Search: "))
        searchLayout.addWidget(self.searchButton)
        from maestro.gui import search
        self.searchBox = search.SearchBox()
        searchLayout.addWidget(self.searchBox, 1) 
        layout.addLayout(searchLayout)
        
        titleLayout = QtWidgets.QHBoxLayout()
        titleLayout.addWidget(QtWidgets.QLabel(self.tr("Title (optional): ")))
        self.titleEdit = QtWidgets.QLineEdit()
        titleLayout.addWidget(self.titleEdit, 1)
        layout.addLayout(titleLayout)
        
        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok
                                               | QtWidgets.QDialogButtonBox.Cancel)
        buttonBox.rejected.connect(self.reject)
        buttonBox.accepted.connect(self.accept)
        layout.addWidget(buttonBox)
    
    def accept(self):
        from maestro.plugins.coverdesk.plugin import StackItem, CoverItem
        stack = StackItem(self.titleEdit.text())
        if self.allButton.isChecked():
            toplevel = list(db.query("""
                    SELECT id
                    FROM {p}elements
                    WHERE domain=? AND id NOT IN (SELECT element_id FROM {p}contents)
                    ORDER BY id
                    """, self.scene.domain.id).getSingleColumn())
            elements = levels.real.collect(toplevel)
            stack.items = [CoverItem(self.scene, el) for el in elements]
        elif self.searchButton.isChecked():
            criterion = self.searchBox.criterion
            if criterion is None:
                return # do not accept
            search.search(criterion, domain=self.scene.domain)
            elids = criterion.result
            toplevel = set(elids)
            toplevel.difference_update(db.query(
                     "SELECT element_id FROM {p}contents WHERE container_id IN ({elids})",
                     elids=db.csList(elids)).getSingleColumn())
            toplevel = sorted(elids)
            elements = levels.real.collect(toplevel)
            stack.items = [CoverItem(self.scene, el) for el in elements]
            
        stack.setPos(self.scene.makePosition(self.position))
        self.scene.addItem(stack)
        super().accept()
        