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
translate = QtCore.QCoreApplication.translate

from . import mainwindow, browserdialog, selection, dockwidget
from .misc import busyindicator
from ..models import browser as browsermodel
from .. import database as db, utils, imageloader, config
from ..core import covers, levels, nodes, tags, elements
from ..search import searchbox, criteria


_displayClasses = {}
_coverBrowsers = weakref.WeakSet()


def addDisplayClass(key, theClass):
    """Add a class to the list of display classes. When more than one class is available, the cover
    browser will display a combobox where the user can choose his preferred display class.
    *class* should be a subclass of AbstractCoverWidget."""
    if key in _displayClasses:
        from .. import logging
        logger = logging.getLogger(__name__)
        logger.error("There is already a cover browser display class with key '{}'.".format(key))
        return
    
    _displayClasses[key] = theClass
    for coverBrowser in _coverBrowsers:
        coverBrowser.updateDisplayChooser()

        
def removeDisplayClass(key):
    """Remove the display class identified by *key*. Switch cover browsers that currently use this class to
    the standard class "table"."""
    assert key != "table"
    del _displayClasses[key]
    for coverBrowser in _coverBrowsers:
        if key == coverBrowser.displayKey():
            coverBrowser.setDisplayKey("table")
        coverBrowser.updateDisplayChooser()
    

class CoverBrowser(dockwidget.DockWidget):
    """A cover browser is similar to the usual browser but shows covers instead of a tree structure of
    elements. Like the browser it has a search box and a configuration widget that allows to set filters.
    
    To actually display covers CoverBrowser uses a display class (subclass of AbstractCoverDisplayWidget).
    The default display class is provided by covertable.CoverTable. Plugins can add more classes via
    addDisplayClass. When more than one class is available, CoverBrowser will contain a combobox where the
    user can choose his preferred display class. 
    """
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
        """Return the current display widget (instance of the current display class)."""
        return self._displayWidgets[self._display]
    
    def displayKey(self):
        """Return the key of the current display class/widget."""
        return self._display
    
    def setDisplayKey(self, key):
        """Set the current display class/widget to the one identified by *key*."""
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
        """Start a search."""
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
        """React to selection changes in the current display widget."""
        s = self._display.selection()
        if s is not None:
            selection.setGlobalSelection(s)
        
    def createOptionDialog(self, parent):
        return BrowserDialog(parent, self)
    
    def _handleHideTitleBarAction(self, checked):
        super()._handleHideTitleBarAction(checked)
        if hasattr(self, 'optionButton'): # false during construction
            self.optionButton.setVisible(checked)
            
    def updateDisplayChooser(self):
        """Update contents and visibility of the combobox which lets the user choose a display class."""
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
        """Handle the combobox which lets the user choose a display class."""
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
    """Base class for classes which can be used as display class for CoverBrowser. Plugins can subclass
    this class and register their cover widgets with addDisplayClass."""
    selectionChanged = QtCore.pyqtSignal()
    
    @classmethod
    def getTitle(cls):
        """Return a user-friendly title for this display class."""
        raise NotImplementedError()
    
    def setCovers(self, ids, coverPaths):
        """Set the covers that are displayed. *ids* is a list of elements-ids (which can be used to fetch
        information besides covers, e.g. for tooltips). *coverPaths* is a dict mapping ids to the cover path
        (relative to the cover directory). Covers should be displayed in the order specified by *ids*."""
        raise NotImplementedError()
    
    def selection(self):
        """Return the current selection as selection.Selection instance."""
        return None
    
    def createConfigWidget(self, parent):
        """Return a configuration widget for this display widget. May return None."""
        return None
    
    def state(self):
        """Return a dict storing the configuration of this widget. It will be passed into the constructor
        when the program is launched the next time."""
        return {}

            
class BrowserDialog(browserdialog.AbstractBrowserDialog):
    """Configuration dialog for the cover browser. Besides the usual filter configuration widgets it contains
    the configuration widget provided by AbstractCoverWidget.createConfigWidget."""
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
        