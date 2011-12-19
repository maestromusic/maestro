# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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

import weakref, functools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ... import utils, tags, modify
from ..delegates import configuration


class DelegatesPanel(QtGui.QWidget):
    def __init__(self,dialog,parent = None):
        super().__init__(parent)
        self.setLayout(QtGui.QVBoxLayout())
        self.panels = {}
        
        self.topLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(self.topLayout)
        self.topLayout.addWidget(QtGui.QLabel(self.tr("Choose a delegate configuration: ")))
        
        self.delegateBox = QtGui.QComboBox()
        self.delegateBox.currentIndexChanged.connect(
                    # get the config having the current item's text as title
                    lambda i: self.showPanel(configuration.getConfiguration(self.delegateBox.itemText(i))))
        self.topLayout.addWidget(self.delegateBox)
        self.topLayout.addStretch(1)
        
        self.stackedWidget = QtGui.QStackedWidget()
        self.layout().addWidget(self.stackedWidget)
        
        bottomLayout = QtGui.QHBoxLayout()
        resetButton = QtGui.QPushButton(self.tr("Reset this configuration"))
        resetButton.clicked.connect(self._handleResetButton)
        bottomLayout.addWidget(resetButton)
        bottomLayout.addStretch(1)
        closeButton = QtGui.QPushButton(self.tr("Close"))
        closeButton.clicked.connect(dialog.close)
        bottomLayout.addWidget(closeButton)
        self.layout().addLayout(bottomLayout)
        
        self._populateDelegateBox()
        self.showPanel(configuration.getConfiguration(self.delegateBox.itemText(0)))
        configuration.dispatcher.changes.connect(self._handleDispatcher)
        
    def _handleDispatcher(self,event):
        if event.type != modify.CHANGED:
            # Only events of type ADDED or REMOVED change the DelegateBox
            self._populateDelegateBox()
        
    def _populateDelegateBox(self):
        self.delegateBox.clear()
        for config in configuration.getConfigurations():
            self.delegateBox.addItem(config.title)
    
    def showPanel(self,config):
        if config not in self.panels:
            panel = DelegateOptionsPanel(self,config)
            self.stackedWidget.addWidget(panel)
            self.panels[config] = panel
        self.stackedWidget.setCurrentWidget(self.panels[config])
        self._currentConfig = config
            
    def _handleResetButton(self):
        self._currentConfig.resetToDefaults()
        
        
class DelegateOptionsPanel(QtGui.QScrollArea):
    def __init__(self,parent,config):
        super().__init__(parent)
        self.config = config
        
        innerWidget = QtGui.QWidget()
        innerWidget.setLayout(QtGui.QVBoxLayout())
        innerWidget.layout().setSizeConstraint(QtGui.QLayout.SetFixedSize)
        self.setWidget(innerWidget)
        
        self.datapieceEditor = DataPiecesEditor(self)
        innerWidget.layout().addWidget(self.datapieceEditor)
        
        frame = QtGui.QFrame()
        frame.setFrameStyle(QtGui.QFrame.Sunken | QtGui.QFrame.HLine)
        innerWidget.layout().addWidget(frame)
        
        grid = QtGui.QGridLayout()
        grid.setContentsMargins(0,0,0,0)
        innerWidget.layout().addLayout(grid)
        
        row = 0
        self._editors = {}
        for id,option in config.options.items():
            grid.addWidget(QtGui.QLabel(option.title),row,1)
            editor = createEditor(option.type,option.value,option.typeOptions)
            editor.valueChanged.connect(functools.partial(self._handleValueChanged,option,editor))
            self._editors[id] = editor
            grid.addWidget(editor,row,0,Qt.AlignRight)
            row += 1
        grid.setRowStretch(row,1)
        grid.setColumnStretch(1,1)
        
        configuration.dispatcher.changes.connect(self._handleConfigurationDispatcher)
        
    def _handleValueChanged(self,option,editor):
        self.config.setOption(option,editor.value)
    
    def _handleConfigurationDispatcher(self,event):
        if event.type == configuration.CHANGED and event.config == self.config:
            for id,option in self.config.options.items():
                if option.value != self._editors[id].value:
                    print("{} {}".format(option.value,self._editors[id].value))
                    self._editors[id].value = option.value
        
    
class DataPiecesEditor(QtGui.QWidget):
    def __init__(self,panel):
        super().__init__()
        self.setLayout(QtGui.QHBoxLayout())
        
        self.leftEditor = DataColumnEditor(panel,True,)
        self.rightEditor = DataColumnEditor(panel,False)
        
        self.layout().addWidget(self.leftEditor)
        self.layout().addWidget(self.rightEditor)
            
    
