# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

from . import dialogs, delegates, search as searchgui
from .. import config, utils, database as db
from ..core import tags, flags
from ..models import browser as browsermodel
from ..search import criteria
from .delegates import browser as browserdelegate
from .misc import lineedits
from .preferences import profiles as profilesgui

MAX_SUB_BROWSERS = 5


# Layers that can be selected in BrowserDialog's comboboxes. Each item in the list is a list containing for
# each layer a list of the tagnames in that layer.
selectableLayers = utils.mapRecursively(functools.partial(tags.get, addDialogIfNew=True), [
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


class AbstractBrowserDialog(dialogs.FancyTabbedPopup):
    """Popup dialog that allows to configure the Browser."""
    def __init__(self, parent, browser):
        super().__init__(parent, 300, 200)
        self.browser = browser
        self.viewConfigurations = []
                
        filterTab = QtGui.QWidget()
        filterTab.setLayout(QtGui.QVBoxLayout())
        self.tabWidget.addTab(filterTab, self.tr("Filter"))
        
        filterTab.layout().addWidget(QtGui.QLabel(self.tr("Flags:")))
        flagList = self.browser.flagCriterion.flags if self.browser.flagCriterion is not None else []
        
        self.flagView = searchgui.FlagView(flagList)
        self.flagView.selectionChanged.connect(browser.setFlagFilter)
        filterTab.layout().addWidget(self.flagView)
        
        filterCriterionLayout = QtGui.QHBoxLayout()
        filterCriterionLayout.addWidget(QtGui.QLabel(self.tr("General:")))
        filterCriterionLine = searchgui.CriterionLineEdit(self.browser.filterCriterion)
        filterCriterionLine.criterionChanged.connect(self.browser.setFilterCriterion)
        filterCriterionLine.criterionCleared.connect(functools.partial(self.browser.setFilterCriterion,None))
        filterCriterionLayout.addWidget(filterCriterionLine)
        filterTab.layout().addLayout(filterCriterionLayout)
        
        self.optionTab = QtGui.QWidget()
        self.optionTab.setLayout(QtGui.QVBoxLayout())
        self.tabWidget.addTab(self.optionTab,self.tr("Options"))
        
        # Option tab is filled in subclasses


class BrowserDialog(AbstractBrowserDialog):
    def __init__(self, parent, browser):
        super().__init__(parent, browser)
        optionLayout = self.optionTab.layout()
        lineLayout = QtGui.QHBoxLayout()
        optionLayout.addLayout(lineLayout)
        lineLayout.addWidget(QtGui.QLabel(self.tr("Item Display:")))
        profileType = browserdelegate.BrowserDelegate.profileType
        profileChooser = profilesgui.ProfileComboBox(delegates.profiles.category,
                                                     restrictToType=profileType,
                                                     default=self.browser.delegateProfile)
        profileChooser.profileChosen.connect(self._handleProfileChosen)

        lineLayout.addWidget(profileChooser)
        
        instantSearchBox = QtGui.QCheckBox(self.tr("Instant search"))
        instantSearchBox.setChecked(self.browser.searchBox.instant)
        instantSearchBox.clicked.connect(self.browser.searchBox.setInstantSearch)
        optionLayout.addWidget(instantSearchBox)
        
        hideInBrowserBox = QtGui.QCheckBox(self.tr("Show hidden values"))
        hideInBrowserBox.setChecked(self.browser.getShowHiddenValues())
        hideInBrowserBox.clicked.connect(self.browser.setShowHiddenValues)
        optionLayout.addWidget(hideInBrowserBox)
        
        viewConfigButton = QtGui.QPushButton(self.tr("Configure Views..."))
        viewConfigButton.clicked.connect(lambda: ViewConfigurationDialog(self.browser).exec_())
        viewConfigButton.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed))
        optionLayout.addWidget(viewConfigButton)
        
        optionLayout.addStretch(1)          
        
    def _handleProfileChosen(self, profile):
        for view in self.browser.views:
            view.itemDelegate().setProfile(profile)
            
        
