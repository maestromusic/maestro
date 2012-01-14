# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

class IconChooser(QtGui.QDialog):
    
    maxCols = 10
    iconSize = 32
    def __init__(self, defaultPaths, parent = None):
        super().__init__(parent)
        
        layout = QtGui.QVBoxLayout()
        icons = []
        for path in defaultPaths:
            for file in QtCore.QDir(path).entryInfoList(filters=QtCore.QDir.Files):
                try:
                    icon = QtGui.QIcon(file.canonicalFilePath())
                    icons.append( (icon, file) )
                except Exception as e:
                    print(e)
        self.table = QtGui.QTableWidget(self)
        self.table.setColumnCount(min(self.maxCols, len(icons)))
        self.table.setRowCount( (len(icons)-1) // self.maxCols + 1)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setIconSize(QtCore.QSize(self.iconSize, self.iconSize))
        self.table.doubleClicked.connect(self.accept)
        self.row = self.col = 0
        for icon, file in icons:
            item = QtGui.QTableWidgetItem(icon, "")
            item.setData(Qt.UserRole, file.canonicalFilePath())
            item.setToolTip(file.baseName())
            self.addItem(item)
                
        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()
        layout.addWidget(self.table)
        
        buttonBox = QtGui.QHBoxLayout()
        
        addButton = QtGui.QPushButton(self.tr("Add..."))
        cancelButton = QtGui.QPushButton(self.tr("Cancel"))
        okButton = QtGui.QPushButton(self.tr("Ok"))
        
        buttonBox.addWidget(addButton)
        buttonBox.addStretch()
        buttonBox.addWidget(cancelButton)
        buttonBox.addWidget(okButton)
        cancelButton.clicked.connect(self.reject)
        okButton.clicked.connect(self.accept)
        addButton.clicked.connect(self.handleAdd)
        layout.addLayout(buttonBox)
        self.setLayout(layout)
        self.resize(320, 350)
    
    @staticmethod
    def getIcon(defaultPaths, parent = None):
        chooser = IconChooser(defaultPaths, parent)
        if chooser.exec_() == QtGui.QDialog.Accepted:
            item = chooser.table.currentItem()
            return (item.data(Qt.DecorationRole), item.data(Qt.UserRole))
        else:
            return None
        
    def addItem(self, item):
        self.table.setItem(self.row, self.col, item)
        if self.col < self.maxCols - 1:
            self.col += 1
        else:
            self.col = 0
            self.row += 1
                
    def handleAdd(self):
        fileName = QtGui.QFileDialog.getOpenFileName(self,self.tr("Choose flag icon"),
                                                     filter = self.tr("Images (*.png *.xpm *.jpg)"))
        if fileName:
            icon = QtGui.QIcon(fileName)
            item = QtGui.QTableWidgetItem(icon, "")
            item.setData(Qt.UserRole, fileName)
            item.setToolTip(fileName)
            self.addItem(item)