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

"""The DBAnalyzer displays statistics about the database, finds errors in it and allows the user to correct
them. It is provided as central widget, dialog (in the extras menu) and standalone application
(bin/dbanalyzer)."""

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from maestro import database as db, application, config, utils, VERSION, widgets
from . import resources, checks


_action = None # the action that is inserted into the Extras menu
_widget = None # the dialog widget must be stored in a variable or it will vanish immediately


def enable():
    global _action
    _action = QtWidgets.QAction(application.mainWindow)
    _action.setText(QtWidgets.QApplication.translate("DBAnalyzerDialog", "DB Analyzer"))
    _action.triggered.connect(_openDialog)
    widgets.addClass(_getWidgetClass())


def mainWindowInit():
    application.mainWindow.menus['extras'].addAction(_action)


def disable():
    application.mainWindow.menus['extras'].removeAction(_action)
    widgets.removeClass("dbanalyzer")


def defaultStorage():
    return {"dbanalyzer": {
            "size": [800,600],
            "pos": None # Position of the window as tuple or None to center the window
        }}
    
    
def _getWidgetClass():
    return widgets.WidgetClass(
        id = "dbanalyzer",
        name = QtWidgets.QApplication.translate("DBAnalyzerDialog", "DB Analyzer"),
        theClass = DBAnalyzer,
        areas = 'central',
        icon = QtGui.QIcon(":/maestro/plugins/dbanalyzer/dbanalyzer.png")
    )
    

