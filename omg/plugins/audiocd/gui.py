# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2013-2014 Martin Altmayer, Michael Helmling
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

from omg import config, logging
from omg.core import levels, tags
from omg.gui import dialogs, delegates, mainwindow, treeactions, treeview
from omg.gui.delegates.abstractdelegate import *
from omg.models import leveltreemodel, rootedtreemodel
from omg.plugins.musicbrainz import plugin as mbplugin, xmlapi, elements
from omg.plugins.musicbrainz.delegate import MusicBrainzDelegate

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)


def askForDiscId():
    import discid
    device, ok = QtGui.QInputDialog.getText(
                        mainwindow.mainWindow,
                        translate("AudioCD Plugin", "Select device"),
                        translate("AudioCD Plugin", "CDROM device:"),
                        QtGui.QLineEdit.Normal,
                        discid.get_default_device())
    if not ok:
        return None
    with discid.read(device) as disc:
        try:
            disc.read(device)
        except discid.disc.DiscError as e:
            dialogs.warning(translate("AudioCD Plugin", "CDROM drive is empty"), str(e))
            return None
    return device, disc.id, len(disc.tracks)


class ImportAudioCDAction(treeactions.TreeAction):
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr('load audio CD'))

    def _getRelease(self, theDiscid):
        releases = xmlapi.findReleasesForDiscid(theDiscid)
        if len(releases) > 1:
            dialog = ReleaseSelectionDialog(releases, theDiscid)
            if dialog.exec_():
                return dialog.selectedRelease
            else:
                return None
        else:
            return releases[0]
    
    def doAction(self):
        ans = askForDiscId()
        if ans is None:
            return
        device, theDiscid, trackCount = ans
        from . import ripper
        self.ripper = ripper.Ripper(device, theDiscid)
        if config.options.audiocd.earlyrip: 
            self.ripper.start()
        try:
            release = self._getRelease(theDiscid)
            if release is None:
                return
            progress = dialogs.WaitingDialog("Querying MusicBrainz", "please wait", False)
            progress.open()        
            stack = self.level().stack.createSubstack(modalDialog=True)
            level = levels.Level("audiocd", self.level(), stack=stack)
            def callback(url):
                progress.setText(self.tr("Fetching data from:\n{}").format(url))
                QtGui.qApp.processEvents()
            xmlapi.queryCallback = callback 
            xmlapi.fillReleaseForDisc(release, theDiscid)
            progress.close()
            xmlapi.queryCallback = None
            QtGui.qApp.processEvents()
            dialog = ImportAudioCDDialog(level, release)
            logger.debug("yeah")
            if dialog.exec_():
                model = self.parent().model()
                model.insertElements(model.root, len(model.root.contents), [dialog.container])
                if not config.options.audiocd.earlyrip:
                    self.ripper.start()
            stack.close()
        except xmlapi.UnknownDiscException:
            ans = dialogs.question(self.tr("Disc not found"),
                    self.tr("The disc was not found in the MusicBrainz database. "
                            "You need to tag the album yourself. Proceed?"))
            if not ans:
                return False
            from .plugin import simpleDiscContainer
            if not config.options.audiocd.earlyrip:
                self.ripper.start()
            
            self.level().stack.beginMacro(self.tr("Load Audio CD"))
            container = simpleDiscContainer(theDiscid, trackCount, self.level())
            model = self.parent().model()
            model.insertElements(model.root, len(model.root.contents), [container])
            self.level().stack.endMacro()


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
        self.profile = delegates.profiles.DelegateProfile("cdrom")
        self.profile.options['appendRemainingTags'] = True
        self.profile.options['showPaths'] = True
        self.profile.options['showType'] = True
        super().__init__(view, self.profile)
        
    def getUrlWarningItem(self, wrapper):
        element = wrapper.element
        if element.isFile() and element.url.scheme == "audiocd":
            return TextItem(self.tr("[Track {:2d}]").format(element.url.tracknr),
                            DelegateStyle(bold=True, color=Qt.blue))
        return super().getUrlWarningItem(wrapper)


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
        self.addItem(entity.aliases[0].name)
        self.entity = entity
        self.setEditable(True)
        self.setEditText(entity.name)
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
                    self.setItemData(self.count()-1,
                                     ("primary " if alias.primary else "") + \
                                     "alias for locale {}".format(alias.locale),
                                     Qt.ToolTipRole)
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
        self.cellChanged.connect(self._handleCellChanged)
        for row, ent in enumerate(self.entities):
            label = QtGui.QTableWidgetItem(", ".join(ent.asTag))
            label.setFlags(Qt.ItemIsEnabled)
            self.setItem(row, 0, label)
            
            label = QtGui.QLabel('<a href="{}">{}</a>'.format(ent.url(), self.tr("lookup")))
            label.setToolTip(ent.url())
            label.setOpenExternalLinks(True)
            self.setCellWidget(row, 1, label)
            
            sortNameItem = QtGui.QTableWidgetItem(ent.sortName)
            combo = AliasComboBox(ent, sortNameItem)
            combo.aliasChanged.connect(self.aliasChanged)
            self.setCellWidget(row, 2, combo)
            
            self.setItem(row, 3, sortNameItem)
    
    def activeEntities(self):
        entities = []
        for row, ent in enumerate(self.entities):
            if self.cellWidget(row, 2).isEnabled():
                entities.append(ent)
        return entities

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

    def _handleCellChanged(self, row, col):
        if col != 3:
            return
        self.entities[row].sortName = self.item(row, col).text()


