# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

from . import profiles as profilesgui
from .. import dialogs, delegates
from ... import application, constants, utils
from ...core import tags

        
class DelegateOptionsPanel(QtGui.QWidget):
    """This panel allows the user to edit a single delegate configuration. It consists of three parts:
    Two DataPiecesEditors to edit the datapieces displayed in the left and those displayed in the right
    column and a list of widgets (checkboxes, comboboxes etc.) to edit the configuration's options.
    """
    def __init__(self, profile, parent):
        super().__init__(parent)
        self.profile = profile
        
        layout = QtGui.QVBoxLayout(self)
        
        layout.addWidget(QtGui.QLabel("Decide which tags should be displayed on the left and right side:"))
        dataLayout = QtGui.QHBoxLayout()
        layout.addLayout(dataLayout)
        dataLayout.addWidget(DataPiecesEditor(self,True,))
        dataLayout.addWidget(DataPiecesEditor(self,False))
        
        layout.addSpacing(20)
        
        optionsBox = QtGui.QGroupBox(self.tr("Options"))
        layout.addWidget(optionsBox)
        grid = QtGui.QGridLayout(optionsBox)
        grid.setContentsMargins(0,0,0,0)
        
        # Create an editor for each option
        row = 0
        self._editors = {}
        for option in profile.type.options.values():
            grid.addWidget(QtGui.QLabel(option.title),row,1)
            editor = createEditor(option.type,profile.options[option.name],option.typeOptions)
            editor.valueChanged.connect(functools.partial(self._handleValueChanged,option,editor))
            self._editors[option.name] = editor
            grid.addWidget(editor,row,0,Qt.AlignRight)
            row += 1
        grid.setRowStretch(row,1)
        grid.setColumnStretch(1,1)
        
        layout.addStretch(1)
        delegates.profiles.category.profileChanged.connect(self._handleProfileChanged)
        
    def _handleValueChanged(self,option,editor):
        """Handle a value change in the editor for the given *option*."""
        self.profile.setOption(option,editor.value)
    
    def _handleProfileChanged(self,profile):
        """Handle an event from the delegate configuration dispatcher."""
        if profile == self.profile:
            for name,value in self.profile.options.items():
                if value != self._editors[name].value:
                    self._editors[name].value = value
               

class DataPiecesModel(QtCore.QAbstractListModel):
    """Depending on *left*, this model manages the datapieces in the left or right column of *profile*."""
    def __init__(self,profile,left):
        super().__init__()
        self.profile = profile
        self.left = left
        delegates.profiles.category.profileChanged.connect(self._handleProfileChanged)
    
    def setProfile(self,profile):
        """Set the profile whose datapieces are managed by this model."""
        self.profile = profile
        self.reset()
    
    def rowCount(self,parent):
        if not parent.isValid():
            return len(self.profile.getDataPieces(self.left))
        
    def data(self,index,role):
        dataPiece = self.profile.getDataPieces(self.left)[index.row()]
        if role == Qt.DisplayRole:
            return dataPiece.title
        elif role == Qt.DecorationRole:
            if dataPiece.tag is not None:
                return dataPiece.tag.icon # may be None
        elif role == Qt.EditRole:
            return dataPiece
    
    def flags(self,index):
        return (Qt.ItemIsSelectable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled | Qt.ItemIsEnabled)

    def dropMimeData(self,mimeData,action,row,column,parent):
        if isinstance(mimeData,MimeData):
            if row == -1:
                if parent.isValid():
                    # The user dropped the items on an existing item -> insert below
                    row = parent.row() + 1
                else: row = self.rowCount(QtCore.QModelIndex())
            # Insert rows and return True so that Qt will call removeRows in the source view to conclude
            # the move action.
            self.beginInsertRows(QtCore.QModelIndex(),row,row+len(mimeData.dataPieces)-1)
            self.profile.insertDataPieces(self.left,row,mimeData.dataPieces,emitEvent=False)
            self.endInsertRows()
            return True
        return False
    
    def removeRows(self,row,count,parent=None):
        # This is called by Qt when a row was dragged to another place.
        # There is no need to use beginRemoveRows/endRemoveRows as the model is reset via the dispatcher.
        self.profile.removeDataPieces(self.left,row,count)
        return True
        
    def supportedDropActions(self):
        return Qt.MoveAction
    
    def supportedDragActions(self):
        return Qt.MoveAction
    
    def mimeTypes(self):
        return ["application/x-omg-datapieces"]
    
    def mimeData(self,indexList):
        return MimeData([self.data(index,Qt.EditRole) for index in indexList])
    
    def _handleProfileChanged(self,profile):
        """Handle profile changed events from the profile category."""
        if profile == self.profile:
            self.reset()
                
        
