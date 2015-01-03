# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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

import functools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ... import config
from ...gui import preferences

translate = QtCore.QCoreApplication.translate


def enable():
    preferences.addPanel(
        path = 'plugins/configeditor',
        title = translate("ConfigEditor", "Configuration Editor"),
        callable = PreferencesDialog,
        description = translate("ConfigEditor", "Edit the configuration file <i>{}</i>.")
                                .format(config.getFile(config.options).path),
    )


def disable():
    preferences.removePanel('plugins/configeditor')
    

def populateSections(section, parent):
    item = QtGui.QTreeWidgetItem(parent)
    item.setText(0, str(section))
    if isinstance(parent, QtGui.QTreeWidget):
        prefix = ''
    else:
        prefix = parent.data(0, Qt.UserRole) + '.'
    string = prefix + str(section)
    item.setData(0, Qt.UserRole, string)
    item.setToolTip(0, string)
    for subsect in section.getSubsections():
        populateSections(subsect, item)
    item.setExpanded(True)


class ConfigItem(QtGui.QTableWidgetItem):
    def __init__(self, widget, option):
        super().__init__()
        self.option = option
        
        if option.type is bool:
            self.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            self.setCheckState(Qt.Checked if option.getValue() else Qt.Unchecked)
        self.setText(str(option.getValue()))
        if option.getValue() != option.default:
            f = self.font()
            f.setBold(True)
            self.setFont(f)
        self.dirty = False
        self.widget = widget
        
    def data(self, role=Qt.DisplayRole):
        if role == Qt.ToolTipRole:
            if self.option.getValue() == self.option.default:
                return translate("ConfigEditor", 'Default value')
            else: return translate("ConfigEditor", 'Value differs from default')
        if role == Qt.DisplayRole and self.option.type is bool:
            return self.checkState() == Qt.Checked
        return super().data(role)
    
    def setData(self, role, value):
        
        if role == Qt.EditRole:
            try:
                self.option.fromString(value)
            except config.ConfigError:
                QtGui.QMessageBox.critical(self.widget, translate("ConfigEditor", 'Invalid entry'),
                            translate("ConfigEditor", 'The data you entered is not valid for this option'))
                return
            self.dirty = True
            self.widget.dirty = True
            f = self.font()
            f.setBold(self.option.getValue() != self.option.default)
            self.setFont(f)
        super().setData(role, value)
    
    def resetToDefault(self):
        self.option.resetToDefault()
        self.dirty = True
        self.widget.dirty = True
        super().setData(Qt.EditRole,self.option.export())
        
    def save(self):
        self.option.setValue(self.option.parseString(self.text()))
        self.dirty = False
        
        
class ConfigSectionWidget(QtGui.QTableWidget):
    def __init__(self, section, parent=None):
        super().__init__(parent)
        self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.setSection(section)
        self.contextMenu = QtGui.QMenu(self)
        self.resetToDefaultAction = QtGui.QAction(self.tr('Reset to default'), self)
        self.contextMenu.addAction(self.resetToDefaultAction)
        self.resetToDefaultAction.triggered.connect(self.setSelectedToDefault)
        
    def setSelectedToDefault(self):
        items = [i for i in self.selectedItems() if i.column() == 1]
        for i in items:
            i.resetToDefault()
    def setSection(self, section):
        self.clear()
        self.dirty = False
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels([self.tr('Option'), self.tr('value')])
        if isinstance(section, str):
            parts = section.split('.')[1:]
            s = config.getFile(config.options).section
            for p in parts:
                s = s.members[p]
            section = s
        options = list(section.getOptions())
        self.setRowCount(len(options))
        for i, opt in enumerate(options):
            nameItem = QtGui.QTableWidgetItem(opt.name)
            nameItem.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            nameItem.setToolTip(opt.description)
            self.setItem(i, 0, nameItem)

            valueItem = ConfigItem(self, opt)            
            self.setItem(i, 1, valueItem)
        self.resizeColumnsToContents()
    
    def save(self):
        '''Saves everything in the current section to the config file.'''
        for row in range(self.rowCount()):
            item = self.item(row, 1)
            item.save()
        config.getFile(config.options).write()
        self.dirty = False

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if item is not None:
            self.contextMenu.popup(event.globalPos() + QtCore.QPoint(2,2))
        event.accept()
        
        
class PreferencesDialog(QtGui.QWidget):
    def __init__(self, dialog, panel):
        super().__init__(panel)
        mainLayout = QtGui.QVBoxLayout(self)
        layout = QtGui.QHBoxLayout()
        self.tree = QtGui.QTreeWidget()
        self.tree.setHeaderLabel(self.tr('Section'))
        options = config.getFile(config.options).section
        populateSections(options, self.tree)
        self.sectionWidget = ConfigSectionWidget(self.tr('<Main>'))
        self.tree.currentItemChanged.connect(self._handleCurrentItemChanged)
        self.tree.setSelectionMode(self.tree.NoSelection)
        self.tree.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Minimum)
        self.sectionWidget.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        layout.addWidget(self.tree)
        layout.addWidget(self.sectionWidget)
        layout.setStretchFactor(self.sectionWidget, 1)
        mainLayout.addLayout(layout)
        saveButton = QtGui.QPushButton(self.tr('Save'))
        saveButton.clicked.connect(self.sectionWidget.save)
        panel.buttonBar.addStretch(1)
        panel.buttonBar.addWidget(saveButton)
        self.setLayout(mainLayout)
        self._ignoreDirty = False
        
    def _handleCurrentItemChanged(self, current, previous):
        if self._ignoreDirty:
            return
        if self.sectionWidget.dirty:
            ans = QtGui.QMessageBox.question(self, self.tr('Unsaved changes'),
                                             self.tr('Do you want to save your changes before proceeding?'),
                                             QtGui.QMessageBox.Cancel | QtGui.QMessageBox.Ignore |
                                             QtGui.QMessageBox.Save)
            if ans == QtGui.QMessageBox.Save:
                self.sectionWidget.save()
            elif ans == QtGui.QMessageBox.Cancel:
                self._ignoreDirty = True
                
                self.tree.setCurrentItem(previous)
                
                #self.tree.setSelect
                self._ignoreDirty = False
                return
            
        self.sectionWidget.setSection(current.data(0, Qt.UserRole))
        