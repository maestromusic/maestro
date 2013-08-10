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

from itertools import chain

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
from PyQt4.QtGui import QDialogButtonBox

from omg.core import levels, tags
from omg.gui import delegates, mainwindow, treeview
from omg.gui.treeactions import TreeAction
from omg.gui.dialogs import warning
from omg.models import leveltreemodel
from omg.plugins.musicbrainz import xmlapi

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
        releases = xmlapi.findReleasesForDiscid(theDiscid)
        if len(releases) > 1:
            dialog = ReleaseSelectionDialog(releases, theDiscid)
            if dialog.exec_():
                release = dialog.selectedRelease
            else:
                return
        stack = self.level().stack.createSubstack(modalDialog=True)
        level = levels.Level("audiocd", self.level(), stack=stack)
        dialog = ImportAudioCDDialog(level, release, theDiscid)
        if dialog.exec_():
            level.commit()
        stack.close()
        
class ReleaseSelectionDialog(QtGui.QDialog):
    
    def __init__(self, releases, discid):
        super().__init__(mainwindow.mainWindow)
        self.setModal(True)
        lay = QtGui.QVBoxLayout()
        for release in releases:
            print(release.tags['title'])
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
            but.release = release
            but.setStyleSheet("text-align: left")
            but.clicked.connect(self._handleClick)
            lay.addWidget(but)
        btbx = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel)
        btbx.rejected.connect(self.reject)
        lay.addWidget(btbx)
        self.setLayout(lay)
    
    def _handleClick(self):
        self.selectedRelease = self.sender().release
        self.accept()

class CDROMDelegate(delegates.StandardDelegate):

    def __init__(self, view): 
        # Because it should not be configurable, this profile is not contained in the profile category
        self.profile = delegates.profiles.DelegateProfile("cdrom")
        self.profile.options['appendRemainingTags'] = True
        super().__init__(view, self.profile)

class AliasComboDelegate(QtGui.QStyledItemDelegate):
    
    def __init__(self, box, parent=None):
        super().__init__(parent)
        self.box = box
        
    def paint(self, painter, option, index):
        alias = self.box.entity.aliases[index.row()]
        if alias.primary:
            option.font.setBold(True)
        super().paint(painter, option, index)
        option.font.setBold(False)
        
class AliasComboBox(QtGui.QComboBox):
    
    aliasChanged = QtCore.pyqtSignal(object)
    
    def __init__(self, entity, sortNameItem):
        super().__init__()
        self.addItem(entity.name)
        self.entity = entity
        self.setEditable(True)
        self.sortNameItem = sortNameItem
        self.setItemDelegate(AliasComboDelegate(self))
        self.activated.connect(self._handleActivate)
        self.editTextChanged.connect(self._handleEditTextChanged)
    
    def showPopup(self):
        if not self.entity.loaded:
            self.entity.loadAliases()
            for alias in self.entity.aliases[1:]:
                self.addItem(alias.name)
                if alias.locale:
                    self.setItemData(self.count()-1, ("primary " if alias.primary else "") + "alias for locale {}".format(alias.locale), Qt.ToolTipRole)
            QtGui.qApp.processEvents()
        return super().showPopup()
    
    def _handleActivate(self, index):
        alias = self.entity.aliases[index]
        sortname = alias.sortName
        self.sortNameItem.setText(sortname)
        if self.currentText() != self.entity.name:
            self.entity.selectAlias(index)
            self.aliasChanged.emit(self.entity)
    
    def _handleEditTextChanged(self, text):
        self.entity.name = text
        self.aliasChanged.emit(self.entity)
        

        
class AliasWidget(QtGui.QTableWidget):
    
    aliasChanged = QtCore.pyqtSignal(object)
    
    def __init__(self, entities):
        super().__init__()
        self.entities = sorted(entities, key=lambda ent: "".join(sorted(ent.asTag)))
        self.columns = [self.tr("Roles"),
                        self.tr("WWW"),
                        self.tr("Name"),
                        self.tr("Sort-Name")]
        self.setColumnCount(len(self.columns))
        self.verticalHeader().hide()
        self.setHorizontalHeaderLabels(self.columns)
        self.horizontalHeader().setResizeMode(QtGui.QHeaderView.ResizeToContents)
        self.horizontalHeader().setStretchLastSection(True)
        self.setRowCount(len(self.entities))
        for row, ent in enumerate(self.entities):
            label = QtGui.QTableWidgetItem(", ".join(ent.asTag))
            label.setFlags(Qt.ItemIsEnabled)
            self.setItem(row, 0, label)
            
            label = QtGui.QLabel('<a href="{}">{}</a>'.format(ent.url(), self.tr("view online")))
            label.setOpenExternalLinks(True)
            self.setCellWidget(row, 1, label)
            
            sortNameItem = QtGui.QTableWidgetItem(ent.sortName)
            combo = AliasComboBox(ent, sortNameItem)
            combo.aliasChanged.connect(self.aliasChanged)
            self.setCellWidget(row, 2, combo)
            
            self.setItem(row, 3, sortNameItem)

    def updateDisabledTags(self, lst):
        for row, ent in enumerate(self.entities):
            state = not all(val in lst for val in ent.asTag)
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item:
                    if state:
                        item.setFlags(item.flags() | Qt.ItemIsEnabled)
                    else:
                        item.setFlags(item.flags() ^ Qt.ItemIsEnabled)
                else:
                    widget = self.cellWidget(row, col)
                    widget.setEnabled(state)
            
