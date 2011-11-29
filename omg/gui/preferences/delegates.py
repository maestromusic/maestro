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

from ... import utils, tags

translate = QtCore.QCoreApplication.translate

delegateClasses = [] #TODO: not needed
delegateConfigs = []


class DataPiece:
    def __init__(self,data,title=None):
        if isinstance(data,tags.Tag):
            self.tag = data
            self.data = None
        else:
            self.tag = None
            self.data = data
            self._title = title
        self.data = data
        
    def getTitle(self):
        if self.tag is not None:
            return self.tag.translated()
        else: return self._title
        
    title = property(getTitle)
    
    def __eq__(self,other):
        return self.data == other.data
    
    def __ne__(self,other):
        return self.data != other.data
        

def availableDataPieces():
    result = [DataPiece(tag) for tag in tags.tagList if tag != tags.TITLE]
    result.extend([
            DataPiece("length",translate("Delegates","Length")),
            DataPiece("filecount",translate("Delegates","Number of files")),
            #DataPiece("bpm",translate("Delegates","BPM")),
            DataPiece("filetype",translate("Delegates","Filetype"))
        ])
    return result


class DelegateOption:
    def __init__(self,id,title,type,default):
        self.id = id
        self.title = title
        self.type = type
        self.value = default # load from storage
        self.active = True # load from storage
        self.typeOptions = None #TODO support max/mins for integer values etc
        
        
class DelegateConfig:
    def __init__(self,title,theClass,values=None,builtin=False):
        self.title = title
        self.theClass = theClass
        self.options = theClass.options.copy()
        if values is not None:
            for option in self.options:
                option.value = values[option.id]
        self.leftData,self.rightData = theClass.getDefaultDataPieces()
        self.builtin = builtin
        
    def copy(self):
        #TODO
        pass
    
    def hasDataPiece(self,piece):
        return piece in self.leftColumn or piece in self.rightColumn
    
    def getData(self,left):
        return self.leftData if left else self.rightData
    
    def resetToDefaults(self):
        self.options = theClass.options.copy()
        
    def __hash__(self):
        return hash(self.title)
        
        
def getConfig(title,theClass=None):
    for config in delegateConfigs:
        if config.title == title:
            if theClass is not None and config.theClass != theClass:
                raise ValueError("Delegate configuration with title '{}' cannot be used for {}"
                                 .format(config.title,theClass.__name__))
            return config
    raise ValueError("There is no delegate configuration with title '{}'".format(title))
        
        
def addDelegateConfig(config):
    insertDelegateConfig(len(delegateConfigs),config)
    
    
def insertDelegateConfig(pos,config):
    delegateConfigs.insert(pos,config)
    # Update the dialog if it is visible
    if DelegatesPanel._instance() is not None:
        DelegatesPanel._instance()._populateDelegateBox


def removeDelegateConfig(title):
    for i,config in enumerate(delegateConfigs):
        if config.title == title:
            del delegateConfigs[i]
            # Update the dialog if it is visible
            if DelegatesPanel._instance() is not None:
                DelegatesPanel._instance()._populateDelegateBox
            return


class DelegatesPanel(QtGui.QWidget):
    # weakref to the only existing instance. Initialize with a weakref pointing to nothing
    _instance = weakref.ref(set())
    
    def __init__(self,dialog,parent = None):
        super().__init__(parent)
        DelegatesPanel._instance = weakref.ref(self)
        self.setLayout(QtGui.QVBoxLayout())
        self.panels = {}
        
        self.topLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(self.topLayout)
        self.topLayout.addWidget(QtGui.QLabel(self.tr("Choose a delegate configuration: ")))
        
        self.delegateBox = QtGui.QComboBox()
        self.delegateBox.currentIndexChanged.connect(
                                        # get the config using the current item's text
                                        lambda i: self.showPanel(getConfig(self.delegateBox.itemText(i))))
        self.topLayout.addWidget(self.delegateBox)
        self.topLayout.addStretch(1)
        
        self.stackedWidget = QtGui.QStackedWidget()
        self.layout().addWidget(self.stackedWidget)
        
        bottomLayout = QtGui.QHBoxLayout()
        bottomLayout.addStretch(1)
        closeButton = QtGui.QPushButton(self.tr("Close"))
        closeButton.clicked.connect(dialog.close)
        bottomLayout.addWidget(closeButton)
        self.layout().addLayout(bottomLayout)
        
        self._populateDelegateBox()
        self.showPanel(delegateConfigs[0])
        
    def _populateDelegateBox(self):
        self.delegateBox.clear()
        for delegateConfig in delegateConfigs:
            self.delegateBox.addItem(delegateConfig.title)
    
    def showPanel(self,config):
        if config not in self.panels:
            panel = DelegateOptionsPanel(self,config)
            self.stackedWidget.addWidget(panel)
            self.panels[config] = panel
        self.stackedWidget.setCurrentWidget(self.panels[config])
            

