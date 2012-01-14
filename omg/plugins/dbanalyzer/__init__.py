# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg import database as db, application, constants, config, utils, tags as tagsModule
from omg.gui import mainwindow

# don't use relative import since this file may be executed directly and is not a package in that case.
from . import resources, checks

_action = None # the action that is inserted into the Extras menu
_widget = None # the dialog widget must be stored in a variable or it will vanish immediately


# The next few (undocumented) functions are called by the plugin system
def enable():
    global _action
    _action = QtGui.QAction(application.mainWindow)
    _action.setText(QtGui.QApplication.translate("DBAnalyzerDialog","DB Analyzer"))
    _action.triggered.connect(_openDialog)
    mainwindow.addWidgetData(mainwindow.WidgetData(
        "dbanalyzer",QtGui.QApplication.translate("DBAnalyzerDialog","DB Analyzer"),DBAnalyzerDialog,
        True,False,False,
        icon=QtGui.QIcon(":/omg/plugins/dbanalyzer/dbanalyzer.png")))


def mainWindowInit():
    application.mainWindow.menus['extras'].addAction(_action)


def disable():
    application.mainWindow.menus['extras'].removeAction(_action)
    mainwindow.removeWidgetData("dbanalyzer")


def defaultStorage():
    return {"dbanalyzer": {
            "size": ((800,600),"Size of the window."),
            "pos": (None,"Position of the window as tuple or None to center the window")
        }}


def _openDialog():
    """Open the DBAnalyzer as a dialog."""
    global _widget # store the widget in a variable or it will immediately destroyed
    _widget = DBAnalyzerDialog(dialog=True)
    _widget.setWindowTitle("OMG version {} – Database Analyzer".format(constants.VERSION))
    _widget.setWindowIcon(utils.getIcon("dbanalyzer.png","dbanalyzer"))

    # TODO: use restoreGeometry
    screen = QtGui.QDesktopWidget().screenGeometry()
    size = QtCore.QSize(*config.storage.dbanalyzer.size)
    _widget.resize(size)
    pos = config.storage.dbanalyzer.pos
    if pos is None:
        _widget.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)
    else: _widget.move(*pos)
    _widget.show()


