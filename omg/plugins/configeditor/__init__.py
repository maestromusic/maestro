# -*- coding: utf-8 -*-
# Copyright 2011 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
from omg import application, config
import functools
translate = functools.partial(QtGui.QApplication.translate, 'ConfigEditor')

_action = None
def enable():
    global _action
    _action = QtGui.QAction(application.mainWindow)
    _action.setText(translate("Preferences"))
    _action.triggered.connect(showDialog)
    options = config.optionObject
    #print(len(options))
    #print(list(options))

def mainWindowInit():
    application.mainWindow.menus['edit'].addAction(_action)

def disable():
    application.mainWindow.menus['edit'].removeAction(_action)
def showDialog():
    pd = PreferencesDialog(application.mainWindow)
    pd.show()


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
    for subname in section:
        subsect = section[subname]
        if isinstance(subsect, config.ConfigSection):
            populateSections(subsect, item)
    item.setExpanded(True)

class ConfigItem(QtGui.QTableWidgetItem):
    def __init__(self, widget, option):
        super().__init__()
        self.option = option
        if option.fileValue is None:
            self.setText(option._export(option.default))
        else:
            self.setText(option._export(option.fileValue))
            if self.text() != option._export(option.default):
                f = self.font()
                f.setBold(True)
                self.setFont(f)
        self.dirty = False

        self.widget = widget
        
    def data(self, role = Qt.DisplayRole):
        if role == Qt.ToolTipRole:
            if self.option.fileValue is None:
                return translate('default value: not set in config file')
            elif self.text() != self.option._export(self.option.default):
                return translate('value differs from default')
            else:
                return translate('set to default value in config file')
        return super().data(role)
    def setData(self, role, value):
        
        if role == Qt.EditRole:
            try:
                self.option._import(value)
            except config.ConfigError:
                QtGui.QMessageBox.critical(self.widget, translate('invalid entry'),
                                           translate('the data you entered is not valid for this option'))
                return
            self.dirty = True
            self.widget.dirty = True
            if (self.option.fileValue is None and value != self.option._export(self.option.default)) or \
                        (self.option.fileValue is not None and value != self.option._export(self.option.fileValue)):
                f = self.font()
                f.setBold(True)
                self.setFont(f)
        super().setData(role, value)
    
    def resetToDefault(self):
        self.setData(Qt.EditRole, self.option._export(self.option.default))
        
    def save(self):
        self.option.updateFileValue(self.text())
        self.dirty = False
        
class ConfigSectionWidget(QtGui.QTableWidget):
    def __init__(self, section, parent = None):
        super().__init__(parent)
        self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.setSection(section)
        self.contextMenu = QtGui.QMenu(self)
        self.resetToDefaultAction = QtGui.QAction(self.tr('reset to default'), self)
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
        self.setHorizontalHeaderLabels(['option', 'value'])
        if isinstance(section, str):
            parts = section.split('.')[1:]
            s = config.optionObject
            for p in parts:
                s = s[p]
            section = s
        options = [section[x] for x in section if isinstance(section[x], config.ConfigOption)]
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
        config.optionObject.write()
        self.dirty = False

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if item is not None:
            self.contextMenu.popup(event.globalPos() + QtCore.QPoint(2,2))
        event.accept()
class PreferencesDialog(QtGui.QDialog):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setModal(False)
        mainLayout = QtGui.QVBoxLayout(self)
        layout = QtGui.QHBoxLayout()
        self.tree = QtGui.QTreeWidget()
        self.tree.setHeaderLabel('section')
        options = config.optionObject
        populateSections(options, self.tree)
        self.sectionWidget = ConfigSectionWidget('<Default>')
        self.tree.currentItemChanged.connect(self._handleCurrentItemChanged)
        self.tree.setSelectionMode(self.tree.NoSelection)
        self.tree.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Minimum)
        self.sectionWidget.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        layout.addWidget(self.tree)
        layout.addWidget(self.sectionWidget)
        layout.setStretchFactor(self.sectionWidget, 1)
        mainLayout.addLayout(layout)
        cancelButton = QtGui.QPushButton(self.tr('cancel'))
        cancelButton.clicked.connect(self.close)
        saveButton = QtGui.QPushButton(self.tr('save'))
        saveButton.clicked.connect(self.sectionWidget.save)
        bottomLayout = QtGui.QHBoxLayout()
        bottomLayout.addStretch()
        bottomLayout.addWidget(cancelButton)
        bottomLayout.addWidget(saveButton)
        mainLayout.addLayout(bottomLayout)
        self.setLayout(mainLayout)
        self.resize(QtCore.QSize(600,400))
        self._ignoreDirty = False
    def _handleCurrentItemChanged(self, current, previous):
        if self._ignoreDirty:
            return
        if self.sectionWidget.dirty:
            ans = QtGui.QMessageBox.question(self, self.tr('unsaved changes'),
                                             self.tr('Do you want to save your changes before proceeding?'),
                                             QtGui.QMessageBox.Cancel | QtGui.QMessageBox.Ignore | QtGui.QMessageBox.Save)
            if ans == QtGui.QMessageBox.Save:
                self.sectionWidget.save()
            elif ans == QtGui.QMessageBox.Cancel:
                self._ignoreDirty = True
                
                self.tree.setCurrentItem(previous)
                
                #self.tree.setSelect
                self._ignoreDirty = False
                return
            
        self.sectionWidget.setSection(current.data(0, Qt.UserRole))