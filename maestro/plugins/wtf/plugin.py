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

"""WTF - The write-to-filesystem plugin."""

import functools, os, os.path, shutil, copy, itertools

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from ... import utils, profiles, config, application, database as db, search, logging, filesystem
from ...core import levels, domains, elements, tags
from ...gui import search as searchgui, dialogs, widgets
from ...gui.misc import lineedits
from ...gui.preferences import profiles as profilesgui
from ...search import criteria
from . import filetree


_action = None # the action that is inserted into the Extras menu
_widget = None # the dialog widget must be stored in a variable or it will vanish immediately

profileCategory = None

STRUCTURE_KEEP, STRUCTURE_FLAT = range(2)

OPTION_DELETE = 'delete'
OPTION_INCLUDE_WORK_TITLES = 'includeWorkTitles'
OPTIONS_ALL = [OPTION_DELETE, OPTION_INCLUDE_WORK_TITLES]

def enable():
    global _action, profileCategory
    profileCategory = profiles.ProfileCategory(
                            name = "wtf",
                            title = translate("wtf", "Export"),
                            storageOption = config.getOption(config.storage, 'wtf.profiles'),
                            profileClass = Profile
                            )
    profiles.manager.addCategory(profileCategory)
    
    _action = QtWidgets.QAction(application.mainWindow)
    _action.setText(QtWidgets.QApplication.translate("wtf", "Export..."))
    _action.triggered.connect(Dialog.execute)
    global _sqlAction
    _sqlAction = QtWidgets.QAction(application.mainWindow)
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
        self.domain = None
        self.criterion = None
        self.path = ''
        self.structure = STRUCTURE_KEEP
        self.options = []
        self.read(state)

    @classmethod
    def configurationWidget(cls, profile, parent):
        return ConfigWidget(profile, parent)
    
    def save(self):
        state = {'path': self.path,
                 'structure': self.structure,
                 'options': ','.join(self.options)
                }
        if self.domain is not None:
            state['domain'] = self.domain.name
        if self.criterion is not None:
            state['criterion'] = repr(self.criterion)
        return state
    
    def read(self, state):
        if state is not None:
            if 'domain' in state:
                self.domain = domains.domainByName(state['domain'])
            if 'criterion' in state:
                try:
                    self.criterion = criteria.parse(state['criterion'])
                except criteria.ParseException:
                    pass
            if 'path' in state:
                self.path = state['path']
            if 'structure' in state:
                self.structure = state['structure']
            if 'options' in state:
                self.options = [s for s in state['options'].split(',') if s in OPTIONS_ALL]
                
    def setOption(self, option, enabled):
        if enabled:
            if option not in self.options:
                self.options.append(option)
        else:
            if option in self.options:
                self.options.remove(option)

    
class Dialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Export"))
        layout = QtWidgets.QVBoxLayout(self)
        self.stackedLayout = QtWidgets.QStackedLayout(self)
        layout.addLayout(self.stackedLayout, 1)
        self.profileActionWidget = profilesgui.ProfileActionWidget(profileCategory)
        self.configWidget = self.profileActionWidget.configWidget
        self.stackedLayout.addWidget(self.profileActionWidget)
        self.stackedLayout.setContentsMargins(0,0,0,0)
        fileTreePage = QtWidgets.QWidget()
        fileTreeLayout = QtWidgets.QVBoxLayout(fileTreePage)
        self.statLabel = QtWidgets.QLabel()
        fileTreeLayout.addWidget(self.statLabel)
        self.fileTree = filetree.FileTreeView()
        fileTreeLayout.addWidget(self.fileTree)
        self.stackedLayout.addWidget(fileTreePage)
        
        buttonLayout = QtWidgets.QHBoxLayout()
        layout.addLayout(buttonLayout)
        cancelButton = QtWidgets.QPushButton(self.tr("Cancel"))
        cancelButton.clicked.connect(self.reject)
        buttonLayout.addWidget(cancelButton)
        buttonLayout.addStretch()
        
        self.previousButton = QtWidgets.QPushButton(self.tr("Previous"))
        self.previousButton.clicked.connect(self.previous)
        self.previousButton.setEnabled(False)
        buttonLayout.addWidget(self.previousButton)
        
        self.nextButton = QtWidgets.QPushButton(self.tr("Next"))
        self.nextButton.clicked.connect(self.next)
        buttonLayout.addWidget(self.nextButton)
        
    def previous(self):
        self.stackedLayout.setCurrentIndex(0)
        self.previousButton.setEnabled(False)
        self.nextButton.setText(self.tr("Next"))
        
    def next(self):
        if self.stackedLayout.currentIndex() == 0:
            if not self.configWidget.criterionLineEdit.isValid():
                dialogs.warning(translate("wtf", "Invalid criterion"),
                                translate("wtf", "The given filter criterion is invalid"))
                return
            model = buildFileTree(self.configWidget.profile)
            if not model:
                return
            self.fileTree.setModel(model)
            self.statLabel.setText(self.tr("Exporting {} files with a total length of {}.")
                                           .format(model.fileCount,
                                                   utils.strings.formatLength(model.totalLength)))
            self.stackedLayout.setCurrentIndex(1)
            self.previousButton.setEnabled(True)
            self.nextButton.setText(self.tr("Finish"))
            return
        else:
            #TODO
            self.accept()
            #if export(self.configWidget.getProfile()):
            #    super().accept() # This will close the dialog
            # otherwise something went wrong. Keep the dialog open.
        
    @staticmethod
    def execute():
        dialog = Dialog(application.mainWindow)
        dialog.exec_()


