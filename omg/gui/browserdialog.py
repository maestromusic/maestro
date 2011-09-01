#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import config, tags, utils, database as db, flags
from . import dialogs

# Layers that can be selected in BrowserDialog's comboboxes. Each item in the list is a list containing for
# each layer a list of the tagnames in that layer.
selectableLayers = utils.mapRecursively(tags.get,[
     [['composer','artist','performer']],
     [['genre'],['composer','artist','performer']],
     [['composer','artist','performer'],['album']],
     [['genre'],['composer','artist','performer'],['album']],
     [['genre']],
     [['artist']],
     [['composer']],
     [['performer']],
     [['conductor']],
     [['album']]
])


class BrowserDialog(dialogs.FancyTabbedPopup):
    """Popup dialog that allows to configure the Browser."""
    def __init__(self,browser):
        dialogs.FancyTabbedPopup.__init__(self,browser.optionButton)
        self.resize(300,170)
        self.browser = browser
        self.viewConfigurations = []
                
        self.flagTab = QtGui.QWidget()
        self.flagTab.setLayout(QtGui.QVBoxLayout())
        self.tabWidget.addTab(self.flagTab,self.tr("Flags"))
        
        self.flagView = FlagView(browser.flags)
        self.flagView.selectionChanged.connect(self._handleSelectionChanged)
        self.flagTab.layout().addWidget(self.flagView)
        
        optionTab = QtGui.QWidget()
        optionLayout = QtGui.QVBoxLayout()
        optionTab.setLayout(optionLayout)
        self.tabWidget.addTab(optionTab,self.tr("Options"))
        
        instantSearchBox = QtGui.QCheckBox(self.tr("Instant search"))
        instantSearchBox.setChecked(self.browser.searchBox.getInstantSearch())
        instantSearchBox.clicked.connect(self.browser.searchBox.setInstantSearch)
        optionLayout.addWidget(instantSearchBox)
        
        hideInBrowserBox = QtGui.QCheckBox(self.tr("Show hidden values"))
        hideInBrowserBox.setChecked(self.browser.getShowHiddenValues())
        hideInBrowserBox.clicked.connect(self.browser.setShowHiddenValues)
        optionLayout.addWidget(hideInBrowserBox)
        
        viewConfigButton = QtGui.QPushButton(self.tr("Configure Views..."))
        viewConfigButton.clicked.connect(lambda: ViewConfigurationDialog(self.browser).exec_())
        viewConfigButton.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed,QtGui.QSizePolicy.Fixed))
        optionLayout.addWidget(viewConfigButton)
        
        optionLayout.addStretch(1)
        
    def close(self):
        self.browser._handleDialogClosed()
        dialogs.FancyTabbedPopup.close(self)
        
    def _handleSelectionChanged(self):
        self.browser.setFlags(self.flagView.selectedFlagTypes)


class FlagView(QtGui.QTableWidget):
    selectionChanged = QtCore.pyqtSignal(list)
    
    def __init__(self,selectedFlagTypes,parent=None):
        QtGui.QTableWidget.__init__(self,parent)
        self.verticalHeader().hide()
        self.horizontalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(self.verticalHeader().fontMetrics().height()+2)
        self.itemChanged.connect(self._handleItemChanged)
        self.setShowGrid(False)
        
        self.selectedFlagTypes = selectedFlagTypes[:]
        self._loadFlags()
        
    def _loadFlags(self):
        self.clear()
        result = db.query("SELECT id,name FROM {}flag_names ORDER BY name".format(db.prefix))
        
        if result.size() > 5:
            self.setColumnCount(2)
            import math
            rowCount = math.ceil(result.size()/2)
            self.setRowCount(rowCount)
        else:
            self.setColumnCount(1)
            rowCount = result.size()
            self.setRowCount(rowCount)
    
        for row,sqlRow in enumerate(result):
            id,name = sqlRow
            flagType = flags.Flag(id,name)
            column = 1 if row >= rowCount else 0
            
            item = QtGui.QTableWidgetItem()
            item.setText(name)
            item.setData(Qt.UserRole,flagType)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if flagType in self.selectedFlagTypes else Qt.Unchecked)
            self.setItem(row % rowCount,column,item)
        
        self.resizeColumnsToContents()
    
    def selectFlagType(self,flagType):
        if flagType not in self.selectedFlagTypes: 
            self.selectedFlagTypes.append(flagType)
            item = self.findItem(flagType)
            if item is not None: # should always be true
                item.setCheckState(Qt.Checked)
            self.selectionChanged.emit(self.selectedFlagTypes)
    
    def unselectFlagType(self,flagType):
        if flagType in self.selectedFlagTypes:
            self.selectedFlagTypes.remove(flagType)
            item = self.findItem(flagType)
            if item is not None: # should always be true
                item.setCheckState(Qt.Unchecked)
            self.selectionChanged.emit(self.selectedFlagTypes)
                
    def _handleItemChanged(self,item):
        flagType = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            self.selectFlagType(flagType)
        elif item.checkState() == Qt.Unchecked:
            self.unselectFlagType(flagType)
        
    def findItem(self,flagType):
        for row in range(self.rowCount()):
            for column in range(self.columnCount()):
                item = self.item(row,column)
                if item is not None and item.data(Qt.UserRole) == flagType:
                    return item
        return None
        
        
