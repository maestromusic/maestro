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

from omg.gui.dockwidget import DockWidget
from omg.gui import mainwindow
from omg.gui.dialogs import warning
from omg.gui.treeview import TreeView
from omg.models.leveltreemodel import LevelTreeModel
from omg.core import levels
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


class ReleaseSelectionDialog(QtGui.QDialog):
    
    def __init__(self, releases, discid):
        super().__init__(mainwindow.mainWindow)
        self.setModal(True)
        self.listW = QtGui.QListWidget()
        self.listW.setAlternatingRowColors(True)
        lay = QtGui.QVBoxLayout()
        for release in releases:
            text = ""
            if len(release.children) > 1:
                text = "[Disc {} of {} in] ".format(release.mediumForDiscid(discid),
                                                   len(release.children))
            text += release.tags["title"][0] + "\nby {}".format(release.tags["artist"][0])
            if "date" in release.tags:
                text += "\nreleased {}".format(release.tags["date"][0])
                if "country" in release.tags:
                    text += " ({})".format(release.tags["country"][0])
                if "barcode" in release.tags:
                    text +=", barcode={}".format(release.tags["barcode"][0])
            but = QtGui.QPushButton(text)
            but.setStyleSheet("text-align: left")
            but.clicked.connect(lambda : self._handleClick(release))
            lay.addWidget(but)
        #lay.addWidget(self.listW)
        btbx = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel)
        btbx.rejected.connect(self.reject)
        lay.addWidget(btbx)
        self.setLayout(lay)
    
    def _handleClick(self, release):
        self.selectedRelease = release
        self.accept()


class CDROMDock(DockWidget):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.setWindowTitle(self.tr('CD-ROM'))
        self.combo = QtGui.QComboBox()
        self.combo.addItems(drives)
        
        check = QtGui.QPushButton(self.tr("check drive"))
        check.clicked.connect(self.checkDrive)
        widget = QtGui.QWidget()
        layout = QtGui.QVBoxLayout()
        
        self.model = LevelTreeModel(levels.editor)
        self.tree = TreeView(levels.editor, affectGlobalSelection=False)
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
        QtGui.qApp.processEvents()
        with discid.read() as disc:
            try:
                disc.read(drive)
            except discid.disc.DiscError:
                warning("No disc found")
                return False
            theDiscid = disc.id
        from omg.plugins.musicbrainz import xmlapi
        releases = xmlapi.findReleasesForDiscid(theDiscid)
        if len(releases) > 1:
            dialog = ReleaseSelectionDialog(releases, theDiscid)
            if dialog.exec_():
                release = dialog.selectedRelease
            else:
                return
            
        container = xmlapi.makeReleaseContainer(release, theDiscid, levels.editor)
        self.model._insertContents(QtCore.QModelIndex(), 0, [container.id])

        
wData = mainwindow.WidgetData(id="cdrom", name=translate("CD-ROM","cdrom"),
                              theClass=CDROMDock, central=False, dock=True, unique=False,
                              preferredDockArea=Qt.RightDockWidgetArea)
