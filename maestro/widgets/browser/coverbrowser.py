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

import functools, weakref

from PyQt5 import QtCore, QtGui, QtWidgets
translate = QtCore.QCoreApplication.translate

from maestro import database as db, utils, search, logging, widgets
from maestro.core import flags, levels, tags, domains
from maestro.gui import selection, dockwidget, search as searchgui, mainwindow
from maestro.widgets.browser import dialog as browserdialog

_displayClasses = {}
_coverBrowsers = weakref.WeakSet()


def addDisplayClass(key, theClass):
    """Add a class to the list of display classes. When more than one class is available, the cover
    browser will display a combobox where the user can choose his preferred display class.
    *class* should be a subclass of AbstractCoverWidget."""
    if key in _displayClasses:
        logging.error(__name__, "There is already a cover browser display class with key '{}'.".format(key))
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
    

class CoverBrowser(widgets.Widget):
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
    hasOptionDialog = True
    
    def __init__(self, state=None, **args):
        super().__init__(**args)
        _coverBrowsers.add(self)
        self.domain = domains.domains[0]
        self.flagCriterion = None
        self.filterCriterion = None
        self.searchCriterion = None
        if state is not None:
            if 'domain' in state:
                self.domain = domains.domainById(state['domain'])
            if 'flags' in state:
                flagList = [flags.get(name) for name in state['flags'] if flags.exists(name)]
                if len(flagList) > 0:
                    self.flagCriterion = search.criteria.FlagCriterion(flagList)
            if 'filter' in state:
                try:
                    self.filterCriterion = search.criteria.parse(state['filter'])
                except search.criteria.ParseException:
                    logging.exception(__name__, "Could not parse the cover browser's filter criterion.")
        
        self.worker = utils.worker.Worker()
        self.worker.done.connect(self._loaded)
        self.worker.start()
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        controlLineLayout = QtWidgets.QHBoxLayout()
        style = self.style()
        controlLineLayout.setContentsMargins(style.pixelMetric(style.PM_LayoutLeftMargin),
                                             style.pixelMetric(style.PM_LayoutTopMargin),
                                             style.pixelMetric(style.PM_LayoutRightMargin),
                                             1)
        self.searchBox = searchgui.SearchBox()
        self.searchBox.criterionChanged.connect(self.search)
        controlLineLayout.addWidget(self.searchBox, 1)
        
        from maestro.widgets.browser.browser import FilterButton
        self.filterButton = FilterButton()
        self.filterButton.setEnabled(self.getFilter() is not None)
        controlLineLayout.addWidget(self.filterButton)
        self.filterButton.clicked.connect(self._handleFilterButton)
        
        self._display = None
        self._displayWidgets = {}
        self._displayConfig = state['config'] if state is not None and 'config' in state else {}

        self.displayChooser = QtWidgets.QComboBox()
        controlLineLayout.addWidget(self.displayChooser)
        self.displayChooser.currentIndexChanged.connect(self._handleDisplayChooser)
        self.updateDisplayChooser()
        
        # This option button is only used when dock widget title bars are hidden (otherwise the dock widget
        # title bar contains an analogous button).
        self.optionButton = dockwidget.DockWidgetTitleButton('options')
        self.optionButton.clicked.connect(functools.partial(self.toggleOptionDialog, self.optionButton))
        controlLineLayout.addWidget(self.optionButton)
        self.optionButton.setVisible(mainwindow.mainWindow.hideTitleBarsAction.isChecked())
        layout.addLayout(controlLineLayout)
        
        self.stackedLayout = QtWidgets.QStackedLayout()
        layout.addLayout(self.stackedLayout, 1)
        if state is not None and 'display' in state and state['display'] in _displayClasses:
            self.setDisplayKey(state['display'])
        else: self.setDisplayKey('table')

    def closeEvent(self, event):
        super().closeEvent(event)
        self.worker.quit()
        
    def saveState(self):
        state = {'domain': self.domain.id,
                 'display': self._display,
                 'config': {}}
        if self.filterCriterion is not None:
            state['filter'] = repr(self.filterCriterion)
        if self.flagCriterion is not None:
            state['flags'] = [flag.name for flag in self.flagCriterion.flags]
            
        # Save configuration of display classes
        for key, widget in self._displayWidgets.items():
            state['config'][key] = widget.state()
        # Keep state of widgets which have not been used this time.
        # Except there is no class anymore (e.g. because a plugin has been disabled).
        for key, c in self._displayConfig.items():
            if key not in state['config'] and key in _displayClasses:
                state['config'][key] = c
        return state
    
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
            self.stackedLayout.setCurrentWidget(display)
        elif key in _displayClasses:
            display = _displayClasses[key](self._displayConfig.get(key), self)
            self.stackedLayout.addWidget(display)
            self.stackedLayout.setCurrentWidget(display)
            self._displayWidgets[key] = display
        else:
            raise ValueError("Invalid display key '{}'".format(key))
            
        self.displayChooser.setCurrentIndex(self.displayChooser.findData(key))
        self.reload()
        # (Re)connect only after reload so that no global selection is set on startup. 
        display.selectionChanged.connect(self._handleSelectionChanged)
        
    def getDomain(self):
        """Return the domain whose elements are displayed."""
        return self.domain
        
    def setDomain(self, domain):
        """Define the domain whose elements are displayed."""
        if domain != self.domain:
            self.domain = domain
            self.reload()
            
    def getFilter(self):
        """Return the complete filter that is currently active (either a Criterion or None).
        The filter consists of the search criterion entered by the user, the selected flags and the static
        filter set in the configuration dialog.
        """ 
        return search.criteria.combine('AND', 
            [c for c in [self.searchCriterion, self.flagCriterion, self.filterCriterion] if c is not None])
        
    def activateFilter(self):
        """Activate and update filter in all views and reload."""
        self.filterButton.setEnabled(self.getFilter() is not None)
        self.reload()

    def search(self):
        """Start a search."""
        self.searchCriterion = self.searchBox.criterion
        self.activateFilter()
        
    def setFlagFilter(self, flags):
        """Set the browser's flag filter to the given list of flags."""
        if len(flags) == 0:
            if self.flagCriterion is not None:
                self.flagCriterion = None
                self.activateFilter()
        else:
            if self.flagCriterion is None or self.flagCriterion.flags != flags:
                self.flagCriterion = search.criteria.FlagCriterion(flags)
                self.activateFilter()
        
    def setFilterCriterion(self, criterion):
        """Set a single criterion that will be added to all other criteria from the searchbox (using AND)
        and thus form a permanent filter."""
        if criterion != self.filterCriterion:
            self.filterCriterion = criterion
            self.activateFilter()
            
    def reload(self):
        """Clear everything and rebuilt it from the database."""
        criterion = None
        if self.filterButton.active:
            criterion = self.getFilter()
        
        self.worker.reset()
        if criterion is not None:
            self.worker.submit(search.SearchTask(criterion, domain=self.domain))
        else: self._loaded(None)
            
    def _loaded(self, task):
        """Load covers after search for elements has finished. If no search was necessary, *task* is None.
        """
        if task is not None:
            if not isinstance(task, search.SearchTask): # subclasses might submit over tasks
                return
            elids = task.criterion.result
            if len(elids):
                filterClause = " AND el.id IN ({})".format(db.csList(elids))
            else:
                self.display().setCovers([], {})
                return
        else:
            filterClause = " AND el.domain={}".format(self.domain.id)
    
        result = db.query("""
            SELECT el.id, st.data
            FROM {p}elements AS el
                JOIN {p}stickers AS st ON el.id = st.element_id
            WHERE st.type = 'COVER' {filter}
            """, filter=filterClause)
        coverPaths = {id: path for id, path in result}
        ids = list(coverPaths.keys())
        levels.real.collect(ids)
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
        return #TODO
        s = self._displayWidgets[self._display].selection()
        if s is not None:
            selection.setGlobalSelection(s)

    def createOptionDialog(self, button=None):
        return BrowserDialog(button, self)
            
    def _handleFilterButton(self):
        """React to the filter button: Activate/deactive filter."""
        if self.getFilter() is not None:
            self.filterButton.setActive(not self.filterButton.active)
            self.reload()
    
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
            self.reload()
                
    def _handleDisplayChooser(self, i):
        """Handle the combobox which lets the user choose a display class."""
        key = self.displayChooser.itemData(i)
        if key != self._display:
            self.setDisplayKey(key)


class AbstractCoverWidget(QtWidgets.QWidget):
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
                
        instantSearchBox = QtWidgets.QCheckBox(self.tr("Instant search"))
        instantSearchBox.setChecked(self.browser.searchBox.instant)
        instantSearchBox.clicked.connect(self.browser.searchBox.setInstantSearch)
        optionLayout.addWidget(instantSearchBox)
        
        widget = browser.display().createConfigWidget(self)
        if widget is not None:
            optionLayout.addWidget(widget)
        optionLayout.addStretch(1)
