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

from .. import config, tags, utils
from . import dialogs

# Layers that can be selected in BrowserDialog's comboboxes. Each item in the list is a list containing for each layer a list of the tagnames in that layer.
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
    def __init__(self,browser):
        dialogs.FancyTabbedPopup.__init__(self,browser.window())
        self.browser = browser
        self.viewConfigurations = []
                
        self.flagTab = QtGui.QWidget()
        self.tabWidget.addTab(self.flagTab,self.tr("Flags"))
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
        
        self.adjustSize()
        
    def close(self):
        self.browser._handleDialogClosed()
        dialogs.FancyTabbedPopup.close(self)


class ViewConfigurationDialog(QtGui.QDialog):
    """The BrowserDialog allows you to configure the views and their layers of a browser."""
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
        """Set the currently selected layers to <layers>. If this is not contained in browserdialog.selectableLayers, nothing is selected."""
        try:
            self.comboBox.setCurrentIndex(selectableLayers.index(layers))
        except ValueError:
            self.comboBox.setCurrentIndex(-1)
            
    def getLayers(self):
        """Return the currently selected layers."""
        if self.comboBox.currentIndex() == -1:
            return None
        else: return self.comboBox.itemData(self.comboBox.currentIndex())
