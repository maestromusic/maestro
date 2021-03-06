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

from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt

from maestro import utils
from maestro.core import tags
from maestro.gui import dialogs, search as searchgui, widgets as guiwidgets
from maestro.gui.preferences import profiles as profilesgui
from maestro.widgets.browser import model

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
    """Popup dialog that allows to configure the Browser. Browser and CoverBrowser each use their own
    subclasses of this abstract class."""
    def __init__(self, parent, browser):
        super().__init__(parent, 300, 200)
        self.browser = browser
        self.viewConfigurations = []
                
        filterTab = QtWidgets.QWidget()
        filterTab.setLayout(QtWidgets.QVBoxLayout())
        self.tabWidget.addTab(filterTab, self.tr("Filter"))
        
        domainLayout = QtWidgets.QHBoxLayout()
        domainLayout.addWidget(QtWidgets.QLabel(self.tr("Domain:")))
        self.domainBox = guiwidgets.DomainBox(self.browser.getDomain())
        self.domainBox.domainChanged.connect(self.browser.setDomain)
        domainLayout.addWidget(self.domainBox)
        filterTab.layout().addLayout(domainLayout)
        
        filterTab.layout().addWidget(QtWidgets.QLabel(self.tr("Flags:")))
        flagList = self.browser.flagCriterion.flags if self.browser.flagCriterion is not None else []
        
        self.flagView = searchgui.FlagView(flagList)
        self.flagView.selectionChanged.connect(browser.setFlagFilter)
        filterTab.layout().addWidget(self.flagView)
        
        filterCriterionLayout = QtWidgets.QHBoxLayout()
        filterCriterionLayout.addWidget(QtWidgets.QLabel(self.tr("General:")))
        filterCriterionLine = searchgui.CriterionLineEdit(self.browser.filterCriterion)
        filterCriterionLine.criterionChanged.connect(self.browser.setFilterCriterion)
        filterCriterionLine.criterionCleared.connect(functools.partial(self.browser.setFilterCriterion,None))

        filterCriterionLayout.addWidget(filterCriterionLine)
        filterTab.layout().addLayout(filterCriterionLayout)
        
        self.optionTab = QtWidgets.QWidget()
        self.optionTab.setLayout(QtWidgets.QVBoxLayout())
        self.tabWidget.addTab(self.optionTab,self.tr("Options"))

        # Option tab is filled in subclasses


class BrowserDialog(AbstractBrowserDialog):
    """This is the subclass of AbstractBrowserDialog used for the browser."""
    def __init__(self, parent, browser):
        super().__init__(parent, browser)
        optionLayout = self.optionTab.layout()
        lineLayout = QtWidgets.QHBoxLayout()
        optionLayout.addLayout(lineLayout)
        lineLayout.addWidget(QtWidgets.QLabel(self.tr("Item Display:")))
        profileChooser = profilesgui.ProfileComboBox('delegates', 'browser',
                                                     default=self.browser.delegateProfile)
        profileChooser.profileChosen.connect(self._handleProfileChosen)
        lineLayout.addWidget(profileChooser)
        
        instantSearchBox = QtWidgets.QCheckBox(self.tr("Instant search"))
        instantSearchBox.setChecked(self.browser.searchBox.instant)
        instantSearchBox.clicked.connect(self.browser.searchBox.setInstantSearch)
        optionLayout.addWidget(instantSearchBox)
        
        hideInBrowserBox = QtWidgets.QCheckBox(self.tr("Show hidden values"))
        hideInBrowserBox.setChecked(self.browser.getShowHiddenValues())
        hideInBrowserBox.clicked.connect(self.browser.setShowHiddenValues)
        optionLayout.addWidget(hideInBrowserBox)
        
        viewConfigButton = QtWidgets.QPushButton(self.tr("Configure Views..."))
        viewConfigButton.clicked.connect(self._handleViewConfigButton)
        viewConfigButton.setSizePolicy(QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed))
        optionLayout.addWidget(viewConfigButton)
        
        optionLayout.addStretch(1)          
        
    def _handleProfileChosen(self, profile):
        for view in self.browser.views:
            view.itemDelegate().setProfile(profile)
            
    def _handleViewConfigButton(self):
        self.close()
        ViewConfigurationDialog(self.browser).exec_()
            
        
class ViewConfigurationDialog(QtWidgets.QDialog):
    """The BrowserDialog allows you to configure the views of a browser and their layers."""
    def __init__(self, browser):
        """Initialize with the given parent, which must be the browser to configure."""
        QtWidgets.QDialog.__init__(self)
        self.setWindowTitle(self.tr("Browser configuration"))
        self.resize(450, 300)
        self.browser = browser
        
        layout = QtWidgets.QVBoxLayout(self)
        self.addButton = QtWidgets.QPushButton(utils.images.icon('list-add'), '')
        self.addButton.setEnabled(len(self.browser.views) < MAX_SUB_BROWSERS)
        self.addButton.clicked.connect(self._handleAddButton)
               
        self.tabWidget = QtWidgets.QTabWidget()
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
    
    
class SingleViewConfiguration(QtWidgets.QWidget):
    def __init__(self, view):
        super().__init__()
        self.model = view.model()
        layout = QtWidgets.QVBoxLayout(self)
        
        self.table = QtWidgets.QTableWidget()
        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setSectionsMovable(True)
        self.table.verticalHeader().sectionMoved.connect(self._handleSectionMoved)
        # Note: only the first column contains an item
        self.table.itemDoubleClicked.connect(lambda item: self._handleEditButton(item.row()))
        layout.addWidget(self.table)
        
        bottomLine = QtWidgets.QHBoxLayout()
        bottomLine.addWidget(QtWidgets.QLabel(self.tr("Add layer:")))
        self.layerTypeBox = QtWidgets.QComboBox()
        for name, (title, theClass) in model.layerClasses.items():
            self.layerTypeBox.addItem(title, name)
        bottomLine.addWidget(self.layerTypeBox)
        self.addLayerButton = QtWidgets.QPushButton(utils.images.icon('list-add'), '')
        self.addLayerButton.clicked.connect(self._handleAddLayerButton)
        bottomLine.addWidget(self.addLayerButton)
        
        bottomLine.addStretch()
        closeButton = QtWidgets.QPushButton(self.tr("Close"))
        closeButton.clicked.connect(self._close)
        bottomLine.addWidget(closeButton)
        layout.addLayout(bottomLine)
        
        self.updateLayerView()
    
    def updateLayerView(self):
        self.table.setRowCount(len(self.model.layers))
        self.table.setColumnCount(2)
        for i, layer in enumerate(self.model.layers):
            item = QtWidgets.QTableWidgetItem(layer.text())
            item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(i, 0, item)
            buttonWidget = QtWidgets.QWidget()
            buttonLayout = QtWidgets.QHBoxLayout(buttonWidget)
            buttonLayout.setContentsMargins(0, 0, 0, 0)
            editButton = QtWidgets.QPushButton(utils.images.icon('document-edit'), '')
            editButton.clicked.connect(functools.partial(self._handleEditButton, i))
            buttonLayout.addWidget(editButton)
            removeButton = QtWidgets.QPushButton(utils.images.icon('list-remove'), '')
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
        theClass = model.layerClasses[layerName][1]
        layer = theClass.openDialog(self, self.model)
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
