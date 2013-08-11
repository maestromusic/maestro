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
            model = self.parent().model()
            model.insertElements(model.root, len(model.root.contents), [dialog.container])
        stack.close()
        
class ReleaseSelectionDialog(QtGui.QDialog):
    
    def __init__(self, releases, discid):
        super().__init__(mainwindow.mainWindow)
        self.setModal(True)
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
        self.profile.options['showPaths'] = True
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

    def updateDisabledTags(self, mapping):
        for row, ent in enumerate(self.entities):
            state = not all((val in mapping and mapping[val] is None) for val in ent.asTag)
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


class NewTagsWidget(QtGui.QTableWidget):
    
    tagConfigChanged = QtCore.pyqtSignal(dict)
    
    def __init__(self, newtags):
        super().__init__()
        self.columns = [ self.tr("Import"), self.tr("MusicBrainz Name"), self.tr("OMG Tag") ]
        self.setColumnCount(len(self.columns))
        self.verticalHeader().hide()
        self.setHorizontalHeaderLabels(self.columns)
        self.horizontalHeader().setResizeMode(QtGui.QHeaderView.ResizeToContents)
        self.setRowCount(len(newtags))
        self.tagMapping = {}
        from omg.gui.tagwidgets import TagTypeBox
        for row, tag in enumerate(newtags):
            self.tagMapping[tag.name] = tag
            checkbox = QtGui.QTableWidgetItem()
            checkbox.setCheckState(Qt.Checked)
            self.setItem(row, 0, checkbox)
            
            mbname = QtGui.QTableWidgetItem(tag.name)
            mbname.setFlags(Qt.ItemIsEnabled)
            self.setItem(row, 1, mbname)
            
            ttBox = TagTypeBox(tag, editable=True)
            ttBox.tagChanged.connect(self._handleTagTypeChanged)
            self.setCellWidget(row, 2, ttBox)
            
        self.cellChanged.connect(self._handleCellChange)
    
    def _handleCellChange(self, row, col):
        if col != 0:
            return
        state = self.item(row, 0).checkState() == Qt.Checked
        item = self.item(row, 1)
        if state:
            item.setFlags(item.flags() | Qt.ItemIsEnabled)
            self.tagMapping[item.text()] = self.cellWidget(row, 2).getTag()
        else:
            item.setFlags(item.flags() ^ Qt.ItemIsEnabled)
            self.tagMapping[item.text()] = None
        self.cellWidget(row, 2).setEnabled(state)           
        self.tagConfigChanged.emit(self.tagMapping)
            
    def _handleTagTypeChanged(self, tag):
        for row in range(self.rowCount()):
            if self.cellWidget(row, 2) is self.sender():
                break
        self.tagMapping[self.item(row, 1).text()] = tag
        self.tagConfigChanged.emit(self.tagMapping)


class ImportAudioCDDialog(QtGui.QDialog):
    
    def __init__(self, level, release, discid):
        super().__init__(mainwindow.mainWindow)
        self.setModal(True)
        self.level = level
        level.stack.beginMacro(self.tr("Create Elements from Audio CD"))
        container = xmlapi.makeReleaseContainer(release, discid, level)
        self.container = container
        self.release = release
        self.model = leveltreemodel.LevelTreeModel(level, [container])
        level.stack.endMacro()
        
        self.view = treeview.TreeView(level, affectGlobalSelection=False)
        self.view.setModel(self.model)
        self.view.setItemDelegate(CDROMDelegate(self.view))
        self.view.expandAll()
        
        self.aliasWidget = AliasWidget(container.mbItem.collectAliasEntities())
        self.aliasWidget.aliasChanged.connect(self.updateTags)
        
        self.newTagWidget = NewTagsWidget(container.mbItem.collectExternalTags())
        self.newTagWidget.tagConfigChanged.connect(self.aliasWidget.updateDisabledTags)
        self.newTagWidget.tagConfigChanged.connect(self.updateTags)
        
        btbx = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btbx.accepted.connect(self.finalize)
        btbx.rejected.connect(self.reject)
        
        lay = QtGui.QVBoxLayout()
        lay.addWidget(self.view, 2)
        lay.addWidget(QtGui.QLabel(self.tr("Alias handling:")))
        lay.addWidget(self.aliasWidget, 1)
        lay.addWidget(QtGui.QLabel(self.tr("New tagtypes:")))
        lay.addWidget(self.newTagWidget, 1)
        lay.addWidget(btbx, 1)
        self.setLayout(lay)
        self.resize(mainwindow.mainWindow.width()*0.8, mainwindow.mainWindow.height()*0.8)
    
    def finalize(self):
        for item in self.release.walk():
            del item.element.mbItem
        self.level.commit()
        self.accepted.emit()
    
    def updateTags(self):
        changes = {}
        for item in self.release.walk():
            t = item.tags.asOMGTags(self.newTagWidget.tagMapping)
            if t != item.element.tags:
                changes[item.element] = tags.TagStorageDifference(item.element.tags, t)
        if len(changes):
            self.level.changeTags(changes)