def buildFileTree(profile):
    if profile.criterion is not None:
        search.search(profile.criterion, profile.domain)
    else:
        raise NotImplementedError()
    result = profile.criterion.result
    profile.criterion.result = None # save memory when result is not needed anymore
    print("Found {} elements for export".format(len(result)))
    if len(result) == 0:
        dialogs.warning(translate("wtf", "No elements found"),
                        translate("wtf", "The given filter criterion does not match any elements."))
        return False
     
    fileTree = filetree.FileTreeModel()
    exported = set()
    if profile.structure == STRUCTURE_FLAT or OPTION_DELETE in profile.options:
        exportedPaths = set()
    toExport = levels.real.collect(result)
    while len(toExport) > 0:
        element = toExport.pop()
        if element.id in exported:
            continue
        exported.add(element.id)
        if element.isContainer():
            toExport.extend(levels.real.collect(element.contents))
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
            source = filesystem.sourceByPath(exportPath)
            if source is not None:
                exportPath = source.relPath(exportPath)
            else:
                print("No source", exportPath)
            if OPTION_DELETE in profile.options:
                exportedPaths.add(exportPath)
        
        # Tag changes
        if OPTION_INCLUDE_WORK_TITLES in profile.options:
            titlesToAdd = []
            parentIds = element.parents
            while len(parentIds) > 0:
                parents = levels.real.collect(parentIds)
                parentIds = set() 
                for p in parents:
                    if p.type == elements.TYPE_WORK and tags.TITLE in p.tags:
                        titlesToAdd.extend(p.tags[tags.TITLE])
                    parentIds.update(p.parents)
            if len(titlesToAdd) > 0: 
                element = element.copy() # don't modify the element stored in levels.real
                element.tags[tags.TITLE] = [' - '.join(itertools.chain(reversed(titlesToAdd),
                                                                       element.tags[tags.TITLE]))]
        
        fileTree.addFile(exportPath, element)
    fileTree.sort()
    return fileTree


