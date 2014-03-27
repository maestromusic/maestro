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

"""This plugin adds a central widget that allows the user to search and will display the search result
table without any fancy grouping as the browser does (it will add titles, though)."""

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ...core import tags
from ... import search, config, application, database as db, constants, utils
from ...search import criteria
from ...gui import mainwindow, dialogs, search as searchgui, dockwidget
from . import resources


def enable():
    mainwindow.addWidgetData(mainwindow.WidgetData(
        id = "searchanalyzer",
        name = QtGui.QApplication.translate("SearchAnalyzer", "Search Analyzer"),
        icon = QtGui.QIcon(":/omg/plugins/searchanalyzer/searchanalyzer.png"),
        theClass = SearchAnalyzer))


def disable():
    mainwindow.removeWidgetData("searchanalyzer")


class SearchAnalyzer(dockwidget.DockWidget):
    """Display search result tables and allow the user to search the database."""
    searchRequest = None

    def __init__(self, parent=None, **args):
        super().__init__(parent, **args)

        self.engine = search.SearchEngine()
        self.engine.searchFinished.connect(self._handleSearchFinished)

        self.flagFilter = []

        # Initialize GUI
        widget = QtGui.QWidget()
        self.setWidget(widget)
        layout = QtGui.QVBoxLayout(widget)
        topLayout = QtGui.QHBoxLayout()
        layout.addLayout(topLayout)

        self.searchBox = searchgui.SearchBox()
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
        layout.addWidget(self.table)

    def _handleSearchFinished(self, searchRequest):
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
            for j, data in enumerate(row):
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

    def setFlags(self, flagTypes):
        """Set the flag filter. Only elements that have all flags in *flagTypes* will be displayed as search
        results."""
        if set(flagTypes) != set(self.flagFilter):
            self.flagFilter = list(flagTypes)
            self._handleCriterionChanged()

    def _handleOptionButton(self):
        """Open the option popup."""
        dialog = OptionPopup(self, self.optionButton)
        dialog.show()


class OptionPopup(dialogs.FancyTabbedPopup):
    """Small popup which currently only allows to set a list of flags. Only elements with all of these flags
    will be displayed in the search results."""
    def __init__(self, searchAnalyzer, parent):
        dialogs.FancyTabbedPopup.__init__(self, parent, 300, 200)

        from ...gui import browserdialog
        self.flagView = browserdialog.FlagView(searchAnalyzer.flagFilter)
        self.flagView.selectionChanged.connect(lambda: searchAnalyzer.setFlags(self.flagView.selectedFlagTypes))
        self.tabWidget.addTab(self.flagView, "Flags")