class TagMapWidget(QtGui.QTableWidget):
    
    tagConfigChanged = QtCore.pyqtSignal(dict)
    
    def __init__(self, newtags):
        super().__init__()
        self.columns = [ self.tr("Import"), self.tr("MusicBrainz Name"), self.tr("OMG Tag") ]
        self.setColumnCount(len(self.columns))
        self.verticalHeader().hide()
        self.setHorizontalHeaderLabels(self.columns)
        self.horizontalHeader().setResizeMode(QtGui.QHeaderView.ResizeToContents)
        self.setRowCount(len(newtags))
        self.tagMapping = mbplugin.tagMap.copy()
        from omg.gui.tagwidgets import TagTypeBox
        for row, tagname in enumerate(newtags):
            tag = tags.get(tagname)
            self.tagMapping[tagname] = tag
            checkbox = QtGui.QTableWidgetItem()
            if tagname in self.tagMapping and self.tagMapping[tagname] is None:
                checkbox.setCheckState(Qt.Unchecked)
            else:
                checkbox.setCheckState(Qt.Checked)
            self.setItem(row, 0, checkbox)
            
            mbname = QtGui.QTableWidgetItem(tagname)
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
    """The main dialog of this plugin, which is used for adding audioCDs to the editor.
    
    Shows the container structure obtained from musicbrainz and allows to configure alias handling
    and some other options.
    """
    def __init__(self, level, release):
        super().__init__(mainwindow.mainWindow)
        self.setModal(True)
        self.level = level
        
        self.mbNode = elements.MBNode(release)
        self.release = release
        
        self.mbModel = rootedtreemodel.RootedTreeModel()
        self.mbModel.root.setContents([self.mbNode])
        self.mbView = treeview.TreeView(level=None, affectGlobalSelection=False)
        self.mbView.setModel(self.mbModel)
        self.mbView.setItemDelegate(MusicBrainzDelegate(self.mbView))
        
        self.omgModel = leveltreemodel.LevelTreeModel(level)
        self.omgView = treeview.TreeView(level, affectGlobalSelection=False)
        self.omgView.setModel(self.omgModel)
        self.omgView.expandAll()
        self.omgView.setItemDelegate(CDROMDelegate(self.omgView))
        
        # collect alias entities in this release
        entities = set()
        for item in release.walk():
            if not item.ignore:
                entities.update(val for val in itertools.chain.from_iterable(item.tags.values())
                                    if isinstance(val, xmlapi.AliasEntity))
        self.aliasWidget = AliasWidget(entities)
        self.aliasWidget.aliasChanged.connect(self.mbModel.layoutChanged)
        
        self.newTagWidget = TagMapWidget(release.collectExternalTags())
        self.newTagWidget.tagConfigChanged.connect(self.aliasWidget.updateDisabledTags)
        
        makeElementsButton = QtGui.QPushButton(
            QtGui.qApp.style().standardIcon(QtGui.QStyle.SP_ArrowRight), "")
        makeElementsButton.clicked.connect(self.makeElements)

        btbx = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btbx.accepted.connect(self.finalize)
        btbx.rejected.connect(self.reject)
        
        lay = QtGui.QVBoxLayout()
        viewLayout = QtGui.QHBoxLayout()
        viewLayout.addWidget(self.mbView)
        viewLayout.addWidget(makeElementsButton)
        viewLayout.addWidget(self.omgView)
        lay.addLayout(viewLayout, stretch=1)
        lay.addWidget(QtGui.QLabel(self.tr("Alias handling:")))
        lay.addWidget(self.aliasWidget, stretch=0)
        lay.addWidget(QtGui.QLabel(self.tr("New tagtypes:")))
        lay.addWidget(self.newTagWidget, stretch=0)
        lay.addWidget(btbx, stretch=0)
        self.setLayout(lay)
        
        self.resize(mainwindow.mainWindow.size()*0.8)
    
    def makeElements(self):
        self.omgModel.clear()
        self.level.removeElements(list(self.level.elements.values()))
        self.container = self.release.makeElements(self.level, self.newTagWidget.tagMapping)
        self.omgModel.insertElements(self.omgModel.root, 0, [self.container])
    
    def finalize(self):
        mbplugin.updateDBAliases(self.aliasWidget.activeEntities())
        for mbname, omgtag in self.newTagWidget.tagMapping.items():
            config.storage.musicbrainz.tagmap[mbname] = omgtag.name if omgtag else None
        self.level.commit()
        self.accept()
                