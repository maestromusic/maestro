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

delegateClasses = []
delegateConfigs = []

        
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
        self.builtin = builtin
        
    def copy(self):
        #TODO
        pass
    
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
        self.setViewport(innerWidget)
        grid = QtGui.QGridLayout()
        innerWidget.setLayout(grid)
        
        row = 0
        for id,option in config.theClass.options.items():
            grid.addWidget(QtGui.QLabel(option.title),row,0)
            editor = createEditor(option.type,option.value,option.typeOptions)
            editor.valueChanged.connect(functools.partial(self._handleValueChanged,config,option,editor))
            grid.addWidget(editor,row,1,Qt.AlignRight)
            row += 1
        grid.setRowStretch(row,1)
        
    def _handleValueChanged(self,config,option,editor):
        if editor.value != option.value:
            option.value = editor.value
            from .. import delegates
            if config.theClass in delegates.AbstractDelegate._instances:
                for instance in delegates.AbstractDelegate._instances[config.theClass]:
                    instance.view.scheduleDelayedItemsLayout()
    
    
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
        