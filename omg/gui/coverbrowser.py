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

import os.path, collections, functools, weakref

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import mainwindow, browserdialog, selection, dockwidget
from .misc import busyindicator
from ..models import browser as browsermodel
from .. import database as db, utils, imageloader, config
from ..core import covers, levels, nodes, tags, elements
from ..search import searchbox, criteria

translate = QtCore.QCoreApplication.translate

_displayClasses = {}
_coverBrowsers = weakref.WeakSet()


def addDisplayClass(key, theClass):
    if key in _displayClasses:
        from .. import logging
        logger = logging.getLogger(__name__)
        logger.error("There is already a cover browser display class with key '{}'.".format(key))
        return
    
    _displayClasses[key] = theClass
    for coverBrowser in _coverBrowsers:
        coverBrowser.updateDisplayChooser()

        
def removeDisplayClass(key):
    assert key != "table"
    del _displayClasses[key]
    for coverBrowser in _coverBrowsers:
        if key == coverBrowser.displayKey():
            coverBrowser.setDisplayKey("table")
        coverBrowser.updateDisplayChooser()
    

class CoverBrowser(dockwidget.DockWidget):
    # The option dialog if it is open, and the index of the tab that was active when the dialog was closed.
    _dialog = None
    _lastDialogTabIndex = 0
    
    def __init__(self, parent=None, state=None, **args):
        super().__init__(parent, **args)
        _coverBrowsers.add(self)
        widget = QtGui.QWidget()
        self.setWidget(widget)
        
        layout = QtGui.QVBoxLayout(widget)
        
        controlLineLayout = QtGui.QHBoxLayout()
        self.searchBox = searchbox.SearchBox()
        self.searchBox.criterionChanged.connect(self.search)
        controlLineLayout.addWidget(self.searchBox, 1)
        
        self._display = None
        self._displayWidgets = {}
        self._displayConfig = state['config'] if state is not None and 'config' in state else {}

        self.displayChooser = QtGui.QComboBox()
        controlLineLayout.addWidget(self.displayChooser)
        self.displayChooser.currentIndexChanged.connect(self._handleDisplayChooser)
        self.updateDisplayChooser()
        
        # This option button is only used when dock widget title bars are hidden (otherwise the dock widget
        # title bar contains an analogous button).
        self.optionButton = dockwidget.DockWidgetTitleButton('options')
        self.optionButton.clicked.connect(functools.partial(self.openOptionDialog, self.optionButton))
        controlLineLayout.addWidget(self.optionButton)
        self.optionButton.setVisible(mainwindow.mainWindow.hideTitleBarsAction.isChecked())
        layout.addLayout(controlLineLayout)
        
        self.stackedLayout = QtGui.QStackedLayout()
        layout.addLayout(self.stackedLayout, 1)
        if state is not None and 'display' in state and state['display'] in _displayClasses:
            self.setDisplayKey(state['display'])
        else: self.setDisplayKey('table')
        
        self.flagCriterion = None
        self.filterCriterion = None
        self.searchCriterion = None
        self.searchRequest = None
        
        if browsermodel.searchEngine is None:
            browsermodel.initSearchEngine()
        browsermodel.searchEngine.searchFinished.connect(self._handleSearchFinished)
        self.resultTable = browsermodel.searchEngine.createResultTable("coverbrowser")

        self.load()
        
    def saveState(self):
        config = {}
        for key, widget in self._displayWidgets.items():
            config[key] = widget.state()
        # Keep state of widgets which have not been used this time.
        # Except there is no class anymore (e.g. because a plugin has been disabled).
        for key, c in self._displayConfig.items():
            if key not in config and key in _displayClasses:
                config[key] = c
        return {'display': self._display, 'config': config}
    
    def display(self):
        return self._displayWidgets[self._display]
    
    def displayKey(self):
        return self._display
    
    def setDisplayKey(self, key):
        if self._display is not None:
            display = self._displayWidgets[self._display]
            display.selectionChanged.disconnect(self._handleSelectionChanged)
            
        self._display = key
        
        if key in self._displayWidgets:
            display = self._displayWidgets[key]
            display.selectionChanged.connect(self._handleSelectionChanged)
            self.stackedLayout.setCurrentWidget(display)
        elif key in _displayClasses:
            display = _displayClasses[key](self._displayConfig.get(key), self)
            display.selectionChanged.connect(self._handleSelectionChanged)
            self.stackedLayout.addWidget(display)
            self.stackedLayout.setCurrentWidget(display)
            self._displayWidgets[key] = display
        else:
            raise ValueError("Invalid display key '{}'".format(key))
            
        self.displayChooser.setCurrentIndex(self.displayChooser.findData(key))
        if hasattr(self, 'table'): # otherwise this is called during the constructor which will call load
            self.reset()
        
    def setFlagFilter(self, flags):
        """Set the browser's flag filter to the given list of flags."""
        if len(flags) == 0:
            if self.flagCriterion is not None:
                self.flagCriterion = None
                self.load()
        else:
            if self.flagCriterion is None or self.flagCriterion.flags != flags:
                self.flagCriterion = criteria.FlagCriterion(flags)
                self.load()
        
    def setFilterCriterion(self, criterion):
        """Set a single criterion that will be added to all other criteria from the searchbox (using AND)
        and thus form a permanent filter."""
        if criterion != self.filterCriterion:
            self.filterCriterion = criterion
            self.load()
            
    def search(self):
        self.searchCriterion = self.searchBox.criterion
        self.load()
        
    def load(self):
        """Load contents into the cover browser, based on the current filterCriterion, flagCriterion and
        searchCriterion. If a search is necessary this will only start a search and actual loading will
        be done in _handleSearchFinished.
        """
        if self.searchRequest is not None:
            self.searchRequest.stop()
            self.searchRequest = None
            
        # Combine returns None if all input criteria are None
        criterion = criteria.combine('AND',
                            [c for c in (self.filterCriterion, self.flagCriterion, self.searchBox.criterion)
                             if c is not None])

        if criterion is not None:
            self.table = self.resultTable
            self.searchRequest = browsermodel.searchEngine.search(
                                                  fromTable = db.prefix+"elements",
                                                  resultTable = self.resultTable,
                                                  criterion = criterion)
        else:
            self.table = db.prefix + "elements"
            self.reset()
            
    def _handleSearchFinished(self,request):
        """React to searchFinished signals."""
        if request is self.searchRequest:
            self.searchRequest = None
            self.reset()
            
    def reset(self):
        result = db.query("""
            SELECT el.id, st.data
            FROM {1} AS el
                JOIN {0}stickers AS st ON el.id = st.element_id
            WHERE st.type = 'COVER'
            """.format(db.prefix, self.table))
        
        coverPaths = {id: path for id, path in result}
        ids = list(coverPaths.keys())
        levels.real.collectMany(ids)
        if tags.isInDb("artist") and tags.isInDb("date"):
            sortValues = {}
            artistTag = tags.get("artist")
            dateTag = tags.get("date")
            for id in ids:
                el = levels.real[id]
                sortValues[id] = (el.tags[artistTag][0] if artistTag in el.tags else utils.PointAtInfinity(),
                                  el.tags[dateTag][0] if dateTag in el.tags else utils.PointAtInfinity())
            ids.sort(key=sortValues.get)

        self.display().setCovers(ids, coverPaths)
        
    def _handleSelectionChanged(self):
        s = self.display.selection()
        if s is not None:
            selection.setGlobalSelection(s)
        
    def createOptionDialog(self, parent):
        return BrowserDialog(parent, self)
    
    def _handleHideTitleBarAction(self, checked):
        super()._handleHideTitleBarAction(checked)
        if hasattr(self, 'optionButton'): # false during construction
            self.optionButton.setVisible(checked)
            
    def updateDisplayChooser(self):
        self.displayChooser.currentIndexChanged.disconnect(self._handleDisplayChooser)
        self.displayChooser.clear()
        values = [(theClass.getTitle(), key) for key, theClass in _displayClasses.items()]
        values.sort()
        for title, key in values:
            self.displayChooser.addItem(title, key)
            if key == self._display:
                self.displayChooser.setCurrentIndex(self.displayChooser.count()-1)
        self.displayChooser.setVisible(len(values) > 1)
        self.displayChooser.currentIndexChanged.connect(self._handleDisplayChooser)
        if self._display is not None and self._display not in [v[1] for v in values]:
            self.reset()
                
    def _handleDisplayChooser(self, i):
        key = self.displayChooser.itemData(i)
        if key != self._display:
            self.setDisplayKey(key)
        