class MimeData(QtCore.QMimeData):
    """Special mimedata class for the drag&drop of datapieces."""
    def __init__(self,dataPieces):
        super().__init__()
        self.dataPieces = dataPieces
        
    def formats(self):
        return ["application/x-omg-datapieces"]
        
        
class DataPiecesEditor(QtGui.QWidget):
    """A widget to edit one column of datapieces (tags, filetype, length etc.)."""
    def __init__(self,panel,left):
        super().__init__()
        layout = QtGui.QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        self.panel = panel
        self.left = left
        
        mainColumn = 0 if left else 1
        
        topLayout = QtGui.QHBoxLayout()
        layout.addLayout(topLayout)
        
        self.addDataBox = QtGui.QComboBox()
        self._fillAddDataBox()
        self.addDataBox.currentIndexChanged.connect(self._handleAddData)
        topLayout.addWidget(self.addDataBox)
        
        removeDataButton = QtGui.QPushButton()
        removeDataButton.setIcon(utils.getIcon('remove.png'))
        removeDataButton.clicked.connect(self._handleRemoveData)
        topLayout.addWidget(removeDataButton)
        
        topLayout.addStretch()
        
        self.model = DataPiecesModel(panel.profile,left)
        self.listView = QtGui.QListView()
        self.listView.setModel(self.model)
        self.listView.setDragEnabled(True)
        self.listView.viewport().setAcceptDrops(True)
        self.listView.setDropIndicatorShown(True)
        self.listView.setDragDropOverwriteMode(False)
        # Effectively this sets the minimum size of listWidget. Note that QListWidgets have a fixed sizeHint
        # by default, but the default is too large for our purposes here. So we decrease it.
        self.listView.sizeHint = lambda: QtCore.QSize(150,120)
        layout.addWidget(self.listView)
            
    def _fillAddDataBox(self):
        """Fill the combobox with a list of all available datapieces."""
        self.addDataBox.clear()
        self.addDataBox.addItem(utils.getIcon('add.png'),
                        self.tr("Add to left column...") if self.left else self.tr("Add to right column..."))
        separatorInserted = False
        for data in delegates.profiles.availableDataPieces():
            if data.tag is not None:
                if data.tag.icon is not None:
                    self.addDataBox.addItem(data.tag.icon,data.title,data)
                else: self.addDataBox.addItem(data.title,data)
            else:
                if not separatorInserted:
                    self.addDataBox.insertSeparator(self.addDataBox.count())
                    separatorInserted = True
                self.addDataBox.addItem(data.title,data)
     
    def _handleAddData(self,index):
        """Add the datapiece with the given index in the combobox to the list if it is not already contained
        in this _or_ the other column."""
        if index == 0:
            return # 'Add to left column...' was selected
        dataPiece = self.addDataBox.itemData(index)
        if not self.panel.profile.hasDataPiece(dataPiece):
            self.panel.profile.addDataPiece(self.left,dataPiece)
        self.addDataBox.setCurrentIndex(0)

    def _handleRemoveData(self):
        """Handle a click on the remove button."""
        allData = self.panel.profile.getDataPieces(self.left)
        remainingData = [allData[i] for i in range(len(allData))
                            if not self.listView.selectionModel().isRowSelected(i,QtCore.QModelIndex())]
        self.panel.profile.setDataPieces(self.left,remainingData)
        
        
class ListWidget(QtGui.QListWidget):
    """Special list widget with the drag&drop handling necessary for DataPiecesEditor."""
    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.MoveAction)
    
    def dropEvent(self,event):
        if isinstance(event.source(),ListWidget):
            super().dropEvent(event)
        

def createEditor(type,value,options=None):
    """Create an editor for the given *type* (a checkbox for 'bool', a QLineEdit for 'string' and so on).
    Ínitialize it with *value*. *options* are passed to the editor's constructor and depend on the type."""
    return {
        "string": StringEditor,
        "bool": BoolEditor,
        "int": IntEditor,
        "tag": TagEditor,
        "datapiece": DataPieceEditor
        #TODO: color, combobox
    }[type](value,options)
    
    
# The next classes are used as editors for the different option types. They all must provide a property 
# value and a signal valueChanged.

