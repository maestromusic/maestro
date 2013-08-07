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

from PyQt4 import QtCore, QtGui

from omg.gui import mainwindow
from omg.gui.treeactions import TreeAction
from omg.gui.dialogs import warning 

class ImportAudioCDAction(TreeAction):
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr('load audio CD'))
        
    def doAction(self):
        import discid
        with discid.read() as disc:
            try:
                disc.read()
            except discid.disc.DiscError:
                warning(self.tr("CDROM drive is empty"))
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
        self.level().stack.beginMacro(self.tr("Load CDROM"))
        container = xmlapi.makeReleaseContainer(release, theDiscid, self.level())
        model = self.parent().model()
        root = model.root
        model.insertElements(model.root, len(root.contents), [container])
        self.level().stack.endMacro()
        
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