class DBAnalyzer(widgets.Widget):
    """This widget displays statistics about the database, finds errors in it and allows the user to
    correct them."""
    currentCheck = None # The check that is currently displayed in the details view.
    
    def __init__(self, state=None, **args):
        super().__init__(**args)
        layout = QtWidgets.QHBoxLayout(self)
        splitter = QtWidgets.QSplitter()
        layout.addWidget(splitter)
        leftWidget = QtWidgets.QWidget()
        leftLayout = QtWidgets.QVBoxLayout()
        leftLayout.setContentsMargins(0,0,0,0)
        leftWidget.setLayout(leftLayout)
        splitter.addWidget(leftWidget)
        rightWidget = QtWidgets.QWidget()
        rightLayout = QtWidgets.QVBoxLayout()
        rightLayout.setContentsMargins(0,0,0,0)
        rightWidget.setLayout(rightLayout)
        splitter.addWidget(rightWidget)

        # Statistics
        statisticsBox = QtWidgets.QGroupBox(self.tr("Statistics"))
        statisticsLayout = QtWidgets.QVBoxLayout()
        statisticsBox.setLayout(statisticsLayout)
        leftLayout.addWidget(statisticsBox,0)

        self.statisticsTable = QtWidgets.QTableWidget(1,2)
        self.statisticsTable.horizontalHeader().hide()
        self.statisticsTable.verticalHeader().hide()
        statisticsLayout.addWidget(self.statisticsTable)

        # Tags
        tagBox = QtWidgets.QGroupBox(self.tr("Tags"))
        tagLayout = QtWidgets.QVBoxLayout()
        tagBox.setLayout(tagLayout)
        leftLayout.addWidget(tagBox,1)

        self.tagTable = QtWidgets.QTableWidget(1,7)
        self.tagTable.verticalHeader().hide()
        tagLayout.addWidget(self.tagTable)

        # Problems
        problemsBox = QtWidgets.QGroupBox(self.tr("Problems"))
        problemsLayout = QtWidgets.QVBoxLayout()
        problemsBox.setLayout(problemsLayout)
        rightLayout.addWidget(problemsBox, 0)

        self.problemsTable = QtWidgets.QTableWidget(1, 2)
        self.problemsTable.verticalHeader().hide()
        self.problemsTable.cellClicked.connect(self._handleCellClicked)
        problemsLayout.addWidget(self.problemsTable)

        self.detailLabel = QtWidgets.QLabel()
        problemsLayout.addWidget(self.detailLabel)
        
        self.detailTable = QtWidgets.QTableWidget(0, 0)
        self.detailTable.verticalHeader().hide()
        problemsLayout.addWidget(self.detailTable)

        # Buttons
        buttonLayout = QtWidgets.QHBoxLayout()
        problemsLayout.addLayout(buttonLayout)
        self.fixButton = QtWidgets.QPushButton(utils.images.icon('edit-clear'), self.tr("Fix problem"))
        self.fixButton.setEnabled(False)
        self.fixButton.clicked.connect(self._handleFixButton)
        buttonLayout.addWidget(self.fixButton, 0)
        refreshButton = QtWidgets.QPushButton(utils.images.icon('view-refresh'), self.tr("Refresh"))
        refreshButton.clicked.connect(self.fetchData)
        buttonLayout.addWidget(refreshButton, 0)
        buttonLayout.addStretch(1)
        self.fetchData()
    
    def fetchData(self):
        """Forget all data and fetch it from the database."""
        # Clear
        self.statisticsTable.clear()
        self.tagTable.clear()
        self.problemsTable.clear()

        # Statistics
        statistics = self.getStatistics()
        self.statisticsTable.setRowCount(len(statistics))
        for i, tuple in enumerate(statistics):
            for j,data in enumerate(tuple):
                item = QtWidgets.QTableWidgetItem(str(data))
                item.setFlags(Qt.ItemIsEnabled)
                self.statisticsTable.setItem(i,j,item)
        self.statisticsTable.resizeColumnsToContents()

        # Tags
        tags = self.getTags()
        self.tagTable.setRowCount(len(tags))
        for i,header in enumerate(("id","tagname","tagtype","private",self.tr("Values"),self.tr("Refs"))):
            self.tagTable.setHorizontalHeaderItem(i,QtWidgets.QTableWidgetItem(header))
        for i,tuple in enumerate(tags):
            for j,data in enumerate(tuple):
                item = QtWidgets.QTableWidgetItem(str(data))
                item.setFlags(Qt.ItemIsEnabled)
                self.tagTable.setItem(i,j,item)
        self.tagTable.resizeColumnsToContents()

        # Problems
        self.checks = [checkClass() for checkClass in checks.Check.__subclasses__()]
        self.checks.sort(key=lambda check: check.getName())
        checkData = [(check.getName(),check.getInfo(),check.getNumber()) for check in self.checks]
        self.problemDetails = {}
        self.problemsTable.setRowCount(len(checkData))
        self.problemsTable.setHorizontalHeaderItem(0,QtWidgets.QTableWidgetItem(self.tr("Check")))
        self.problemsTable.setHorizontalHeaderItem(1,QtWidgets.QTableWidgetItem(self.tr("Broken")))
        for i,tuple in enumerate(checkData):
            name,info,number = tuple
            item = QtWidgets.QTableWidgetItem(name)
            # Use <qt> to enforce rich text handling so that QT automatically breaks lines
            item.setData(Qt.ToolTipRole,"<qt>{}</qt>".format(info))
            if number > 0:
                item.setIcon(QtGui.QIcon.fromTheme("dialog-warning"))
            item.setFlags(Qt.ItemIsEnabled)
            self.problemsTable.setItem(i,0,item)
            item = QtWidgets.QTableWidgetItem(str(number))
            item.setData(Qt.ToolTipRole,"<qt>{}</qt>".format(info))
            item.setFlags(Qt.ItemIsEnabled)
            self.problemsTable.setItem(i,1,item)
        self.problemsTable.resizeColumnsToContents()

        if self.currentCheck is None:
            # Show the first check with a nonzero number in details
            for check in self.checks:
                if check.getNumber() > 0:
                    self.loadDetails(check)
                    break
            else:
                # Everything is fine. Simply display the first check (disabled).
                self.loadDetails(self.checks[0])
        else: self.loadDetails(self.currentCheck)

    def _handleCellClicked(self,row,column):
        """Handle a click on a table cell in the problems table."""
        check = self.checks[row]
        self.loadDetails(check)

    def loadDetails(self,check):
        """Load details for the current check into the details table and label. Deactivate the table if there
        are no problems with the current check."""
        self.currentCheck = check
        self.fixButton.setEnabled(check.getNumber() > 0)

        # Format detail table header
        self.detailTable.clear()
        self.detailTable.setColumnCount(len(check._columnHeaders))
        for i,header in enumerate(check.getColumnHeaders()):
            self.detailTable.setHorizontalHeaderItem(i,QtWidgets.QTableWidgetItem(header))
        
        if check.getNumber() == 0:
            self.detailLabel.setText(self.tr("OK"))
            self.detailTable.setRowCount(0)
            self.detailTable.setEnabled(False)
        else:
            data = check.getData()
            self.detailLabel.setText(self.tr("Details for check '{}':").format(check.getName()))
            self.detailTable.setRowCount(len(data))
            self.detailTable.setEnabled(True)

            for i,tuple in enumerate(data):
                for j,content in enumerate(tuple):
                    item = QtWidgets.QTableWidgetItem(str(content))
                    item.setFlags(Qt.ItemIsEnabled)
                    self.detailTable.setItem(i,j,item)
        self.detailTable.resizeColumnsToContents()

    def _handleFixButton(self):
        """Fix the problems of the current check."""
        self.currentCheck.fix()
        self.fetchData()
        
    def getStatistics(self):
        """Gather and return the data for the statistics table."""
        length = db.query("SELECT SUM(length) FROM {}files".format(db.prefix)).getSingle()
        # SQL's SUM returns NULL if files is empty
        if length is None:
            length = 0
            
        return [
            (self.tr("Elements"), db.query("SELECT COUNT(*) FROM {}elements".format(db.prefix)).getSingle()),
            (self.tr("Files"), db.query("SELECT COUNT(*) FROM {}files".format(db.prefix)).getSingle()),
            (self.tr("Total Length"), utils.strings.formatLength(length)),
            (self.tr("Containers"),db.query(
                    "SELECT COUNT(*) FROM {}elements WHERE file = 0"
                    .format(db.prefix)).getSingle()),
            (self.tr("Toplevel elements"),db.query("""
                    SELECT COUNT(*)
                    FROM {0}elements AS el LEFT JOIN {0}contents AS c ON el.id = c.element_id
                    WHERE c.element_id IS NULL
                    """.format(db.prefix)).getSingle()),
            (self.tr("Toplevel files"),db.query("""
                    SELECT COUNT(*)
                    FROM {0}elements AS el LEFT JOIN {0}contents AS c ON el.id = c.element_id
                    WHERE el.file = 1 AND c.element_id IS NULL
                    """.format(db.prefix)).getSingle()),
            (self.tr("Content relations"),db.query(
                    "SELECT COUNT(*) FROM {}contents"
                        .format(db.prefix)).getSingle()),
            (self.tr("Tag relations"),db.query(
                    "SELECT COUNT(*) FROM {}tags"
                        .format(db.prefix)).getSingle()),
            (self.tr("Tracked new files"),db.query(
                    "SELECT COUNT(*) FROM {}newfiles"
                        .format(db.prefix)).getSingle()),
            ]

    def getTags(self):
        """Gather and return the data for the tags table."""
        tags = []
        result = db.query("SELECT id, tagname, tagtype, private FROM {}tagids ORDER BY id".format(db.prefix))
        for id,name,type,private in result:
            tuple = (id,name,type,private,
                db.query("SELECT COUNT(*) FROM {}values_{} WHERE tag_id={}"
                         .format(db.prefix,type,id)).getSingle(),
                db.query("SELECT COUNT(*) FROM {}tags WHERE tag_id={}"
                         .format(db.prefix,id)).getSingle()
             )
            tags.append(tuple)
        return(tags)

    def close(self):
        config.storage.dbanalyzer.size = (self.width(),self.height())
        config.storage.dbanalyzer.pos = (self.x(),self.y())
        QtWidgets.QDialog.close(self)


