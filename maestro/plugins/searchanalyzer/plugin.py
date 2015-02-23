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

"""This plugin adds a central widget that allows the user to search and will display the search result
table without any fancy grouping as the browser does (it will add titles, though)."""

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from ...core import tags, domains
from ... import search, config, application, database as db, utils
from ...search import criteria
from ...gui import mainwindow, dialogs, search as searchgui, widgets
from . import resources


def enable():
    mainwindow.addWidgetClass(mainwindow.WidgetClass(
        id = "searchanalyzer",
        name = QtWidgets.QApplication.translate("SearchAnalyzer", "Search Analyzer"),
        icon = QtGui.QIcon(":/maestro/plugins/searchanalyzer/searchanalyzer.png"),
        theClass = SearchAnalyzer))


def disable():
    mainwindow.removeWidgetClass("searchanalyzer")


class SearchAnalyzer(mainwindow.Widget):
    """Display search result tables and allow the user to search the database."""

    def __init__(self, state=None, **args):
        super().__init__(**args)
        self.criterion = None
        self.domain = domains.domains[0]

        self.worker = utils.worker.Worker()
        self.worker.done.connect(self.updateTable)
        self.worker.start()

        self.flagFilter = []

        # Initialize GUI
        layout = QtWidgets.QVBoxLayout(self)
        topLayout = QtWidgets.QHBoxLayout()
        layout.addLayout(topLayout)

        self.searchBox = searchgui.SearchBox()
        self.searchBox.criterionChanged.connect(self._handleCriterionChanged)
        topLayout.addWidget(self.searchBox)

        self.instantSearchBox = QtGui.QCheckBox(self.tr("Instant search"))
        self.instantSearchBox.setChecked(True)
        self.instantSearchBox.clicked.connect(self.searchBox.setInstantSearch)
        topLayout.addWidget(self.instantSearchBox)
        
        self.domainBox = widgets.DomainBox()
        self.domainBox.domainChanged.connect(self.setDomain)
        topLayout.addWidget(self.domainBox)
        
        topLayout.addStretch(1)

        self.table = QtWidgets.QTableWidget()
        layout.addWidget(self.table)
        
    def closeEvent(self, event):
        self.worker.quit()
        super().closeEvent(event)
        
    def setDomain(self, domain):
        """Change the domain that is being searched."""
        if domain != self.domain:
            self.domain = domain
            self._handleCriterionChanged()

    def updateTable(self):
        """Update the result table (in the GUI) with data from the result table (in the database)."""
        self.table.clear()
        rowCount = 0 if self.criterion is None else len(self.criterion.result)
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
                           ids=','.join(str(id) for id in self.criterion.result)))
        for i, row in enumerate(result):
            if i == 0:
                self.table.setColumnCount(len(row))
            for j, data in enumerate(row):
                item = QtWidgets.QTableWidgetItem(str(data))
                item.setFlags(Qt.ItemIsEnabled)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()
        self.table.setEnabled(True)

    def _handleCriterionChanged(self):
        """Reload search criterion. If there is a search criterion, then start search. Otherwise clear the
        result table."""
        self.worker.reset()
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.table.setEnabled(False)
        self.criterion = self.searchBox.criterion
        if self.criterion is not None:
            task = search.SearchTask(self.criterion, self.domain)
            self.worker.submit(task)
        else:
            self.updateTable()

    def setFlags(self, flagTypes):
        """Set the flag filter. Only elements that have all flags in *flagTypes* will be displayed as search
        results."""
        if set(flagTypes) != set(self.flagFilter):
            self.flagFilter = list(flagTypes)
            self._handleCriterionChanged()
