# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

"""WTF - The write-to-filesystem plugin."""

import functools, os, os.path, shutil

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ... import utils, profiles, config, application, database as db, search, logging
from ...core import levels
from ...search import criteria

translate = QtCore.QCoreApplication.translate

_action = None # the action that is inserted into the Extras menu
_widget = None # the dialog widget must be stored in a variable or it will vanish immediately

profileCategory = None

STRUCTURE_KEEP, STRUCTURE_FLAT = range(2)

logger = logging.getLogger("wtf")


def enable():
    global _action, profileCategory
    profileCategory = profiles.ProfileCategory(
                            name = "wtf",
                            title = translate("wtf", "Export"),
                            storageOption = config.storageObject.wtf.profiles,
                            profileClass = Profile
                            )
    profiles.manager.addCategory(profileCategory)
    
    _action = QtGui.QAction(application.mainWindow)
    _action.setText(QtGui.QApplication.translate("wtf", "Export..."))
    _action.triggered[tuple()].connect(handleAction)
    
    
def mainWindowInit():
    application.mainWindow.menus['extras'].addAction(_action)


def disable():
    application.mainWindow.menus['extras'].removeAction(_action)
    profiles.manager.removeCategory(profileCategory)


def defaultStorage():
    return {"SECTION:wtf": {
            "size": (800,600),
            "pos": None, # Position of the window as tuple or None to center the window
            "profiles": {}
        }}


def handleAction():
    from ...gui.preferences import profiles as profilesgui
    dialog = profilesgui.ProfileActionDialog(profileCategory)
    dialog.setWindowTitle(translate("wtf", "Export"))
    if dialog.exec_() == QtGui.QDialog.Accepted:
        export(dialog.configWidget.getProfile())
    
    
class Profile(profiles.Profile):
    def __init__(self, name, type=None, state=None):
        super().__init__(name, type, state)
        self.filter = ''
        self.path = ''
        self.structure = STRUCTURE_KEEP
        self.delete = False
        self.read(state)
            
    def configurationWidget(self, parent):
        return ConfigWidget(self, parent)
    
    def save(self):
        return {'filter': self.filter,
                'path': self.path,
                'structure': self.structure,
                'delete': self.delete
                }
    
    def read(self, state):
        if state is not None:
            if 'filter' in state:
                self.filter = state['filter']
            if 'path' in state:
                self.path = state['path']
            if 'structure' in state:
                self.structure = state['structure']
            if 'delete' in state:
                self.delete = state['delete']
            
            
class CollapsingPanel(QtGui.QWidget):
    def __init__(self, title, widgetOrLayout, parent=None):
        super().__init__(parent)
        layout = QtGui.QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        groupBox = QtGui.QGroupBox(title)
        groupBox.setFlat(True)
        groupBox.setCheckable(True)
        groupBox.setChecked(True)
        layout.addWidget(groupBox)
        if isinstance(widgetOrLayout, QtGui.QWidget):
            widget = widgetOrLayout
        else:
            widget = QtGui.QWidget()
            widgetOrLayout.setContentsMargins(1,1,1,1)
            widget.setLayout(widgetOrLayout)
        self.widget = widget
        layout.addWidget(widget)
        groupBox.toggled.connect(self._toggle)
        
    def _toggle(self, checked):
        self.widget.setVisible(checked)
        self.updateGeometry()

    
