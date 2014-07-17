# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

import functools, os, os.path, shutil, copy, itertools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from ... import utils, profiles, config, application, database as db, search, logging
from ...core import levels
from ...gui import search as searchgui, dialogs
from ...gui.misc import collapsiblepanel
from ...gui.preferences import profiles as profilesgui
from ...search import criteria


_action = None # the action that is inserted into the Extras menu
_widget = None # the dialog widget must be stored in a variable or it will vanish immediately

profileCategory = None

STRUCTURE_KEEP, STRUCTURE_FLAT = range(2)


def enable():
    global _action, profileCategory
    profileCategory = profiles.ProfileCategory(
                            name = "wtf",
                            title = translate("wtf", "Export"),
                            storageOption = config.getOption(config.storage, 'wtf.profiles'),
                            profileClass = Profile
                            )
    profiles.manager.addCategory(profileCategory)
    
    _action = QtGui.QAction(application.mainWindow)
    _action.setText(QtGui.QApplication.translate("wtf", "Export..."))
    _action.triggered[tuple()].connect(Dialog.execute)
    global _sqlAction
    _sqlAction = QtGui.QAction(application.mainWindow)
    _sqlAction.setText("Export SQLite...")
    _sqlAction.triggered.connect(exportSQLite)
    
    
def mainWindowInit():
    application.mainWindow.menus['extras'].addAction(_action)
    application.mainWindow.menus['extras'].addAction(_sqlAction)


def disable():
    application.mainWindow.menus['extras'].removeAction(_action)
    profiles.manager.removeCategory(profileCategory)


def defaultStorage():
    return {"wtf": {
            "size": (800,600),
            "pos": None, # Position of the window as tuple or None to center the window
            "profiles": ({},),
        }}


class Profile(profiles.Profile):
    def __init__(self, name, type=None, state=None):
        super().__init__(name, type, state)
        self.criterion = None
        self.path = ''
        self.structure = STRUCTURE_KEEP
        self.delete = False
        self.read(state)
            
    def configurationWidget(self, parent):
        return ConfigWidget(self, parent)
    
    def save(self):
        return {'criterion': repr(self.criterion),
                'path': self.path,
                'structure': self.structure,
                'delete': self.delete
                }
    
    def read(self, state):
        if state is not None:
            if 'criterion' in state:
                try:
                    self.criterion = criteria.parse(state['criterion'])
                except criteria.ParseException:
                    pass
            if 'path' in state:
                self.path = state['path']
            if 'structure' in state:
                self.structure = state['structure']
            if 'delete' in state:
                self.delete = state['delete']

    
class Dialog(profilesgui.ProfileActionDialog):
    def __init__(self):
        super().__init__(profileCategory)
        self.setWindowTitle(self.tr("Export"))
        
    def accept(self):
        if not self.configWidget.criterionLineEdit.isValid():
            dialogs.warning(translate("wtf", "Invalid criterion"),
                            translate("wtf", "The given filter criterion is invalid"))
            return
        if export(self.configWidget.getProfile()):
            super().accept() # This will close the dialog
        # otherwise something went wrong. Keep the dialog open.
    
    @staticmethod
    def execute():
        dialog = Dialog()
        dialog.exec_()
    



    
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
        self.criterionLineEdit = searchgui.CriterionLineEdit(profile.criterion)
        self.criterionLineEdit.criterionChanged.connect(self._handleCriterionLineEdit)
        self.criterionLineEdit.criterionCleared.connect(self._handleCriterionLineEdit)
        lineLayout.addWidget(self.criterionLineEdit, 1)
        self.flagButton = QtGui.QPushButton()
        self.flagButton.setIcon(utils.getIcon("flag_blue.png"))
        # Make the button as high as the QLineEdit
        self.flagButton.setSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.flagButton.clicked.connect(self._handleFlagButton)
        lineLayout.addWidget(self.flagButton)
        self.layout().addWidget(
                            collapsiblepanel.CollapsiblePanel(self.tr("Choose elements to export"), layout))
        
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
        self.layout().addWidget(collapsiblepanel.CollapsiblePanel(self.tr("Export location"), layout))
        
        self.layout().addStretch(1)
        self.setProfile(profile)
        
    def getProfile(self):
        return self.profile
    
    def setProfile(self, profile):
        self.profile = profile
        self.criterionLineEdit.setCriterion(profile.criterion)
        self.pathLineEdit.setText(profile.path)
        self.structureBox.setCurrentIndex(profile.structure)
        self.deleteBox.setChecked(profile.delete)
    
    def _handleCriterionLineEdit(self):
        self.profile.criterion = self.criterionLineEdit.getCriterion()
    
    def _handleFlagButton(self):
        dialog = FlagDialog(self.flagButton, self.criterionLineEdit)
        dialog.show()
        
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
            