class NewTagWidget(QtGui.QTableWidget):
    
    disabledTagsChanged = QtCore.pyqtSignal(list)
    
    def __init__(self, newtags):
        super().__init__()
        self.columns = [ self.tr("Import"), self.tr("MB name"), self.tr("Tag Name"),
                        self.tr("Tag Title"), self.tr("Value Type") ]
        self.setColumnCount(len(self.columns))
        self.verticalHeader().hide()
        self.setHorizontalHeaderLabels(self.columns)
        self.horizontalHeader().setResizeMode(QtGui.QHeaderView.ResizeToContents)
        self.setRowCount(len(newtags))
        from omg.gui.tagwidgets import ValueTypeBox, TagTypeBox
        from omg.core import tags
        for row, tag in enumerate(newtags):
            checkbox = QtGui.QTableWidgetItem()
            checkbox.setCheckState(Qt.Checked)
            self.setItem(row, 0, checkbox)
            
            mbname = QtGui.QTableWidgetItem(tag.name)
            mbname.setFlags(Qt.ItemIsEnabled)
            self.setItem(row, 1, mbname)
            
            #self.setItem(row, 2, QtGui.QTableWidgetItem(tag.name))
            self.setCellWidget(row, 2, TagTypeBox(tag, editable=True))
            self.setItem(row, 3, QtGui.QTableWidgetItem(tag.name.capitalize()))
            self.setCellWidget(row, 4, ValueTypeBox(tags.TYPE_VARCHAR))
        self.cellChanged.connect(self._handleCellChange)
    
    def _handleCellChange(self, row, col):
        if col == 0:
            state = self.item(row, col).checkState() == Qt.Checked
            for c in [1, 3]:
                item = self.item(row, c)
                if state:
                    item.setFlags(item.flags() | Qt.ItemIsEnabled)
                else:
                    item.setFlags(item.flags() ^ Qt.ItemIsEnabled)
            for c in [2, 4]:
                self.cellWidget(row, 4).setEnabled(state)
            disabledTags = [self.item(row, 1).text() for row in range(self.rowCount()) if self.item(row, 0).checkState() == Qt.Unchecked]
            self.disabledTagsChanged.emit(disabledTags)
            
            

class ImportAudioCDDialog(QtGui.QDialog):
    
    def __init__(self, level, release, discid):
        super().__init__(mainwindow.mainWindow)
        self.setModal(True)
        self.level = level
        level.stack.beginMacro(self.tr("Create Elements from Audio CD"))
        container = xmlapi.makeReleaseContainer(release, discid, level)
        self.release = release
        self.model = leveltreemodel.LevelTreeModel(level, [container])
        level.stack.endMacro()
        
        self.view = treeview.TreeView(level, affectGlobalSelection=False)
        self.view.setModel(self.model)
        self.view.setItemDelegate(CDROMDelegate(self.view))
        
        self.aliasWidget = AliasWidget(container.mbItem.collectAliasEntities())
        self.aliasWidget.aliasChanged.connect(self._handleAliasChange)
        
        self.newTagWidget = NewTagWidget(container.mbItem.collectExternalTags())
        self.newTagWidget.disabledTagsChanged.connect(self.aliasWidget.updateDisabledTags)
        btbx = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btbx.accepted.connect(self.accept)
        btbx.rejected.connect(self.reject)
        
        lay = QtGui.QVBoxLayout()
        lay.addWidget(self.view)
        lay.addWidget(QtGui.QLabel(self.tr("Alias handling:")))
        lay.addWidget(self.aliasWidget)
        lay.addWidget(QtGui.QLabel(self.tr("New tagtypes:")))
        lay.addWidget(self.newTagWidget)
        lay.addWidget(btbx)
        self.setLayout(lay)
        self.resize(mainwindow.mainWindow.width()*0.8, mainwindow.mainWindow.height()*0.8)
        
    def _handleAliasChange(self, entity):
        for item in self.release.walk():
            rebuild = False
            for val in chain.from_iterable(item.tags.values()):
                if isinstance(val, xmlapi.AliasEntity) and val == entity:
                    rebuild = True
            if rebuild:
                t = item.tags.asOMGTags()
                self.level.changeTags({item.element: tags.TagStorageDifference(item.element.tags, t)})
            