class ConfigWidget(profilesgui.ProfileConfigurationWidget):

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(1,1,1,1)
        
        layout = QtWidgets.QFormLayout()
        self.domainBox = widgets.DomainBox(profile.domain)
        self.domainBox.domainChanged.connect(self._handleDomainChanged)
        if profile.domain is None:
            profile.domain = self.domainBox.currentDomain()
        layout.addRow(self.tr("Domain:"), self.domainBox)
        lineLayout = QtWidgets.QHBoxLayout()
        self.criterionLineEdit = searchgui.CriterionLineEdit(profile.criterion)
        self.criterionLineEdit.criterionChanged.connect(self._handleCriterionLineEdit)
        self.criterionLineEdit.criterionCleared.connect(self._handleCriterionLineEdit)
        lineLayout.addWidget(self.criterionLineEdit, 1)
        layout.addRow(self.tr("Filter:"), lineLayout)
        self.flagButton = QtWidgets.QPushButton()
        self.flagButton.setIcon(utils.getIcon("flag_blue.png"))
        self.flagButton.setIconSize(QtCore.QSize(16, 16))
        self.flagButton.clicked.connect(self._handleFlagButton)
        lineLayout.addWidget(self.flagButton)
        self.layout().addLayout(layout)
        #self.layout().addWidget(
        #                    collapsiblepanel.CollapsiblePanel(self.tr("Choose elements to export"), layout))
        
        layout = QtWidgets.QFormLayout()
        self.pathLineEdit = lineedits.PathLineEdit(self.tr("Choose an export directory"),
                                                   pathType="existingDirectory",
                                                   path=profile.path)
        self.pathLineEdit.textChanged.connect(self._handlePathEditingFinished)
        layout.addRow(self.tr("Path:"), self.pathLineEdit)
        self.structureBox = QtWidgets.QComboBox()
        self.structureBox.addItem(self.tr("Keep directory structure"), STRUCTURE_KEEP)
        self.structureBox.addItem(self.tr("Put all files into target directory"), STRUCTURE_FLAT)
        self.structureBox.setCurrentIndex(profile.structure)
        self.structureBox.currentIndexChanged.connect(self._handleStructureBox)
        layout.addRow(self.tr("Structure:"), self.structureBox)
        self.deleteBox = QtWidgets.QCheckBox(self.tr("Delete unexported files from target directory"))
        self.deleteBox.toggled.connect(lambda x: self.profile.setOption(OPTION_DELETE, x))
        layout.addRow(self.deleteBox)
        self.layout().addLayout(layout)
        #self.layout().addWidget(collapsiblepanel.CollapsiblePanel(self.tr("Export location"), layout))
        
        layout = QtWidgets.QFormLayout()
        self.includeWorkTitlesBox = QtWidgets.QCheckBox(
                                            self.tr("Include titles of works into the works' contents."))
        self.includeWorkTitlesBox.toggled.connect(
                                        lambda x: self.profile.setOption(OPTION_INCLUDE_WORK_TITLES, x))
        layout.addRow(self.includeWorkTitlesBox)
        self.layout().addLayout(layout)
        #self.layout().addWidget(collapsiblepanel.CollapsiblePanel(self.tr("Tag modifications"), layout))
        
        self.layout().addStretch(1)
        self.setProfile(profile)
    
    def setProfile(self, profile):
        self.profile = profile
        self.criterionLineEdit.setCriterion(profile.criterion)
        self.pathLineEdit.setText(profile.path)
        self.structureBox.setCurrentIndex(profile.structure)
        self.deleteBox.setChecked(OPTION_DELETE in profile.options)
        self.includeWorkTitlesBox.setChecked(OPTION_INCLUDE_WORK_TITLES in profile.options)
    
    def _handleDomainChanged(self, domain):
        self.profile.domain = domain
        
    def _handleCriterionLineEdit(self):
        self.profile.criterion = self.criterionLineEdit.getCriterion()
    
    def _handleFlagButton(self):
        dialog = FlagDialog(self.flagButton, self.criterionLineEdit)
        dialog.show()
        
    def _handlePathEditingFinished(self):
        self.profile.path = self.pathLineEdit.text()
    
    def _handleStructureBox(self, index):
        self.profile.structure = self.structureBox.itemData(index)
            

class FlagDialog(dialogs.FancyPopup):
    """A FancyPopup that allows the user to modify the list of flags used in the criterion of *criterionLine*
    (a gui.search.CriterionLineEdit). The dialog recognizes criteria.FlagCriterions if they appear alone
    or grouped together in a criteria.MultiCriterion that uses 'OR' as junction.
    
    *parent* is the button there the FancyPopup should appear.
    """
    def __init__(self, parent, criterionLine):
        super().__init__(parent)
        self.criterionLine = criterionLine
        layout = QtWidgets.QVBoxLayout(self)
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
            newCriterion = criteria.MultiCriterion('OR', cList)
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
    toExport = levels.real.collect(request.result)
    while len(toExport) > 0:
        element = toExport.pop()
        if element.id in exported:
            continue
        exported.add(element.id)
        if element.isContainer():
            toExport.extend(levels.real.collect(element.contents))
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
    from maestro.gui import mainwindow
    path = QtGui.QFileDialog.getSaveFileName(mainwindow.mainWindow, "Choose export location",
                                             os.path.expanduser('~'))
    if not path:
        return
    if os.path.exists(path):
        os.remove(path)
        
    from maestro.database import tables
    from sqlalchemy import MetaData, Table
    
    engine = db.createEngine(type='sqlite', path=path)
    metadata = MetaData(engine)
    
    for table in tables.metadata.sorted_tables:
        newName = table.name[len(db.prefix):] # do not use a prefix in exported table
        newTable = Table(newName, metadata)
        for column in table.columns:
            newTable.append_column(column.copy())
        newTable.create()
        
        # Copy data
        data = db.engine.execute(table.select()).fetchall()
        if data:
            engine.execute(newTable.insert(), data)