class ViewConfigurationDialog(QtGui.QDialog):
    """The BrowserDialog allows you to configure the views of a browser and their layers."""
    def __init__(self,parent):
        """Initialize with the given parent, which must be the browser to configure."""
        QtGui.QDialog.__init__(self,parent)
        self.setWindowTitle(self.tr("Browser configuration"))
        self.browser = parent
        
        self.viewConfigurations = []
        
        # GUI
        layout = QtGui.QVBoxLayout()
        self.setLayout(layout)
        
        topLayout = QtGui.QHBoxLayout()
        topLayout.addWidget(QtGui.QLabel(self.tr("Number of views: ")))
        spinBox = QtGui.QSpinBox()
        spinBox.setRange(1,5)
        spinBox.setValue(len(self.browser.views))
        spinBox.valueChanged.connect(self._handleValueChanged)
        topLayout.addWidget(spinBox)
        topLayout.addStretch(1)
        
        layout.addLayout(topLayout)
        
        self.viewConfLayout = QtGui.QVBoxLayout()
        layout.addLayout(self.viewConfLayout)
        
        layout.addStretch(1)
        
        bottomLayout = QtGui.QHBoxLayout()
        layout.addLayout(bottomLayout)
        
        bottomLayout.addStretch(1)
        abortButton = QtGui.QPushButton(self.tr("Cancel"))
        abortButton.clicked.connect(self.close)
        bottomLayout.addWidget(abortButton)
        okButton = QtGui.QPushButton(self.tr("OK"))
        okButton.clicked.connect(self._handleOk)
        bottomLayout.addWidget(okButton)
        
        self._handleValueChanged(len(self.browser.views))
        for i in range(0,len(self.browser.views)):
            self.viewConfigurations[i].setLayers(self.browser.views[i].model().getLayers())
        
    def _handleValueChanged(self,value):
        if value < len(self.viewConfigurations):
            for viewConf in self.viewConfigurations[value:]:
                self.viewConfLayout.removeWidget(viewConf)
                viewConf.setParent(None)
            del self.viewConfigurations[value:]
            self.adjustSize()
        elif value > len(self.viewConfigurations):
            for i in range(len(self.viewConfigurations),value):
                newViewConfiguration = ViewConfiguration(self,i)
                self.viewConfigurations.append(newViewConfiguration)
                self.viewConfLayout.addWidget(newViewConfiguration)
                
    def _handleOk(self):
        self.browser.createViews([viewConf.getLayers() for viewConf in self.viewConfigurations])
        self.close()


class ViewConfiguration(QtGui.QWidget):
    """A row in BrowserDialog which allows to configure a single view."""
    def __init__(self,parent,index):
        """Initialize this ViewConfiguration with the given parent and the label "View <index+1>: "."""
        QtGui.QWidget.__init__(self,parent)
        
        # GUI
        layout = QtGui.QHBoxLayout()
        self.setLayout(layout)
        
        layout.addWidget(QtGui.QLabel(self.tr("View {}: ").format(index+1),self))
        self.comboBox = QtGui.QComboBox(self)
        for layers in selectableLayers:
            self.comboBox.addItem(str(utils.mapRecursively(str,layers)),layers)
        layout.addWidget(self.comboBox)
        
    def setLayers(self,layers):
        """Set the currently selected layers to <layers>. If this is not contained in
        browserdialog.selectableLayers, nothing is selected.
        """
        try:
            self.comboBox.setCurrentIndex(selectableLayers.index(layers))
        except ValueError:
            self.comboBox.setCurrentIndex(-1)
            
    def getLayers(self):
        """Return the currently selected layers."""
        if self.comboBox.currentIndex() == -1:
            return None
        else: return self.comboBox.itemData(self.comboBox.currentIndex())