class ConfigWidget(QtGui.QWidget):
    def __init__(self, profile, parent):
        super().__init__(parent)
        
        self.setLayout(QtGui.QVBoxLayout())
        self.layout().setContentsMargins(1,1,1,1)
        
        layout = QtGui.QVBoxLayout()
        lineLayout = QtGui.QHBoxLayout()
        layout.addLayout(lineLayout)
        lineLayout.addWidget(QtGui.QLabel(self.tr("Filter:")))
        lineLayout.addSpacing(QtGui.QApplication.style()
                              .pixelMetric(QtGui.QStyle.PM_LayoutHorizontalSpacing))
        lineLayout.setSpacing(0)
        self.filterLineEdit = QtGui.QLineEdit(profile.filter)
        self.filterLineEdit.editingFinished.connect(self._handleFilterEditingFinished)
        lineLayout.addWidget(self.filterLineEdit, 1)
        flagButton = QtGui.QPushButton()
        flagButton.setIcon(utils.getIcon("flag_blue.png"))
        flagButton.setSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        lineLayout.addWidget(flagButton)
        self.layout().addWidget(CollapsingPanel(self.tr("Choose elements to export"), layout))
        
        layout = QtGui.QFormLayout()
        lineLayout = QtGui.QHBoxLayout()
        self.pathLineEdit = QtGui.QLineEdit(profile.path)
        self.pathLineEdit.editingFinished.connect(self._handlePathEditingFinished)
        lineLayout.addWidget(self.pathLineEdit)
        pathChooserButton = QtGui.QPushButton()
        pathChooserButton.setIcon(QtGui.QApplication.style().standardIcon(QtGui.QStyle.SP_DirIcon))
        pathChooserButton.clicked.connect(self._handlePathChooserButton)
        lineLayout.addWidget(pathChooserButton)
        layout.addRow(self.tr("Path:"), lineLayout)
        self.structureBox = QtGui.QComboBox()
        self.structureBox.addItem(self.tr("Keep directory structure"), STRUCTURE_KEEP)
        self.structureBox.addItem(self.tr("Put all files into target directory"), STRUCTURE_FLAT)
        self.structureBox.setCurrentIndex(profile.structure)
        self.structureBox.currentIndexChanged.connect(self._handleStructureBox)
        layout.addRow(self.tr("Structure:"), self.structureBox)
        self.deleteBox = QtGui.QCheckBox(self.tr("Delete unexported files from target directory"))
        self.deleteBox.setChecked(profile.delete)
        self.deleteBox.toggled.connect(self._handleDeleteBox)
        layout.addRow(self.deleteBox)
        self.layout().addWidget(CollapsingPanel(self.tr("Export location"), layout))
        
        self.layout().addStretch(1)
        self.setProfile(profile)
        
    def getProfile(self):
        return self.profile
    
    def setProfile(self, profile):
        self.profile = profile
        self.filterLineEdit.setText(profile.filter)
        self.pathLineEdit.setText(profile.path)
        self.structureBox.setCurrentIndex(profile.structure)
        self.deleteBox.setChecked(profile.delete)
    
    def _handleFilterEditingFinished(self):
        self.profile.filter = self.filterLineEdit.text()
        
    def _handlePathEditingFinished(self):
        self.profile.path = self.pathLineEdit.text()
        
    def _handlePathChooserButton(self):
        """Handle the button next to the path field: Open a file dialog."""
        result = QtGui.QFileDialog.getExistingDirectory(self, self.tr("Choose export path"),
                                                        self.pathLineEdit.text())
        if result:
            self.pathLineEdit.setText(result)
            
    def _handleStructureBox(self, index):
        self.profile.structure = self.structureBox.itemData(index)
        
    def _handleDeleteBox(self, checked):
        self.profile.delete = checked
            

def export(profile):
    engine = search.SearchEngine()
    try:
        criterion = criteria.parse(profile.filter)
    except criteria.ParseException:
        QtGui.QMessageBox.warning(None, translate("wtf", "Invalid criterion"),
                                  translate("wtf", "The given filter criterion is invalid"))
        return
    
    request = engine.searchAndBlock(db.prefix+"elements", criterion)
    print("Found {} elements for export".format(len(request.result)))
    if len(request.result) == 0:
        QtGui.QMessageBox.warning(None, translate("wft", "No elements found"),
                                translate("wtf", "The given filter criterion does not match any elements."))
        return
    
    exported = set()
    if profile.structure == STRUCTURE_FLAT:
        exportedPaths = set()
    toExport = levels.real.collectMany(request.result)
    while len(toExport) > 0:
        element = toExport.pop()
        if element.id in exported:
            continue
        exported.add(element.id)
        if element.isContainer():
            toExport.extend(levels.real.collectMany(element.contents))
            continue
        if element.url.scheme != 'file':
            print("I can only export regular files. Skipping", str(element.url))
            continue
        
        if profile.structure == STRUCTURE_FLAT:
            exportPath = os.path.basename(element.url.path)
            if exportPath in exportedPaths:
                # TODO mv path.mp3 to path-1.mp3
                exportPath, ext = os.path.splitext(exportPath)
                i = 1
                while exportPath+"-" + str(i) + ext in exportedPaths:
                    i += 1
                exportPath += "-" + str(i) + ext 
            assert exportPath not in exportedPaths
            exportedPaths.add(exportPath)
        else:
            exportPath = element.url.path
        
        src = os.path.join(config.options.main.collection, element.url.path)
        dest = os.path.join(profile.path, exportPath)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(src, dest)
        