class DelegateOptionsPanel(QtGui.QScrollArea):
    def __init__(self,parent,config):
        super().__init__(parent)
        self.config = config
        
        innerWidget = QtGui.QWidget()
        innerWidget.setLayout(QtGui.QVBoxLayout())
        innerWidget.layout().setSizeConstraint(QtGui.QLayout.SetFixedSize)
        self.setWidget(innerWidget)
        
        self.datapieceEditor = DataPieceEditor(self)
        innerWidget.layout().addWidget(self.datapieceEditor)
        
        frame = QtGui.QFrame()
        frame.setFrameStyle(QtGui.QFrame.Sunken | QtGui.QFrame.HLine)
        innerWidget.layout().addWidget(frame)
        
        grid = QtGui.QGridLayout()
        grid.setContentsMargins(0,0,0,0)
        innerWidget.layout().addLayout(grid)
        
        row = 0
        for id,option in config.theClass.options.items():
            grid.addWidget(QtGui.QLabel(option.title),row,1)
            editor = createEditor(option.type,option.value,option.typeOptions)
            editor.valueChanged.connect(functools.partial(self._handleValueChanged,config,option,editor))
            grid.addWidget(editor,row,0,Qt.AlignRight)
            row += 1
        grid.setRowStretch(row,1)
        grid.setColumnStretch(1,1)
        
        
    def _handleValueChanged(self,config,option,editor):
        if editor.value != option.value:
            option.value = editor.value
            self._updateDelegates(config)
    
    def addDataPiece(self,dataPiece,left):
        pass
    
    def setDataPieces(self,left,right):
        pass
    
    def _updateDelegates(self,config):
        from .. import delegates
        if config.theClass in delegates.AbstractDelegate._instances:
            for instance in delegates.AbstractDelegate._instances[config.theClass]:
                instance.view.scheduleDelayedItemsLayout()
    
    
class DataPieceEditor(QtGui.QWidget):
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
            
    def _fillAddDataBox(self):
        self.addDataBox.clear()
        self.addDataBox.addItem(
                        self.tr("Add to left column...") if self.left else self.tr("Add to right column..."))
        separatorInserted = False
        for data in availableDataPieces():
            if data.tag is not None:
                if data.tag.icon is not None:
                    self.addDataBox.addItem(data.tag.icon,data.title,data)
                else: self.addDataBox.addItem(data.title,data)
            else:
                if not separatorInserted:
                    self.addDataBox.insertSeparator(self.addDataBox.count())
                    separatorInserted = True
                self.addDataBox.addItem(data.title,data)
    
    def _updateList(self):
        self.listWidget.clear()
        for dataPiece in self.panel.config.getData(self.left):
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
            item = QtGui.QListWidgetItem(dataPiece.title)
            if dataPiece.tag is not None and dataPiece.tag.icon is not None:
                item.setIcon(dataPiece.tag.icon)
            item.setData(Qt.UserRole,dataPiece)
            self.listWidget.addItem(item)
        self.addDataBox.setCurrentIndex(0)
        
    def _handleDispatcher(self,event):
        # TODO : call _fillAddDataBox on TagTypeChangeEvents
        pass


def createEditor(type,value,options=None):
    return {
        "string": StringEditor,
        "bool": BoolEditor,
        "int": IntEditor
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
    