class FlagDialog(dialogs.FancyPopup):
    """A FancyPopup that allows the user to modify the list of flags used in the criterion of *criterionLine*
    (a gui.search.CriterionLineEdit). The dialog recognizes criteria.FlagCriterions if they appear alone
    or grouped together in a criteria.MultiCriterion that uses 'OR' as junction.
    
    *parent* is the button there the FancyPopup should appear.
    """
    def __init__(self, parent, criterionLine):
        super().__init__(parent)
        self.criterionLine = criterionLine
        layout = QtGui.QVBoxLayout(self)
        self.flagView = searchgui.FlagView(self._getSelectedFlags())
        self.flagView.selectionChanged.connect(self._setSelectedFlags)
        layout.addWidget(self.flagView)
    
    def _getSelectedFlags(self):
        """Get the list of flags used in the criterion of self.criterionLine."""
        criterion = self.criterionLine.getCriterion()
        selectedFlags = []
        if isinstance(criterion, criteria.FlagCriterion) and criterion.junction == 'OR':
            selectedFlags = criterion.flags
        elif isinstance(criterion, criteria.MultiCriterion) and criterion.junction == 'OR':
            for c in criterion.criteria:
                if isinstance(c, criteria.FlagCriterion) and c.junction == 'OR':
                    selectedFlags.extend(c.flags)
        return selectedFlags
    
    def _setSelectedFlags(self, selectedFlags):
        """Modify the criterion of self.criterionLine to use the given set of flags.""" 
        criterion = self.criterionLine.getCriterion()
        if criterion is None:
            if len(selectedFlags) > 0:
                newCriterion = criteria.FlagCriterion(selectedFlags)
            else: return
        elif isinstance(criterion, criteria.FlagCriterion) and criterion.junction == 'OR':
            if len(selectedFlags) > 0:
                newCriterion = copy.deepcopy(criterion)
                newCriterion.flags = selectedFlags
            else: newCriterion = None
        elif isinstance(criterion, criteria.MultiCriterion) and criterion.junction == 'OR':
            cList = []
            for c in criterion.criteria:
                if not (isinstance(c, criteria.FlagCriterion) and criterion.junction == 'OR'): 
                    cList.append(c)
            if len(selectedFlags) > 0:
                cList.append(criteria.FlagCriterion(selectedFlags))
            newCriterion = criteria.MultiCriterion('OR', newCriteria)
        else:
            if len(selectedFlags) > 0:
                cList = [criterion, criteria.FlagCriterion(selectedFlags)]
            else: cList = [criterion]
            newCriterion = criteria.combine('OR', cList)
        
        self.criterionLine.setCriterion(newCriterion)
        
        
def export(profile):
    if profile.criterion is not None:
        engine = search.SearchEngine()
        request = engine.searchAndBlock(db.prefix+"elements", profile.criterion)
    else:
        raise NotImplementedError()
    print("Found {} elements for export".format(len(request.result)))
    if len(request.result) == 0:
        dialogs.warning(translate("wtf", "No elements found"),
                        translate("wtf", "The given filter criterion does not match any elements."))
        return False
    
    exported = set()
    if profile.structure == STRUCTURE_FLAT or profile.delete:
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
                exportPath, ext = os.path.splitext(exportPath)
                i = 1
                while exportPath+"-" + str(i) + ext in exportedPaths:
                    i += 1
                exportPath += "-" + str(i) + ext 
            assert exportPath not in exportedPaths
            exportedPaths.add(exportPath)
        else:
            exportPath = element.url.path
            if profile.delete:
                exportedPaths.add(exportPath)
        
        src = os.path.join(config.options.main.collection, element.url.path)
        dest = os.path.join(profile.path, exportPath)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(src, dest)
    
    if profile.delete:
        toDelete = []
        for dirPath, dirNames, fileNames in os.walk(profile.path):
            dirPath = os.path.relpath(dirPath, profile.path)
            if dirPath == '.':
                dirPath = ''
            for filePath in fileNames:
                filePath = os.path.join(dirPath, filePath)
                if filePath not in exportedPaths:
                    toDelete.append(os.path.join(profile.path, filePath))

        if len(toDelete) > 0 and \
                dialogs.question(translate("wtf", "Delete files?"),
                                 translate("wtf",
                                           "The target folder contains %n file(s) that have not been"
                                           " exported. Should they be deleted?",
                                           '', QtCore.QCoreApplication.CodecForTr, len(toDelete))):
            for filePath in toDelete:
                os.remove(filePath)
                # Delete empty directories
                dirPath = os.path.dirname(filePath)
                while len(os.listdir(dirPath)) == 0:
                    assert len(dirPath) > len(profile.path) # profile.path should never be empty
                    os.rmdir(dirPath)
                    dirPath = os.path.dirname(dirPath)
            
    return True
        
        
def exportSQLite():
    """Ask the user for an SQLite-database file and export the whole database to it."""
    from ...gui import mainwindow
    path = QtGui.QFileDialog.getSaveFileName(mainwindow.mainWindow, "Choose export location",
                                             os.path.expanduser('~'))
    if not path:
        return
    if os.path.exists(path):
        os.remove(path)
    from ...database.sql import sqlite
    dbNew = sqlite.Sql()
    dbNew.connect(path)
    from ...database import tables
    for table in tables.sortedList():
        for query in table.createQueries['sqlite']:
            print(query)
            dbNew.query(query)
    for table in tables.sortedList():
        unprefixedTableName = table.name[len(db.prefix):]
        dbNew.query("ALTER TABLE {} RENAME TO {}".format(table.name, unprefixedTableName))
        columns = ','.join(table.columns)
        result = list(db.query("SELECT {columns} FROM {table}", columns=columns, table=table.name))
        print("INSERT INTO {table} ({columns}) VALUES ({qm})"\
                        .format(table=unprefixedTableName, columns=columns,
                                qm=','.join(['?']*len(table.columns))))
        dbNew.multiQuery("INSERT INTO {table} ({columns}) VALUES ({qm})",
                         result,
                         table=unprefixedTableName, columns=columns, qm=','.join(['?']*len(table.columns)))
