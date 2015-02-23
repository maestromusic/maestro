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

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt


class IconChooser(QtWidgets.QDialog):
    """Lets the user choose an icon from a list or using a file dialog to choose an arbitrary icon. *folders*
    is a list of directory paths. The dialog will display all files in these directories. If *defaultPath*
    is the path of a displayed icon, it will be selected.
    """
    def __init__(self, folders, defaultPath, parent = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Choose an icon"))
        
        layout = QtWidgets.QVBoxLayout(self)
        icons = []
        for path in folders:
            for file in QtCore.QDir(path).entryInfoList(filters=QtCore.QDir.Files):
                icon = QtGui.QIcon(file.canonicalFilePath())
                icons.append( (icon, file) )
        self.view = QtWidgets.QListWidget(self)
        self.view.setViewMode(QtWidgets.QListView.IconMode)
        self.view.doubleClicked.connect(self.accept)
       
        self.row = self.col = 0
        if defaultPath is not None:
            defaultFile = QtCore.QFileInfo(defaultPath)
        else: defaultFile = None
        for icon, file in icons:
            item = QtWidgets.QListWidgetItem(icon,'')
            item.setData(Qt.UserRole, file.canonicalFilePath())
            item.setToolTip(file.baseName())
            self.view.addItem(item)
            if file == defaultFile:
                self.view.setItemSelected(item,True)
                self.view.setCurrentItem(item)
                
        layout.addWidget(self.view)
        buttonBox = QtWidgets.QDialogButtonBox()
        layout.addWidget(buttonBox)
        
        addButton = QtWidgets.QPushButton(self.tr("Add..."))
        addButton.clicked.connect(self._handleAdd)
        buttonBox.addButton(addButton,QtWidgets.QDialogButtonBox.ActionRole)
        cancelButton = buttonBox.addButton(QtWidgets.QDialogButtonBox.Cancel)
        cancelButton.clicked.connect(self.reject)
        okButton = buttonBox.addButton(QtWidgets.QDialogButtonBox.Ok)
        okButton.clicked.connect(self.accept)
        
        self.resize(320, 350)
    
    @staticmethod
    def getIcon(folders,defaultPath,parent = None):
        """Let the user choose an icon using an IconChooser dialog. Return the icon and its path if the user
        selected an icon. Return None otherwise."""
        chooser = IconChooser(folders,defaultPath,parent)
        if chooser.exec_() == QtWidgets.QDialog.Accepted:
            item = chooser.view.currentItem()
            return (item.data(Qt.DecorationRole), item.data(Qt.UserRole))
        else: return None
                
    def _handleAdd(self):
        """Handle clicks on the add button: Open a file dialog."""
        fileName = QtGui.QFileDialog.getOpenFileName(self,self.tr("Choose an icon"),
                                                     filter = self.tr("Images (*.png *.xpm *.jpg)"))
        if fileName:
            icon = QtGui.QIcon(fileName)
            item = QtWidgets.QListWidgetItem(icon,'')
            item.setData(Qt.UserRole, fileName)
            item.setToolTip(fileName)
            self.view.addItem(item)
            