class StringEditor(QtGui.QLineEdit):
    """Editor for options of type 'string'."""
    def __init__(self,value,options):
        super().__init__(value)
        
    value = property(QtGui.QLineEdit.text,QtGui.QLineEdit.setText)
    valueChanged = QtGui.QLineEdit.editingFinished
    
    
class BoolEditor(QtGui.QCheckBox):
    """Editor for options of type 'bool'."""
    def __init__(self,value,options):
        super().__init__()
        self.setCheckState(Qt.Checked if value else Qt.Unchecked)
        self.stateChanged.connect(self.valueChanged)
        
    def getValue(self):
        return self.checkState() == Qt.Checked
    
    def setValue(self,value):
        self.setCheckState(Qt.Checked if value else Qt.Unchecked)
    
    value = property(getValue,setValue)
    valueChanged = QtCore.pyqtSignal()
    

class IntEditor(QtGui.QSpinBox):
    """Editor for options of type 'int'."""
    def __init__(self,value,options):
        super().__init__()
        self.value = value
        if options is not None:
            if 'minimum' in options:
                self.setMinimum(options['minimum'])
            if 'maximum' in options:
                self.setMaximum(options['maximum'])
                
    value = property(QtGui.QSpinBox.value,QtGui.QSpinBox.setValue)
    # valueChanged is already contained in QSpinBox


class TagEditor(QtGui.QComboBox):
    """Editor for options of type 'tag'."""
    valueChanged = QtCore.pyqtSignal()
    
    def __init__(self,value,options):
        super().__init__()
        self._updateBox(value)
        self.currentIndexChanged.connect(self.valueChanged)
        application.dispatcher.connect(self._handleTagTypeChanged)
            
    def _updateBox(self,defaultTag):
        """Fill/update the list of tags."""
        self.clear()
        self.addItem(self.tr("None"),None)
        self.insertSeparator(1)
        for tag in tags.tagList:
            if tag.icon is not None:
                self.addItem(tag.icon,tag.title,tag)
            else: self.addItem(tag.title,tag)
            if tag == defaultTag:
                self.setCurrentIndex(self.count()-1)
                
    def getValue(self):
        return self.itemData(self.currentIndex(),Qt.UserRole)
    
    def setValue(self,value):
        for i in range(self.count()):
            if self.itemData(i,Qt.UserRole) == value:
                if i != self.currentIndex():
                    self.setCurrentIndex(i)
                    self.valueChanged.emit()
                return
            
    value = property(getValue,setValue)
    
    def _handleTagTypeChanged(self,event):
        """React upon tagTypeChanged-signals from the dispatcher."""
        if isinstance(event,tags.TagTypeChangedEvent):
            self._updateBox(self.getValue())
            

class DataPieceEditor(QtGui.QComboBox):
    """Editor for options of type 'datapiece'."""
    valueChanged = QtCore.pyqtSignal()
    
    def __init__(self,value,options):
        super().__init__()
        self._updateBox(value)
        self.currentIndexChanged.connect(self.valueChanged)
        application.dispatcher.connect(self._handleTagTypeChanged)
            
    def _updateBox(self,default):
        """Fill/update the list of datapieces."""
        self.clear()
        self.addItem(self.tr("None"),None)
        self.insertSeparator(1)
        for dataPiece in delegates.profiles.availableDataPieces():
            if dataPiece.tag is not None and dataPiece.tag.icon is not None:
                self.addItem(dataPiece.tag.icon,dataPiece.title,dataPiece)
            else: self.addItem(dataPiece.title,dataPiece)
            if dataPiece == default:
                self.setCurrentIndex(self.count()-1)
        # Insert a separator after all tags, before stuff like length
        self.insertSeparator(
                len([data for data in delegates.profiles.availableDataPieces() if data.tag is not None])+2)
                
    def getValue(self):
        return self.itemData(self.currentIndex(),Qt.UserRole)
    
    def setValue(self,value):
        for i in range(self.count()):
            if self.itemData(i,Qt.UserRole) == value:
                if i != self.currentIndex():
                    self.setCurrentIndex(i)
                    self.valueChanged.emit()
                return
            
    value = property(getValue,setValue)
    
    def _handleTagTypeChanged(self,event):
        """React upon tagTypeChanged-signals from the dispatcher."""
        if isinstance(event,tags.TagTypeChangedEvent):
            self._updateBox(self.getValue())
            
            
