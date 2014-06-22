# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2013-2014 Martin Altmayer, Michael Helmling
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

import os.path

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from ... import application, filesystem, config, stack, utils


class FilesystemSettings(QtGui.QWidget):
    columns = [
        ("name",   translate("FilesystemSettings", "Name")),
        ("path",   translate("FilesystemSettings", "Path")),
        ("domain", translate("FilesystemSettings", "Domain")),
        ("enable", translate("FilesystemSettings", "Check"))
    ]

    def __init__(self, dialog, panel):
        super().__init__(panel)
        layout = QtGui.QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        
        buttonBar = QtGui.QToolBar()
        self.layout().addWidget(buttonBar)
        addButton = QtGui.QToolButton()
        addButton.setIcon(utils.getIcon("add.png"))
        addButton.setToolTip("Add source")
        addButton.clicked.connect(self._handleAddButton)
        buttonBar.addWidget(addButton)
        self.undoButton = QtGui.QToolButton()
        self.undoButton.setIcon(utils.getIcon("undo.png"))
        self.undoButton.clicked.connect(stack.undo)
        buttonBar.addWidget(self.undoButton)
        self.redoButton = QtGui.QToolButton()
        self.redoButton.setIcon(utils.getIcon("redo.png"))
        self.redoButton.clicked.connect(stack.redo)
        buttonBar.addWidget(self.redoButton)
        self.deleteButton = QtGui.QToolButton()
        self.deleteButton.setIcon(utils.getIcon("delete.png"))
        self.deleteButton.setToolTip(self.tr("Delete source"))
        self.deleteButton.setEnabled(False)
        self.deleteButton.clicked.connect(self._handleDeleteButton)
        buttonBar.addWidget(self.deleteButton)
        
        self.tableWidget = QtGui.QTableWidget()
        self.tableWidget.setItemDelegateForColumn(self._getColumnIndex("domain"), DomainItemDelegate())
        self.tableWidget.setColumnCount(len(self.columns))
        self.tableWidget.verticalHeader().hide()
        self.tableWidget.setSortingEnabled(True)
        self.tableWidget.horizontalHeader().setResizeMode(QtGui.QHeaderView.ResizeToContents)
        self.tableWidget.itemChanged.connect(self._handleItemChanged)
        self.tableWidget.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.tableWidget.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.tableWidget.itemSelectionChanged.connect(self._handleSelectionChanged)
        self.layout().addWidget(self.tableWidget)
        
        self.recheckButton = QtGui.QPushButton(self.tr("Force recheck of all files"))
        self.recheckButton.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        self.recheckButton.clicked.connect(self._handleRecheckButton)
        self.scanIntervalBox = QtGui.QSpinBox()
        self.scanIntervalBox.setMinimum(0)
        self.scanIntervalBox.setMaximum(24*3600)
        self.scanIntervalLabel = QtGui.QLabel()
        self.scanIntervalText = self.tr("Rescan filesystem every {} seconds (set to 0 to disable scans).")
        self.scanDisabledText = self.tr("No periodic rescans.")
        self.scanIntervalBox.valueChanged[int].connect(self._handleIntervalChanged)
        self.scanIntervalBox.setValue(config.options.filesystem.scan_interval)
            
        intervalLayout = QtGui.QHBoxLayout()
        intervalLayout.addWidget(self.scanIntervalBox)
        intervalLayout.addWidget(self.scanIntervalLabel)
        
        layout.addLayout(intervalLayout)
        layout.addWidget(self.recheckButton)
        layout.addStretch()
        
        self._loadSources()
        self._checkUndoRedoButtons()
        stack.indexChanged.connect(self._checkUndoRedoButtons)
        stack.undoTextChanged.connect(self._checkUndoRedoButtons)
        stack.redoTextChanged.connect(self._checkUndoRedoButtons)
        application.dispatcher.connect(self._handleDispatcher)
        
    def _loadSources(self):
        """Load sources information from filesystem.sources."""
        self.tableWidget.itemChanged.disconnect(self._handleItemChanged)
        self._sources = list(filesystem.sources)
        self.tableWidget.clear()
        self.tableWidget.setHorizontalHeaderLabels([column[1] for column in self.columns])
        self.tableWidget.setRowCount(len(self._sources))
        
        for row, source in enumerate(self._sources):
            column = self._getColumnIndex("name")
            item = QtGui.QTableWidgetItem(source.name)
            item.setFlags(Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tableWidget.setItem(row, column, item)
            
            column = self._getColumnIndex("path")
            item = QtGui.QTableWidgetItem(source.path)
            item.setFlags(Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tableWidget.setItem(row, column, item)
            
            column = self._getColumnIndex("domain")
            item = QtGui.QTableWidgetItem(source.domain.name if source.domain is not None else '')
            item.setFlags(Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tableWidget.setItem(row, column, item)
            
            column = self._getColumnIndex("enable")
            item = QtGui.QTableWidgetItem(source.enabled)
            item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setCheckState(Qt.Checked if source.enabled else Qt.Unchecked)
            self.tableWidget.setItem(row, column, item)
            
        self.tableWidget.resizeColumnsToContents()
        self.tableWidget.itemChanged.connect(self._handleItemChanged)
        
    def _handleDispatcher(self, event):
        if isinstance(event, filesystem.SourceChangeEvent):
            self._loadSources()
            
    def _handleSelectionChanged(self):
        rows = self.tableWidget.selectionModel().selectedRows()
        self.deleteButton.setEnabled(len(rows) == 1)
        
    def _handleAddButton(self):
        """Create a new domain (querying the user for its name)."""
        dialog = SourceDialog(self)
        dialog.exec_()
        # Table will be reloaded via the dispatcher event
            
    def _handleDeleteButton(self):
        """Delete the selected source (not from disk, only from configuration)."""
        rows = self.tableWidget.selectionModel().selectedRows()
        if len(rows) == 1:
            source = self._sources[rows[0].row()]
            filesystem.deleteSource(source)
    
    def _handleItemChanged(self, item):
        """Change a domain's name after the user edited it."""
        source = self._sources[item.row()]
        if item.column() == self._getColumnIndex("name"):
            oldName = source.name
            newName = item.text().strip()
            if oldName != newName:
                if _checkSourceName(self, newName, source):
                    filesystem.changeSource(source, name=newName)
                else: item.setText(oldName) # reset
        elif item.column() == self._getColumnIndex("path"):
            oldPath = source.path
            newPath = item.text()
            if oldPath != newPath:
                if _checkSourcePath(self, newPath, source):
                    filesystem.changeSource(source, path=newPath)
                else: item.setText(oldPath) # reset
        elif item.column() == self._getColumnIndex("enable"):
            filesystem.changeSource(source, enabled=item.checkState() == Qt.Checked)
                
    def _checkUndoRedoButtons(self):
        """Enable or disable the undo and redo buttons depending on stack state."""
        self.undoButton.setEnabled(stack.canUndo())
        self.undoButton.setToolTip(self.tr("Undo: {}").format(stack.undoText()))
        self.redoButton.setEnabled(stack.canRedo())
        self.redoButton.setToolTip(self.tr("Redo: {}").format(stack.redoText()))
           
    def _handleRecheckButton(self):
        if filesystem.enabled:
            QtCore.QMetaObject.invokeMethod(filesystem.synchronizer,
                                            "recheck", Qt.QueuedConnection,
                                            QtCore.Q_ARG("QString", ""))
    
    def _handleIntervalChanged(self, val):
        if val == 0:
            self.scanIntervalLabel.setText(self.scanDisabledText)
        else:
            self.scanIntervalLabel.setText(self.scanIntervalText.format(val))
        config.options.filesystem.scan_interval = val
        return #TODO
        if filesystem.enabled:
            timer = filesystem.synchronizer.timer
            timer.stop()
            if val != 0:
                timer.setInterval(val*1000)
                timer.start()

    @staticmethod
    def _getColumnIndex(columnKey):
        """Return the index of the column with the given key (i.e. the first part of the corresponding tuple
        in FilesystemSettings.columns."""
        for i in range(len(FilesystemSettings.columns)):
            if FilesystemSettings.columns[i][0] == columnKey:
                return i
        raise ValueError("Invalid key {}".format(columnKey))


class DomainItemDelegate(QtGui.QStyledItemDelegate):
    def createEditor(self, parent, option, index): 
        from .. import widgets
        return widgets.DomainBox(parent=parent)
        
    def setEditorData(self, editor, index):
        domain = filesystem.sources[index.row()].domain
        editor.setCurrentDomain(domain)
        
    def setModelData(self, editor, model, index):
        domain = editor.currentDomain()
        source = filesystem.sources[index.row()]
        filesystem.changeSource(source, domain=domain)


class SourceDialog(QtGui.QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Add source"))
        layout = QtGui.QVBoxLayout(self)
        formLayout = QtGui.QFormLayout()
        layout.addLayout(formLayout, 1)
        self.nameLineEdit = QtGui.QLineEdit()
        formLayout.addRow(self.tr("Name:"), self.nameLineEdit)
        self.pathLineEdit = QtGui.QLineEdit()
        formLayout.addRow(self.tr("Path:"), self.pathLineEdit)
        from .. import widgets
        self.domainChooser =  widgets.DomainBox()
        formLayout.addRow(self.tr("Domain:"), self.domainChooser)
        self.enableBox = QtGui.QCheckBox()
        formLayout.addRow(self.tr("Enabled:"), self.enableBox)
        
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        layout.addWidget(buttonBox)
      
    def accept(self):
        name = self.nameLineEdit.text()
        if not _checkSourceName(self, name):
            return
        path = self.pathLineEdit.text()
        if not _checkSourcePath(self, path):
            return
        domain = self.domainChooser.currentDomain()
        enabled = self.enableBox.isChecked()
        filesystem.addSource(name=name, path=path, domain=domain, enabled=enabled)
        super().accept()
        
            
def _checkSourceName(parent, name, source=None):
    if not filesystem.isValidSourceName(name):
        QtGui.QMessageBox.warning(parent, translate("Filesystem", "Cannot change source"),
                    translate("Filesystem", "'{}' is not a valid source name.").format(name))
        return False
    
    for s in filesystem.sources:
        if s != source and s.name == name:
            QtGui.QMessageBox.warning(parent, translate("Filesystem", "Cannot change source"),
                   translate("Filesystem", "A source named '{}' already exists.").format(name))
            return False
    return True


def _checkSourcePath(parent, path, source=None):
    if not os.path.exists(path):
        QtGui.QMessageBox.warning(parent, translate("Filesystem", "Cannot change source"),
                    translate("Filesystem", "The path '{}' does not exist.").format(path))
        return False
    if any(s.contains(path) for s in filesystem.sources if s != source):
        QtGui.QMessageBox.warning(parent, translate("Filesystem", "Cannot change source"),
                translate("Filesystem", "The path '{}' is contained in an existing source.").format(path))
        return False
    return True
