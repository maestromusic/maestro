# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2013 Martin Altmayer, Michael Helmling
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

import subprocess

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg.gui.mainwindow import DockWidget, WidgetData
from omg.gui import mainwindow
from omg.gui.dialogs import warning
from omg.gui.treeview import TreeView
from omg.models.leveltreemodel import LevelTreeModel
from omg.core import levels, tags
from omg.gui import delegates
from omg import filebackends

translate = QtCore.QCoreApplication.translate

drives = None

def enable():
    global drives
    drives = findDrives()
    mainwindow.addWidgetData(wData)
    from . import filebackend as cdfilebackend
    filebackends.urlTypes["audiocd"] = cdfilebackend.AudioCDURL

def disable():
    mainwindow.removeWidgetData(wData)
    filebackends.urlTypes["audiocd"]

def findDrives():
    output = subprocess.check_output("cd-drive")
    drives = []
    for line in output.decode().splitlines():
        if line.startswith("                       Drive: "):
            drives.append(line[30:])
    return drives

class CDROMDelegate(delegates.StandardDelegate):

    def __init__(self, view): 
        # Because it should not be configurable, this profile is not contained in the profile category
        self.profile = delegates.profiles.DelegateProfile("cdrom")
        super().__init__(view, self.profile)


class CDROMDock(DockWidget):
    def __init__(self, parent=None, state=None, location=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('CD-ROM'))
        self.combo = QtGui.QComboBox()
        self.combo.addItems(drives)
        
        check = QtGui.QPushButton(self.tr("check drive"))
        check.clicked.connect(self.checkDrive)
        widget = QtGui.QWidget()
        layout = QtGui.QVBoxLayout()
        
        self.level = levels.Level(name="CDROM", parent=levels.editor)
        self.model = LevelTreeModel(self.level)
        self.tree = TreeView(self.level, affectGlobalSelection=False)
        self.tree.setModel(self.model)
        self.tree.setItemDelegate(CDROMDelegate(self.tree))
        
        layout.addWidget(self.combo)
        layout.addWidget(self.tree)
        layout.addWidget(check)
        widget.setLayout(layout)
        self.setWidget(widget)
        
    def checkDrive(self):
        drive = self.combo.currentText()
        import discid
        progress = QtGui.QProgressDialog(mainwindow.mainWindow)
        progress.setLabelText("reading disc ...")
        progress.setWindowModality(Qt.WindowModal)
        progress.setRange(0,2)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QtGui.qApp.processEvents()
        with discid.read() as disc:
            try:
                disc.read(drive)
            except discid.disc.DiscError:
                warning("No disc found")
                return False
            discid = disc.id
        progress.setLabelText("Looking up disc id ...")
        progress.setValue(1)
        from omg.plugins.musicbrainz import xmlapi
        containers = xmlapi.makeReleaseTree(discid, self.level)
        print(containers)
        self.model._insertContents(QtCore.QModelIndex(), 0, containers)
        progress.reset()
        
wData = WidgetData(id="cdrom", name=translate("CD-ROM","cdrom"), theClass=CDROMDock,
                   central=False, dock=True, default=False, unique=False,
                   preferredDockArea=Qt.RightDockWidgetArea)