class DataColumnEditor(QtGui.QWidget):
    def __init__(self,panel,left):
        super().__init__()
        self.panel = panel
        self.left = left
        grid = QtGui.QGridLayout()
        grid.setContentsMargins(0,0,0,0)
        self.setLayout(grid)
        
        mainColumn = 0 if left else 1
        
        self.addDataBox = QtGui.QComboBox()
        self._fillAddDataBox()
        self.addDataBox.currentIndexChanged.connect(self._handleAddData)
        grid.addWidget(self.addDataBox,0,mainColumn)
        
        removeDataButton = QtGui.QPushButton()
        removeDataButton.setIcon(utils.getIcon('delete.png'))
        removeDataButton.clicked.connect(self._handleRemoveData)
        grid.addWidget(removeDataButton,0,mainColumn+1)
        
        self.listWidget = QtGui.QListWidget()
        # Effectively this sets the minimum size of listWidget. Note that QListWidgets have a fixed sizeHint
        # by default, but the default is too large for our purposes here. So we decrease it.
        self.listWidget.sizeHint = lambda: QtCore.QSize(150,140)
        self._updateList()
        grid.addWidget(self.listWidget,1,mainColumn,2,2)
        
        upButton = QtGui.QPushButton()
        upButton.setIcon(utils.getIcon('go-up.png'))
        downButton = QtGui.QPushButton()
        downButton.setIcon(utils.getIcon('go-down.png'))
        
        if left:
            grid.addWidget(upButton,1,2)
            grid.addWidget(downButton,2,2)
        else:
            grid.addWidget(upButton,1,0)
            grid.addWidget(downButton,2,0)
            
        configuration.dispatcher.changes.connect(self._handleConfigurationDispatcher)
            
    def _fillAddDataBox(self):
        self.addDataBox.clear()
        self.addDataBox.addItem(
                        self.tr("Add to left column...") if self.left else self.tr("Add to right column..."))
        separatorInserted = False
        for data in configuration.availableDataPieces():
            if data.tag is not None:
                if data.tag.icon is not None:
                    self.addDataBox.addItem(data.tag.icon,data.title,data)
                else: self.addDataBox.addItem(data.title,data)
            else:
                if not separatorInserted:
                    self.addDataBox.insertSeparator(self.addDataBox.count())
                    separatorInserted = True
                self.addDataBox.addItem(data.title,data)
    
    def getDataPieces(self):
        return [self.listWidget.item(row).data(Qt.UserRole) for row in range(self.listWidget.count())]
    
    def _updateList(self):
        self.listWidget.clear()
        for dataPiece in self.panel.config.getDataPieces(self.left):
            item = QtGui.QListWidgetItem(dataPiece.title)
            if dataPiece.tag is not None and dataPiece.tag.icon is not None:
                item.setIcon(dataPiece.tag.icon)
            item.setData(Qt.UserRole,dataPiece)
            self.listWidget.addItem(item)
    
    def _handleAddData(self,index):
        if index == 0:
            return # 'Add to left column...' was selected
        dataPiece = self.addDataBox.itemData(index)
        if not self.panel.config.hasDataPiece(dataPiece):
            self.panel.config.addDataPiece(self.left,dataPiece)
#            item = QtGui.QListWidgetItem(dataPiece.title)
#            if dataPiece.tag is not None and dataPiece.tag.icon is not None:
#                item.setIcon(dataPiece.tag.icon)
#            item.setData(Qt.UserRole,dataPiece)
#            self.listWidget.addItem(item)
#            self.panel.config.setDataPieces(self.left,self.getDataPieces())
        self.addDataBox.setCurrentIndex(0)
    
    def _handleRemoveData(self):
        allItems = [self.listWidget.item(row) for row in range(self.listWidget.count())]
        remainingData = [item.data(Qt.UserRole) for item in allItems if not item.isSelected()]
        self.panel.config.setDataPieces(self.left,remainingData)
        
    def _handleConfigurationDispatcher(self,event):
        if event.type == configuration.CHANGED and event.config == self.panel.config:
            self._updateList()
        
    
    

def createEditor(type,value,options=None):
    return {
        "string": StringEditor,
        "bool": BoolEditor,
        "int": IntEditor,
        "tag": TagEditor,
        "datapiece": DataPieceEditor
        #TODO: color, combobox
    }[type](value,options)
    
    
class StringEditor(QtGui.QLineEdit):
    def __init__(self,value,options):
        super().__init__(value)
        
    value = property(QtGui.QLineEdit.text,QtGui.QLineEdit.setText)
    valueChanged = QtGui.QLineEdit.editingFinished
    
    
class BoolEditor(QtGui.QCheckBox):
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
    valueChanged = QtCore.pyqtSignal()
    
    def __init__(self,value,options):
        super().__init__()
        self._fillBox(value)
        self.currentIndexChanged.connect(self.valueChanged)
        modify.dispatcher.changes.connect(self._handleTagTypeChanged)
            
    def _fillBox(self,defaultTag):
        self.clear()
        self.addItem(self.tr("None"),None)
        self.insertSeparator(1)
        for tag in tags.tagList:
            if tag.icon is not None:
                self.addItem(tag.icon,tag.translated(),tag)
            else: self.addItem(tag.translated(),tag)
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
        if isinstance(event, modify.events.TagTypeChangedEvent):
            self._fillBox(self.getValue())
            

class DataPieceEditor(QtGui.QComboBox):
    valueChanged = QtCore.pyqtSignal()
    
    def __init__(self,value,options):
        super().__init__()
        self._fillBox(value)
        self.currentIndexChanged.connect(self.valueChanged)
        modify.dispatcher.changes.connect(self._handleTagTypeChanged)
            
    def _fillBox(self,default):
        self.clear()
        self.addItem(self.tr("None"),None)
        self.insertSeparator(1)
        for dataPiece in configuration.availableDataPieces():
            if dataPiece.tag is not None and dataPiece.tag.icon is not None:
                self.addItem(dataPiece.tag.icon,dataPiece.title,dataPiece)
            else: self.addItem(dataPiece.title,dataPiece)
            if dataPiece == default:
                self.setCurrentIndex(self.count()-1)
        # Insert a separator after all tags, before stuff like length
        self.insertSeparator(
                    len([data for data in configuration.availableDataPieces() if data.tag is not None])+2)
                
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
        if isinstance(event, modify.events.TagTypeChangedEvent):
            self._fillBox(self.getValue())
            