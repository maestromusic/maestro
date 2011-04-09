# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

import types

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg import getIcon,database

# don't use relative import since this file may be executed directly and is not a package in that case.
from omg.plugins.dbanalyzer import checks

def storage():
    return {"dbanalyzer": {
            "width": (800,"Width of the window."),
            "height": (600,"Height of the window."),
            "pos_x": (None,"X-Pos of the window."),
            "pos_y": (None,"Y-Pos of the window.")
        }}


class DBAnalyzerDialog(QtGui.QDialog):
    """A dialog that displays statistics about the database, finds errors in it and allows the user to correct them."""
    currentCheck = None # The check that is currently displayed in the details view.
    
    def __init__(self,parent=None):
        QtGui.QDialog.__init__(self,parent)
        self.setLayout(QtGui.QHBoxLayout())
        leftLayout = QtGui.QVBoxLayout()
        rightLayout = QtGui.QVBoxLayout()
        self.layout().addLayout(leftLayout,0)
        self.layout().addLayout(rightLayout,1)

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

        self.tagTable = QtGui.QTableWidget(1,5)
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
        fixButton = QtGui.QPushButton(getIcon("edit-clear.png"),self.tr("Fix problem"))
        fixButton.clicked.connect(self._handleFixButton)
        buttonLayout.addWidget(fixButton,0)
        buttonLayout.addStretch(1)
        closeButton = QtGui.QPushButton(QtGui.QIcon.fromTheme('window-close'),self.tr("Close"))
        closeButton.clicked.connect(self.close)
        buttonLayout.addWidget(closeButton,0)
        
    def fetchData(self):
        """Forget all data and fetch it from the database."""
        global db, prefix
        db = database.get()
        prefix = database.prefix

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
        for i,header in enumerate((self.tr("ID"),self.tr("Name"),self.tr("Type"),self.tr("Values"),self.tr("Refs"))):
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
                        .format(prefix)).getSingle()),
            (self.tr("Files"),db.query(
                    "SELECT COUNT(*) FROM {}files"
                        .format(prefix)).getSingle()),
            (self.tr("Containers"),db.query(
                    "SELECT COUNT(*) FROM {}elements WHERE file = 0"
                        .format(prefix)).getSingle()),
            (self.tr("Toplevel elements"),db.query(
                    "SELECT COUNT(*) FROM {}elements WHERE toplevel = 1"
                        .format(prefix)).getSingle()),
            (self.tr("Content relations"),db.query(
                    "SELECT COUNT(*) FROM {}contents"
                        .format(prefix)).getSingle()),
            (self.tr("Tag relations"),db.query(
                    "SELECT COUNT(*) FROM {}tags"
                        .format(prefix)).getSingle())
            ]

    def getTags(self):
        """Gather and return the data for the tags table."""
        tags = []
        result = db.query("SELECT id,tagname,tagtype FROM {}tagids ORDER BY id".format(prefix))
        for id,name,type in result:
            tuple = (id,name,type,
                db.query("SELECT COUNT(*) FROM {}values_{} WHERE tag_id={}".format(prefix,type,id)).getSingle(),
                db.query("SELECT COUNT(*) FROM {}tags WHERE tag_id={}".format(prefix,id)).getSingle()
             )
            tags.append(tuple)
        return(tags)


if __name__ == "__main__":
    import sys, os

    # Switch to the application's directory (three levels above this file's directory)
    if os.path.dirname(__file__):
        os.chdir(os.path.dirname(__file__))
    os.chdir("../../../")

    from omg import constants, config, logging, tags
    config.init()
    config.storageObject.loadPlugins(storage())
    logging.init()
    database.connect()
    tags.init()
    
    app = QtGui.QApplication(sys.argv)
        
    widget = DBAnalyzerDialog()
    widget.setWindowTitle("OMG version {} – Database Analyzer".format(constants.VERSION))

    screen = QtGui.QDesktopWidget().screenGeometry()
    size =  QtCore.QSize(config.storage.dbanalyzer.width,config.storage.dbanalyzer.height)
    widget.resize(size)
    x = config.storage.dbanalyzer.pos_x
    y = config.storage.dbanalyzer.pos_y
    if x is None or y is None:
        widget.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)
    else: widget.move(x,y)
    widget.show()

    widget.fetchData()

    returnValue = app.exec_()

    config.storage.dbanalyzer.width = widget.width()
    config.storage.dbanalyzer.height = widget.height()
    config.storage.dbanalyzer.pos_x = widget.x()
    config.storage.dbanalyzer.pos_y = widget.y()
    config.storageObject.write()
    sys.exit(returnValue)
