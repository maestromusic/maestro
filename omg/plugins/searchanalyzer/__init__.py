# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg import search, config, application, database as db, constants
from omg.search import searchbox
from omg.gui import mainwindow


_action = None # the action that is inserted into the Extras menu
_widget = None # the dialog widget must be stored in a variable or it will vanish immediately


# The next few (undocumented) functions are called by the plugin system
def enable():
    global _action
    _action = QtGui.QAction(application.mainWindow)
    _action.setText(QtGui.QApplication.translate("SearchAnalyzer","Search Analyzer"))
    _action.triggered.connect(_openDialog)
    mainwindow.addWidgetData(mainwindow.WidgetData(
        "searchanalyzer",
        QtGui.QApplication.translate("SearchAnalyzer","Search Analyzer"),
        SearchAnalyzer,True,False))


def mainWindowInit():
    application.mainWindow.menus['extras'].addAction(_action)


def disable():
    application.mainWindow.menus['extras'].removeAction(_action)
    mainwindow.removeWidgetData("searchanalyzer")


def defaultStorage():
    return {"searchanalyzer": {
            "size": ((800,600),"Size of the window."),
            "pos": (None,"Position of the window as tuple or None to center the window")
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
    def __init__(self,parent=None,dialog=False):
        QtGui.QDialog.__init__(self,parent)

        self.engine = search.SearchEngine()
        #self.engine.searchStarted.connect(self.updateLabel)
        self.engine.searchFinished.connect(self.updateTable)
        self.resultTable = self.engine.createResultTable("analyzer",
                "name VARCHAR({}) NULL".format(constants.TAG_VARCHAR_LENGTH))
        
        # Initialize GUI
        self.setLayout(QtGui.QVBoxLayout())
        topLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(topLayout)

        self.searchBox = searchbox.SearchBox()
        self.searchBox.criteriaChanged.connect(self._handleCriteriaChanged)
        topLayout.addWidget(self.searchBox)

        self.instantSearchBox = QtGui.QCheckBox(self.tr("Instant search"))
        self.instantSearchBox.setChecked(True)
        self.instantSearchBox.clicked.connect(self.searchBox.setInstantSearch)
        topLayout.addWidget(self.instantSearchBox)
        topLayout.addStretch(1)

        self.label = QtGui.QLabel()
        self.layout().addWidget(self.label)

        self.table = QtGui.QTableWidget()
        self.layout().addWidget(self.table)

        if dialog:
            buttonLayout = QtGui.QHBoxLayout()
            self.layout().addLayout(buttonLayout)
            buttonLayout.addStretch(1)
            closeButton = QtGui.QPushButton(QtGui.QIcon.fromTheme('window-close'),self.tr("Close"))
            closeButton.clicked.connect(self.close)
            buttonLayout.addWidget(closeButton,0)

    def updateLabel(self):
        self.criteriaLabel.setText(", ".join(str(criterion) for criterion in self.engine.getCriteria()))

    def updateTable(self):
        self.table.clear()
        # Add the titles. If there are more than one title, concatenate them.
        db.query("""
            UPDATE {1} AS res JOIN 
                (SELECT el.id AS id, GROUP_CONCAT(v.value SEPARATOR ', ') AS value
                FROM {0}elements AS el JOIN {0}tags AS t ON el.id = t.element_id JOIN {0}values_varchar AS v ON t.tag_id = v.tag_id AND t.value_id = v.id
                WHERE v.tag_id = 4
                GROUP BY el.id) AS sub
            ON res.id = sub.id
            SET res.name = sub.value
            """.format(db.prefix,self.resultTable))
        result = db.query("SELECT * FROM {}".format(self.resultTable))
        self.table.setRowCount(len(result))
        for i,row in enumerate(result):
            if i == 0:
                self.table.setColumnCount(len(row))
            for j,data in enumerate(row):
                if db.isNull(data):
                    data = None
                item = QtGui.QTableWidgetItem(str(data))
                item.setFlags(Qt.ItemIsEnabled)
                self.table.setItem(i,j,item)
        self.table.resizeColumnsToContents()
        self.table.setEnabled(True)
            
    def _handleCriteriaChanged(self):
        criteria = self.searchBox.getCriteria()
        if len(criteria) == 0:
            self.table.clear()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.table.setEnabled(True)
            self.label.setText("")
        else:
            self.table.setEnabled(False)
            self.engine.runSearch("{}elements".format(db.prefix),self.resultTable,criteria)