mainwindow.addWidgetData(mainwindow.WidgetData(
        id = "coverbrowser",
        name = translate("CoverBrowser","Cover Browser"),
        icon = utils.getIcon('widgets/coverbrowser.png'),
        theClass = CoverBrowser,
        preferredDockArea = Qt.RightDockWidgetArea))


class AbstractCoverWidget(QtGui.QWidget):
    selectionChanged = QtCore.pyqtSignal()
    
    @classmethod
    def getTitle(cls):
        raise NotImplementedError()
    
    def setCovers(self, ids, coverPaths):
        raise NotImplementedError()
    
    def selection(self):
        return None
    
    def createConfigWidget(self, parent):
        return None
    
    def state(self):
        return {}

            
class BrowserDialog(browserdialog.AbstractBrowserDialog):
    def __init__(self, parent, browser):
        super().__init__(parent, browser)
        optionLayout = self.optionTab.layout()
                
        instantSearchBox = QtGui.QCheckBox(self.tr("Instant search"))
        instantSearchBox.setChecked(self.browser.searchBox.getInstantSearch())
        instantSearchBox.clicked.connect(self.browser.searchBox.setInstantSearch)
        optionLayout.addWidget(instantSearchBox)
        
        widget = browser.display().createConfigWidget(self)
        if widget is not None:
            optionLayout.addWidget(widget)
        optionLayout.addStretch(1)
        