def _openDialog():
    """Open the DBAnalyzer as a dialog."""
    global _widget # store the widget in a variable or it will immediately destroyed
    _widget = DBAnalyzerDialog()
    _widget.show()
    
    
class DBAnalyzerDialog(QtWidgets.QDialog):
    """A dialog containing a DBAnalyzer."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Maestro version {} – Database Analyzer".format(VERSION))
        self.setWindowIcon(QtGui.QIcon(":/maestro/plugins/dbanalyzer/dbanalyzer.png"))
        layout = QtWidgets.QVBoxLayout(self)
        analyzer = DBAnalyzer(widgetClass=_getWidgetClass())
        layout.addWidget(analyzer)
        
        # TODO: use restoreGeometry
        screen = QtWidgets.QDesktopWidget().screenGeometry()
        size = QtCore.QSize(*config.storage.dbanalyzer.size)
        self.resize(size)
        pos = config.storage.dbanalyzer.pos
        if pos is None:
            self.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)
        else: self.move(*pos)


def run():
    """Run the DBAnalyzer as separate application."""
    app = application.init()
    config.getFile(config.storage).addSections(defaultStorage())
        
    _openDialog()
    returnValue = app.exec_()
    
    from maestro import logging
    config.shutdown()
    logging.shutdown()
    import sys
    sys.exit(returnValue)
    
    
if __name__ == "__main__":
    run()
    