class ManageConfigurationsDialog(QtGui.QDialog):
    """Dialog to add, rename and delete delegate configurations."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Manage configurations"))
        layout = QtGui.QVBoxLayout(self)
        
        layout.addWidget(QtGui.QLabel(
                            self.tr("<i>Italic configurations</i> are built in and cannot be deleted.")))
        layout.addWidget(QtGui.QLabel(self.tr("Click on a name to change it.")))
        
        mainLayout = QtGui.QHBoxLayout()
        layout.addLayout(mainLayout)
        self.table = QtGui.QTableWidget()
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self._updateTable()
        self.table.itemSelectionChanged.connect(self._handleSelectionChanged)
        self.table.itemChanged.connect(self._handleItemChanged)
        mainLayout.addWidget(self.table)
        
        buttonLayout = QtGui.QVBoxLayout()
        mainLayout.addLayout(buttonLayout)
        
        self.addBox = QtGui.QComboBox()
        self.addBox.addItem(self.tr("Add configuration"))
        for type in configuration.getTypes():
            self.addBox.addItem(type.title,type)
        self.addBox.currentIndexChanged.connect(self._handleAddBox)
        buttonLayout.addWidget(self.addBox)
            
        self.resetButton = QtGui.QPushButton(self.tr("Reset to defaults"))
        self.resetButton.setEnabled(False)
        self.resetButton.clicked.connect(self._handleResetButton)
        buttonLayout.addWidget(self.resetButton)
        
        self.deleteButton = QtGui.QPushButton(self.tr("Delete"))
        self.deleteButton.setEnabled(False)
        self.deleteButton.clicked.connect(self._handleDeleteButton)
        buttonLayout.addWidget(self.deleteButton)
        
        buttonLayout.addStretch(1)
        
        closeButton = QtGui.QPushButton(self.tr("Close"))
        closeButton.clicked.connect(self.close)
        buttonLayout.addWidget(closeButton)
        closeButton.setFocus(Qt.PopupFocusReason)
        
    def _updateTable(self):
        """Fill/update the table of delegate configurations."""
        self.table.clear()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels([self.tr("Name"),self.tr("Type")])
        
        configs = configuration.getConfigurations()
        self.table.setRowCount(len(configs))
        
        for row,config in enumerate(configs):
            item = QtGui.QTableWidgetItem(config.title)
            if config.builtin:
                font = item.font()
                font.setItalic(True)
                item.setFont(font)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            else: item.setFlags(Qt.ItemIsEditable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(row,0,item)
            
            item = QtGui.QTableWidgetItem(config.type.title)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(row,1,item)
            
    def _handleAddBox(self,index):
        """Add a new delegate configuration for the type with the given index in addBox."""
        if index != 0:
            type = self.addBox.itemData(index)
            configuration.createDelegateConfiguration(type)
            self.addBox.setCurrentIndex(0)
            self._updateTable()
    
    def _selectedConfigs(self):
        """Return a list of currently selected configurations."""
        configs = configuration.getConfigurations()
        return [configs[rowIndex.row()] for rowIndex in self.table.selectionModel().selectedRows()]
    
    def _handleSelectionChanged(self):
        """Enable/disable buttons according to the selection: Built-in configurations must not be deleted."""
        self.resetButton.setEnabled(self.table.selectionModel().hasSelection())
        self.deleteButton.setEnabled(self.table.selectionModel().hasSelection()
                                     and all(not config.builtin for config in self._selectedConfigs()))
        
    def _handleDeleteButton(self):
        """Delete the selected configurations if the user confirms this."""
        if dialogs.question(
                    self.tr("Delete configurations"),
                    self.tr("Should I really delete %n configuration(s)?",'',len(self._selectedConfigs())),
                    parent=self):
            for config in self._selectedConfigs():
                configuration.removeDelegateConfiguration(config)
            self._updateTable()
    
    def _handleResetButton(self):
        """Reset the selected configurations if the user confirms this."""
        if dialogs.question(
                    self.tr("Reset configurations"),
                    self.tr("Should I really reset %n configuration(s)?",'',len(self._selectedConfigs())),
                    parent=self):
            for config in self._selectedConfigs():
                config.resetToDefaults()
                
    def _handleItemChanged(self,item):
        """React to changes to the item texts in the table: Rename the corresponding configuration."""
        if item.column() != 0:
            return
        config = configuration.getConfigurations()[item.row()]
        if config.title != item.text():
            if configuration.exists(item.text()):
                dialogs.warning("Invalid title","There is already a configuration with this title.",
                               parent=self)
                item.setText(config.title)
            else:
                config.setTitle(item.text())
                