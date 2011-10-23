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

from PyQt4 import QtGui, QtCore
import os
from .. import config, database as db
from . import mainwindow
from ..utils import relPath

"""This module contains a dock widget that displays the music in directory view, i.e. without
considering the container structure in the database. It is meant to help building up the database.
Folders which contain music files that are not yet present in the database are marked with a
special icon."""

translate = QtCore.QCoreApplication.translate

class IconProvider(QtGui.QFileIconProvider):
    
    def __init__(self):
        super().__init__()
        self.dirtyFolderIcon = QtGui.QIcon("images/icons/folder_unknown.svg")
        self.musicFolderIcon = QtGui.QIcon("images/icons/folder_ok.svg")
        self.defaultFolderIcon = QtGui.QIcon("images/icons/folder.svg")
    
    def icon(self, arg):
        if os.path.isdir(arg.absoluteFilePath()):
            path = arg.absoluteFilePath()
            dir = relPath(arg.canonicalFilePath())
            if dir == '..':
                return super().icon(arg)
            stati = set(db.query('''SELECT state FROM {}folders WHERE path = ? OR path LIKE CONCAT(?, "/%")
            GROUP BY state'''.format(db.prefix),
                             dir, dir).getSingleColumn())
            if 'unsynced' in stati:
                return self.dirtyFolderIcon
            elif 'ok' in stati:
                return self.musicFolderIcon
            else:
                return self.defaultFolderIcon
        return super().icon(arg)  
        

class FileSystemBrowserModel(QtGui.QFileSystemModel):
    
    def __init__(self, parent = None):
        QtGui.QFileSystemModel.__init__(self, parent)
        self.setFilter(QtCore.QDir.AllEntries | QtCore.QDir.NoDotAndDotDot)
       
        self.setIconProvider(IconProvider())

    def columnCount(self, index):
        return 1
                
        
class FileSystemBrowser(QtGui.QTreeView):
    
    def __init__(self, rootDirectory = config.options.main.collection, parent = None):
        QtGui.QTreeView.__init__(self, parent)
        self.setAlternatingRowColors(True)
        self.setModel(FileSystemBrowserModel())
        musikindex = self.model().setRootPath(rootDirectory)
        self.setRootIndex(musikindex)
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragDropMode(QtGui.QAbstractItemView.DragOnly)

class FileSystemBrowserDock(QtGui.QDockWidget):
    """A DockWidget wrapper for the FileSystemBrowser."""
    def __init__(self,parent=None,location=None):
        QtGui.QDockWidget.__init__(self, parent)
        self.setWindowTitle(translate("FileSystemBrowser","File System Browser"))
        self.setWidget(FileSystemBrowser())
        
        
# register this widget in the main application
data = mainwindow.WidgetData(id = "filesystembrowser",
                             name = translate("FileSystemBrowser","File System Browser"),
                             theClass = FileSystemBrowserDock,
                             central = False,
                             dock = True,
                             default = True,
                             unique = False,
                             preferredDockArea = QtCore.Qt.RightDockWidgetArea)
mainwindow.addWidgetData(data)