class ViewConfigurationDialog(QtGui.QDialog):
    """The BrowserDialog allows you to configure the views of a browser and their layers."""
    def __init__(self, browser):
        """Initialize with the given parent, which must be the browser to configure."""
        QtGui.QDialog.__init__(self)
        self.setWindowTitle(self.tr("Browser configuration"))
        self.resize(450, 300)
        self.browser = browser
        
        layout = QtGui.QVBoxLayout(self)
        
        self.addButton = QtGui.QPushButton(utils.getIcon('add.png'), '')
        self.addButton.setEnabled(len(self.browser.views) < MAX_SUB_BROWSERS)
        self.addButton.clicked.connect(self._handleAddButton)
               
        self.tabWidget = QtGui.QTabWidget()
        self.tabWidget.setCornerWidget(self.addButton)
        self.tabWidget.setMovable(True)
        self.tabWidget.setTabsClosable(True)
        self.tabWidget.tabCloseRequested.connect(self._handleTabCloseRequested)
        self.tabWidget.tabBar().tabMoved.connect(self._handleTabMoved)
        layout.addWidget(self.tabWidget)
                    
        for index, view in enumerate(self.browser.views, start=1):
            self.tabWidget.addTab(SingleViewConfiguration(view), self.tr("Browser {}").format(index))
            
    def _handleAddButton(self):
        view = self.browser.addView()
        self.tabWidget.addTab(SingleViewConfiguration(view),
                              self.tr("Browser {}").format(self.tabWidget.count()+1))
        self.addButton.setEnabled(len(self.browser.views) < MAX_SUB_BROWSERS)
    
    def _handleTabCloseRequested(self, index):
        if len(self.browser.views) <= 1:
            return
        self.browser.removeView(index)
        tab = self.tabWidget.widget(index)
        self.tabWidget.removeTab(index)
        tab.setParent(None)
        self._setTabTitles()
    
    def _handleTabMoved(self, fromIndex, toIndex):
        self.browser.moveView(fromIndex, toIndex)
        self._setTabTitles()
        
    def _setTabTitles(self):
        for index in range(self.tabWidget.count()):
            self.tabWidget.setTabText(index, self.tr("Browser {}").format(index+1))
    
    
class SingleViewConfiguration(QtGui.QWidget):
    def __init__(self, view):
        super().__init__()
        self.model = view.model()
        layout = QtGui.QVBoxLayout(self)
        
        self.table = QtGui.QTableWidget()
        self.table.horizontalHeader().setVisible(False)
        #TODO: Does not work
        self.table.horizontalHeader().setResizeMode(0, QtGui.QHeaderView.Stretch)
        self.table.horizontalHeader().setResizeMode(1, QtGui.QHeaderView.Fixed)
        self.table.verticalHeader().setMovable(True)
        self.table.verticalHeader().sectionMoved.connect(self._handleSectionMoved)
        # Note: only the first column contains an item
        self.table.itemDoubleClicked.connect(lambda item: self._handleEditButton(item.row()))
        layout.addWidget(self.table)
        
        bottomLine = QtGui.QHBoxLayout()
        bottomLine.addWidget(QtGui.QLabel(self.tr("Add layer:")))
        self.layerTypeBox = QtGui.QComboBox()
        for name, (title, theClass) in browsermodel.layerClasses.items():
            self.layerTypeBox.addItem(title, name)
        bottomLine.addWidget(self.layerTypeBox)
        self.addLayerButton = QtGui.QPushButton(utils.getIcon('add.png'), '')
        self.addLayerButton.clicked.connect(self._handleAddLayerButton)
        bottomLine.addWidget(self.addLayerButton)
        
        bottomLine.addStretch()
        closeButton = QtGui.QPushButton(self.tr("Close"))
        closeButton.clicked.connect(self._close)
        bottomLine.addWidget(closeButton)
        layout.addLayout(bottomLine)
        
        self.updateLayerView()
    
    def updateLayerView(self):
        self.table.setRowCount(len(self.model.layers))
        self.table.setColumnCount(2)
        for i, layer in enumerate(self.model.layers):
            item = QtGui.QTableWidgetItem(layer.text())
            item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(i, 0, item)
            buttonWidget = QtGui.QWidget()
            buttonLayout = QtGui.QHBoxLayout(buttonWidget)
            buttonLayout.setContentsMargins(0, 0, 0, 0)
            editButton = QtGui.QPushButton(utils.getIcon('pencil.png'), '')
            editButton.clicked.connect(functools.partial(self._handleEditButton, i))
            buttonLayout.addWidget(editButton)
            removeButton = QtGui.QPushButton(utils.getIcon('remove.png'), '')
            removeButton.clicked.connect(functools.partial(self._handleRemoveButton, i))
            buttonLayout.addWidget(removeButton)
            self.table.setIndexWidget(self.table.model().index(i, 1), buttonWidget)
        self.table.resizeColumnsToContents()
        
    def _handleSectionMoved(self, logicalIndex, oldVisualIndex, newVisualIndex):
        self.model.moveLayer(oldVisualIndex, newVisualIndex)
        self.table.setRowCount(0) # event QTableView.clear does not reset visual indexes to logical indexes
        self.updateLayerView() # this will ensure that logical indices equal visual indices
        
    def _close(self):
        self.window().close()
        
    def _handleAddLayerButton(self):
        layerName = self.layerTypeBox.itemData(self.layerTypeBox.currentIndex())
        theClass = browsermodel.layerClasses[layerName][1]
        layer = theClass.openDialog(self)
        if layer is not None:
            self.model.addLayer(layer)
            self.updateLayerView()
    
    def _handleEditButton(self, index):
        layer = self.model.layers[index]
        newLayer = layer.openDialog(self, layer)
        if newLayer is not None:
            self.model.changeLayer(layer, newLayer)
            self.updateLayerView()
    
    def _handleRemoveButton(self, index):
        self.model.removeLayer(index)
        self.updateLayerView()
