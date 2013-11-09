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

"""This plugin adds a central widget that allows the user to search and will display the search result
table without any fancy grouping as the browser does (it will add titles, though)."""

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ...core import tags
from ... import search, config, application, database as db, constants, utils
from ...search import searchbox, criteria
from ...gui import mainwindow, dialogs
from . import resources


_action = None # the action that is inserted into the Extras menu
_widget = None # the dialog widget must be stored in a variable or it will vanish immediately


def enable():
    global _action
    _action = QtGui.QAction(application.mainWindow)
    _action.setText(QtGui.QApplication.translate("SearchAnalyzer","Search Analyzer"))
    _action.triggered.connect(_openDialog)
    mainwindow.addWidgetData(mainwindow.WidgetData(
        id = "searchanalyzer",
        name = QtGui.QApplication.translate("SearchAnalyzer","Search Analyzer"),
        icon = QtGui.QIcon(":/omg/plugins/searchanalyzer/searchanalyzer.png"),
        theClass = SearchAnalyzer))


def mainWindowInit():
    application.mainWindow.menus['extras'].addAction(_action)


def disable():
    application.mainWindow.menus['extras'].removeAction(_action)
    mainwindow.removeWidgetData("searchanalyzer")


def defaultStorage():
    return {"SECTION:searchanalyzer": {
            "size": (800,600),
            "pos": None # Position of the window as tuple or None to center the window
        }}


def _openDialog():
    """Open the SearchAnalyzer as a dialog."""
    global _widget # store the widget in a variable or it will immediately destroyed
    _widget = SearchAnalyzer(dialog=True)
    _widget.setWindowTitle("OMG version {} – Search Analyzer".format(constants.VERSION))

    # TODO: use restoreGeometry
    screen = QtGui.QDesktopWidget().screenGeometry()
    size = QtCore.QSize(*config.storage.searchanalyzer.size)
    _widget.resize(size)
    pos = config.storage.searchanalyzer.pos
    if pos is None:
        _widget.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)
    else: _widget.move(*pos)
    _widget.show()


class SearchAnalyzer(QtGui.QDialog):
    """Display search result tables and allow the user to search the database."""
    searchRequest = None
    
    def __init__(self, parent=None, dialog=False):
        QtGui.QDialog.__init__(self,parent)

        self.engine = search.SearchEngine()
        self.engine.searchFinished.connect(self._handleSearchFinished)
        
        self.flagFilter = []
        
        # Initialize GUI
        self.setLayout(QtGui.QVBoxLayout())
        topLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(topLayout)

        self.searchBox = searchbox.SearchBox()
        self.searchBox.criterionChanged.connect(self._handleCriterionChanged)
        topLayout.addWidget(self.searchBox)

        self.optionButton = QtGui.QToolButton(self)
        self.optionButton.setIcon(utils.getIcon("options.png"))
        self.optionButton.clicked.connect(self._handleOptionButton)
        topLayout.addWidget(self.optionButton)
        
        self.instantSearchBox = QtGui.QCheckBox(self.tr("Instant search"))
        self.instantSearchBox.setChecked(True)
        self.instantSearchBox.clicked.connect(self.searchBox.setInstantSearch)
        topLayout.addWidget(self.instantSearchBox)
        topLayout.addStretch(1)

        self.table = QtGui.QTableWidget()
        self.layout().addWidget(self.table)

        if dialog:
            buttonLayout = QtGui.QHBoxLayout()
            self.layout().addLayout(buttonLayout)
            buttonLayout.addStretch(1)
            closeButton = QtGui.QPushButton(QtGui.QIcon.fromTheme('window-close'),self.tr("Close"))
            closeButton.clicked.connect(self.close)
            buttonLayout.addWidget(closeButton,0)
        
    def _handleSearchFinished(self,searchRequest):
        """If the search was successful, update the result list."""
        if searchRequest is self.searchRequest and not searchRequest.stopped:
            self.updateTable()

    def updateTable(self):
        """Update the result table (in the GUI) with data from the result table (in the database)."""
        self.table.clear()
        rowCount = 0 if self.searchRequest is None else len(self.searchRequest.result)
        self.table.setRowCount(rowCount)
        if rowCount == 0:
            return
        # Add the titles. If there are more than one title, concatenate them.
        result = db.query("""
                SELECT el.id AS id, GROUP_CONCAT(v.value {separator} ', ') AS value
                FROM {0}elements AS el
                            LEFT JOIN {0}tags AS t ON el.id = t.element_id AND t.tag_id = {titleTag}
                            LEFT JOIN {0}values_varchar AS v ON t.tag_id = v.tag_id AND t.value_id = v.id
                WHERE el.id IN ({ids})
                GROUP BY el.id
                """.format(db.prefix,
                           separator='SEPARATOR' if db.type == 'mysql' else ',',
                           titleTag=tags.TITLE.id,
                           ids=','.join(str(id) for id in self.searchRequest.result)))
        for i, row in enumerate(result):
            if i == 0:
                self.table.setColumnCount(len(row))
            for j,data in enumerate(row):
                if db.isNull(data):
                    data = None
                item = QtGui.QTableWidgetItem(str(data))
                item.setFlags(Qt.ItemIsEnabled)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()
        self.table.setEnabled(True)
            
    def _handleCriterionChanged(self):
        """Reload search criterion. If there is a search criterion, then start search. Otherwise clear the
        result table."""
        if self.searchRequest is not None:
            self.searchRequest.stop()
            self.table.clear()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.table.setEnabled(True)
        
        self.table.setEnabled(False)
        if self.searchBox.criterion is not None:
            self.searchRequest = self.engine.search("{}elements".format(db.prefix), self.searchBox.criterion)
        else:
            self.searchRequest = None
            self.updateTable()
    
    def setFlags(self,flagTypes):
        """Set the flag filter. Only elements that have all flags in *flagTypes* will be displayed as search
        results."""
        if set(flagTypes) != set(self.flagFilter):
            self.flagFilter = list(flagTypes)
            self._handleCriterionChanged()
        
    def _handleOptionButton(self):
        """Open the option popup."""
        dialog = OptionPopup(self,self.optionButton)
        dialog.show()


class OptionPopup(dialogs.FancyTabbedPopup):
    """Small popup which currently only allows to set a list of flags. Only elements with all of these flags
    will be displayed in the search results."""
    def __init__(self,searchAnalyzer,parent):
        dialogs.FancyTabbedPopup.__init__(self,parent,300,200)
        
        from ...gui import browserdialog
        self.flagView = browserdialog.FlagView(searchAnalyzer.flagFilter)
        self.flagView.selectionChanged.connect(lambda: searchAnalyzer.setFlags(self.flagView.selectedFlagTypes))
        self.tabWidget.addTab(self.flagView,"Flags")
        