class DBAnalyzerDialog(QtGui.QDialog):
    """A dialog that displays statistics about the database, finds errors in it and allows the user to correct them."""
    currentCheck = None # The check that is currently displayed in the details view.
    
    def __init__(self,parent=None,dialog=False):
        QtGui.QDialog.__init__(self,parent)
        self.setLayout(QtGui.QHBoxLayout())
        splitter = QtGui.QSplitter()
        self.layout().addWidget(splitter)
        leftWidget = QtGui.QWidget()
        leftLayout = QtGui.QVBoxLayout()
        leftLayout.setContentsMargins(0,0,0,0)
        leftWidget.setLayout(leftLayout)
        splitter.addWidget(leftWidget)
        rightWidget = QtGui.QWidget()
        rightLayout = QtGui.QVBoxLayout()
        rightLayout.setContentsMargins(0,0,0,0)
        rightWidget.setLayout(rightLayout)
        splitter.addWidget(rightWidget)

        # Statistics
        statisticsBox = QtGui.QGroupBox(self.tr("Statistics"))
        statisticsLayout = QtGui.QVBoxLayout()
        statisticsBox.setLayout(statisticsLayout)
        leftLayout.addWidget(statisticsBox,0)

        self.statisticsTable = QtGui.QTableWidget(1,2)
        self.statisticsTable.horizontalHeader().hide()
        self.statisticsTable.verticalHeader().hide()
        statisticsLayout.addWidget(self.statisticsTable)

        # Tags
        tagBox = QtGui.QGroupBox(self.tr("Tags"))
        tagLayout = QtGui.QVBoxLayout()
        tagBox.setLayout(tagLayout)
        leftLayout.addWidget(tagBox,1)

        self.tagTable = QtGui.QTableWidget(1,7)
        self.tagTable.verticalHeader().hide()
        tagLayout.addWidget(self.tagTable)

        # Problems
        problemsBox = QtGui.QGroupBox(self.tr("Problems"))
        problemsLayout = QtGui.QVBoxLayout()
        problemsBox.setLayout(problemsLayout)
        rightLayout.addWidget(problemsBox,0)

        self.problemsTable = QtGui.QTableWidget(1,2)
        self.problemsTable.verticalHeader().hide()
        self.problemsTable.cellClicked.connect(self._handleCellClicked)
        problemsLayout.addWidget(self.problemsTable)

        self.detailLabel = QtGui.QLabel()
        problemsLayout.addWidget(self.detailLabel)
        
        self.detailTable = QtGui.QTableWidget(0,0)
        self.detailTable.verticalHeader().hide()
        problemsLayout.addWidget(self.detailTable)

        # Buttons
        buttonLayout = QtGui.QHBoxLayout()
        problemsLayout.addLayout(buttonLayout)
        self.fixButton = QtGui.QPushButton(utils.getIcon("edit-clear.png"),self.tr("Fix problem"))
        self.fixButton.setEnabled(False)
        self.fixButton.clicked.connect(self._handleFixButton)
        buttonLayout.addWidget(self.fixButton,0)
        refreshButton = QtGui.QPushButton(QtGui.QIcon.fromTheme('view-refresh'),self.tr("Refresh"))
        refreshButton.clicked.connect(self.fetchData)
        buttonLayout.addWidget(refreshButton,0)
        
        buttonLayout.addStretch(1)
        if dialog:
            closeButton = QtGui.QPushButton(QtGui.QIcon.fromTheme('window-close'),self.tr("Close"))
            closeButton.clicked.connect(self.close)
            buttonLayout.addWidget(closeButton,0)

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
        for i,tuple in enumerate(statistics):
            for j,data in enumerate(tuple):
                item = QtGui.QTableWidgetItem(str(data))
                item.setFlags(Qt.ItemIsEnabled)
                self.statisticsTable.setItem(i,j,item)
        self.statisticsTable.resizeColumnsToContents()

        # Tags
        tags = self.getTags()
        self.tagTable.setRowCount(len(tags))
        for i,header in enumerate(("id","tagname","tagtype","sorttags","private",
                                   self.tr("Values"),self.tr("Refs"))):
            self.tagTable.setHorizontalHeaderItem(i,QtGui.QTableWidgetItem(header))
        for i,tuple in enumerate(tags):
            for j,data in enumerate(tuple):
                item = QtGui.QTableWidgetItem(str(data))
                item.setFlags(Qt.ItemIsEnabled)
                self.tagTable.setItem(i,j,item)
        self.tagTable.resizeColumnsToContents()

        # Problems
        self.checks = [checkClass() for checkClass in checks.Check.__subclasses__()]
        checkData = [(check.getName(),check.getInfo(),check.getNumber()) for check in self.checks]
        self.problemDetails = {}
        self.problemsTable.setRowCount(len(checkData))
        self.problemsTable.setHorizontalHeaderItem(0,QtGui.QTableWidgetItem(self.tr("Check")))
        self.problemsTable.setHorizontalHeaderItem(1,QtGui.QTableWidgetItem(self.tr("Broken")))
        for i,tuple in enumerate(checkData):
            name,info,number = tuple
            item = QtGui.QTableWidgetItem(name)
            # Use <qt> to enforce rich text handling so that QT automatically breaks lines
            item.setData(Qt.ToolTipRole,"<qt>{}</qt>".format(info))
            if number > 0:
                item.setIcon(QtGui.QIcon.fromTheme("dialog-warning"))
            item.setFlags(Qt.ItemIsEnabled)
            self.problemsTable.setItem(i,0,item)
            item = QtGui.QTableWidgetItem(str(number))
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
            else: self.loadDetails(self.checks[0]) # Everything is fine. Simply display the first check (disabled).
        else: self.loadDetails(self.currentCheck)

    def _handleCellClicked(self,row,column):
        """Handle a click on a table cell in the problems table."""
        check = self.checks[row]
        self.loadDetails(check)

    def loadDetails(self,check):
        """Load details for the current check into the details table and label. Deactivate the table if there are no problems with the current check."""
        self.currentCheck = check
        self.fixButton.setEnabled(check.getNumber() > 0)

        # Format detail table header
        self.detailTable.clear()
        self.detailTable.setColumnCount(len(check._columnHeaders))
        for i,header in enumerate(check.getColumnHeaders()):
            self.detailTable.setHorizontalHeaderItem(i,QtGui.QTableWidgetItem(header))
        
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
                    item = QtGui.QTableWidgetItem(str(content))
                    item.setFlags(Qt.ItemIsEnabled)
                    self.detailTable.setItem(i,j,item)
        self.detailTable.resizeColumnsToContents()

    def _handleFixButton(self):
        """Fix the problems of the current check."""
        self.currentCheck.fix()
        self.fetchData()
        
    def getStatistics(self):
        """Gather and return the data for the statistics table."""
        return [
            (self.tr("Elements"),db.query(
                    "SELECT COUNT(*) FROM {}elements"
                        .format(db.prefix)).getSingle()),
            (self.tr("Files"),db.query(
                    "SELECT COUNT(*) FROM {}files"
                        .format(db.prefix)).getSingle()),
            (self.tr("Containers"),db.query(
                    "SELECT COUNT(*) FROM {}elements WHERE file = 0"
                        .format(db.prefix)).getSingle()),
            (self.tr("Toplevel elements"),db.query(
                    "SELECT COUNT(*) FROM {}elements WHERE toplevel = 1"
                        .format(db.prefix)).getSingle()),
            (self.tr("Content relations"),db.query(
                    "SELECT COUNT(*) FROM {}contents"
                        .format(db.prefix)).getSingle()),
            (self.tr("Tag relations"),db.query(
                    "SELECT COUNT(*) FROM {}tags"
                        .format(db.prefix)).getSingle())
            ]

    def getTags(self):
        """Gather and return the data for the tags table."""
        tags = []
        result = db.query("SELECT id,tagname,tagtype,sorttags,private FROM {}tagids ORDER BY id".format(db.prefix))
        for id,name,type,sort,private in result:
            sortTags = []
            if len(sort) > 0:
                for sortId in sort.split(','):
                    try:
                        sortTags.append(db.query("SELECT tagname FROM {}tagids WHERE id = {}"
                                                   .format(db.prefix,sortId)).getSingle())
                    except db.sql.EmptyResultException:
                        sortTags.append('{} (INVALID!)'.format(sortId))
            sortTags = ", ".join(sortTags) 
                        
            tuple = (id,name,type,sortTags,private,
                db.query("SELECT COUNT(*) FROM {}values_{} WHERE tag_id={}".format(db.prefix,type,id)).getSingle(),
                db.query("SELECT COUNT(*) FROM {}tags WHERE tag_id={}".format(db.prefix,id)).getSingle()
             )
            tags.append(tuple)
        return(tags)

    def close(self):
        config.storage.dbanalyzer.size = (self.width(),self.height())
        config.storage.dbanalyzer.pos = (self.x(),self.y())
        QtGui.QDialog.close(self)


if __name__ == "__main__":
    app = application.init()
    config.storageObject.loadPlugins(defaultStorage())
         
    _openDialog()
    returnValue = app.exec_()
    
    config.storageObject.write()
    from omg import logging
    logging.shutdown()
    import sys
    sys.exit(returnValue)
