# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2013-2015 Martin Altmayer, Michael Helmling
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


import os.path
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import QDialogButtonBox

from maestro import config
from maestro.core import levels, tags, domains, urls
from maestro.core.elements import ContainerType
from maestro.gui import actions, dialogs, delegates, mainwindow, tagwidgets, treeview
from maestro.gui.delegates.abstractdelegate import *
from maestro.models import leveltreemodel
from maestro.plugins.musicbrainz import plugin as mbplugin, xmlapi, elements

translate = QtCore.QCoreApplication.translate


class ImportAudioCDAction(actions.TreeAction):

    label = translate('ImportAudioCDAction', 'Rip audio CD ...')

    ripper = None

    @staticmethod
    def _getRelease(theDiscid):
        releases = xmlapi.findReleasesForDiscid(theDiscid)
        if len(releases) > 1:
            dialog = ReleaseSelectionDialog(releases, theDiscid)
            if dialog.exec_():
                return dialog.selectedRelease
            else:
                return None
        else:
            return releases[0]

    @staticmethod
    def askForDiscId():
        """Asks the user for a CD-ROM device to use.
        :returns: Three-tuple of the *device*, *disc id*, and number of tracks.
        """
        import discid

        device, ok = QtWidgets.QInputDialog.getText(
            mainwindow.mainWindow,
            translate('AudioCD Plugin', 'Select device'),
            translate('AudioCD Plugin', 'CDROM device:'),
            QtWidgets.QLineEdit.Normal,
            discid.get_default_device())
        if not ok:
            return None
        try:
            with discid.read(device) as disc:
                disc.read()
        except discid.disc.DiscError as e:
                dialogs.warning(translate("AudioCD Plugin", "CDROM drive is empty"), str(e))
                return None
        return device, disc.id, len(disc.tracks)

    def doAction(self):
        # device, theDiscid, trackCount = '/dev/sr0', 'qx_MV1nqkljh.L37bA_rgVoyAgU-', 3
        ans = self.askForDiscId()
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

            def callback(url):
                progress.setText(self.tr("Fetching data from:\n{}").format(url))
                QtWidgets.qApp.processEvents()

            xmlapi.queryCallback = callback
            xmlapi.fillReleaseForDisc(release, theDiscid)
            progress.close()
            xmlapi.queryCallback = None
            QtWidgets.qApp.processEvents()
            stack = self.level().stack.createSubstack(modalDialog=True)
            level = levels.Level("audiocd", self.level(), stack=stack)
            dialog = ImportAudioCDDialog(level, release)
            if dialog.exec_():
                model = self.parent().model()
                model.insertElements(model.root, len(model.root.contents), [dialog.container])
                if not config.options.audiocd.earlyrip:
                    self.ripper.start()
            stack.close()
        except xmlapi.UnknownDiscException:
            dialog = SimpleRipDialog(theDiscid, trackCount, self.level())
            if dialog.exec_():
                if not config.options.audiocd.earlyrip:
                    self.ripper.start()
                self.level().stack.beginMacro(self.tr("Load Audio CD"))
                model = self.parent().model()
                model.insertElements(model.root, len(model.root.contents), [dialog.container])
                self.level().stack.endMacro()
        except ConnectionError as e:
            dialogs.warning(self.tr('Error communicating with MusicBrainz'), str(e))
            if 'progress' in locals():
                progress.close()


class ReleaseSelectionDialog(QtWidgets.QDialog):

    def __init__(self, releases, discid):
        super().__init__(mainwindow.mainWindow)
        self.setModal(True)
        lay = QtWidgets.QVBoxLayout()
        lay.addWidget(QtWidgets.QLabel(self.tr('Select release:')))
        for release in releases:
            text = ""
            if len(release.children) > 1:
                pos, medium = release.mediumForDiscid(discid)
                text = "[Disc {}: '{}' of {} in] ".format(pos, medium, len(release.children))
            text += release.tags["title"][0] + "\nby {}".format(release.tags["artist"][0])
            if "date" in release.tags:
                text += "\nreleased {}".format(release.tags["date"][0])
                if "country" in release.tags:
                    text += " ({})".format(release.tags["country"][0])
                if "barcode" in release.tags:
                    text += ", barcode={}".format(release.tags["barcode"][0])
            but = QtWidgets.QPushButton(text)
            but.release = release
            but.setStyleSheet("text-align: left")
            but.clicked.connect(self._handleClick)
            lay.addWidget(but)
        btbx = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel)
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
        from . import plugin
        if element.isFile() and element.url.scheme == 'audiocd':
            tracknr = plugin.parseNetloc(element.url)[1]
            return TextItem(self.tr('[Track {:2d}]').format(tracknr),
                            DelegateStyle(bold=True, color=Qt.blue))
        return super().getUrlWarningItem(wrapper)


class AliasComboDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, box, parent=None):
        super().__init__(parent)
        self.box = box

    def paint(self, painter, option, index):
        alias = self.box.entity.aliases[index.row()]
        if alias.primary:
            option.font.setBold(True)
        super().paint(painter, option, index)
        option.font.setBold(False)


class AliasComboBox(QtWidgets.QComboBox):
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
                    self.setItemData(self.count() - 1,
                                     ("primary " if alias.primary else "") + \
                                     "alias for locale {}".format(alias.locale),
                                     Qt.ToolTipRole)
            QtWidgets.qApp.processEvents()
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


class AliasWidget(QtWidgets.QTableWidget):
    """
    TODO: use sort names!
    """
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
        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.horizontalHeader().setStretchLastSection(True)
        self.setRowCount(len(self.entities))
        self.cellChanged.connect(self._handleCellChanged)
        for row, ent in enumerate(self.entities):
            label = QtWidgets.QTableWidgetItem(", ".join(ent.asTag))
            label.setFlags(Qt.ItemIsEnabled)
            self.setItem(row, 0, label)

            label = QtWidgets.QLabel('<a href="{}">{}</a>'.format(ent.url(), self.tr("lookup")))
            label.setToolTip(ent.url())
            label.setOpenExternalLinks(True)
            self.setCellWidget(row, 1, label)

            sortNameItem = QtWidgets.QTableWidgetItem(ent.sortName)
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


class TagMapWidget(QtWidgets.QTableWidget):
    tagConfigChanged = QtCore.pyqtSignal(dict)

    def __init__(self, newtags):
        super().__init__()
        self.columns = [self.tr("Import"), self.tr("MusicBrainz Name"), self.tr("Maestro Tag")]
        self.setColumnCount(len(self.columns))
        self.verticalHeader().hide()
        self.setHorizontalHeaderLabels(self.columns)
        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.setRowCount(len(newtags))
        self.tagMapping = mbplugin.tagMap.copy()
        from ...gui.tagwidgets import TagTypeBox

        for row, tagname in enumerate(newtags):
            if tagname in self.tagMapping:
                tag = self.tagMapping[tagname]
            else:
                tag = tags.get(tagname)
            checkbox = QtWidgets.QTableWidgetItem()
            ttBox = TagTypeBox(tag, editable=True)
            ttBox.tagChanged.connect(self._handleTagTypeChanged)
            mbname = QtWidgets.QTableWidgetItem(tagname)
            self.setCellWidget(row, 2, ttBox)
            if tag is None:
                checkbox.setCheckState(Qt.Unchecked)
                ttBox.setEnabled(False)
                mbname.setFlags(mbname.flags() ^ Qt.ItemIsEnabled)
            else:
                checkbox.setCheckState(Qt.Checked)
                self.tagMapping[tagname] = tag
                mbname.setFlags(Qt.ItemIsEnabled)
            self.setItem(row, 0, checkbox)
            self.setItem(row, 1, mbname)

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


class ImportAudioCDDialog(QtWidgets.QDialog):
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
        self.maestroModel = leveltreemodel.LevelTreeModel(level)
        self.maestroView = treeview.TreeView(level, affectGlobalSelection=False)
        self.maestroView.setModel(self.maestroModel)
        self.maestroView.setItemDelegate(CDROMDelegate(self.maestroView))
        # collect alias entities in this release
        entities = set()
        for item in release.walk():
            if not item.ignore:
                entities.update(val for val in itertools.chain.from_iterable(item.tags.values())
                                if isinstance(val, xmlapi.AliasEntity))
        self.aliasWidget = AliasWidget(entities)
        self.aliasWidget.aliasChanged.connect(self.makeElements)
        self.newTagWidget = TagMapWidget(release.collectExternalTags())
        self.newTagWidget.tagConfigChanged.connect(self.aliasWidget.updateDisabledTags)
        self.newTagWidget.tagConfigChanged.connect(self.makeElements)
        configLayout = QtWidgets.QVBoxLayout()
        self.searchReleaseBox = QtWidgets.QCheckBox(self.tr('search for existing release'))
        self.searchReleaseBox.setChecked(True)
        self.searchReleaseBox.stateChanged.connect(self.makeElements)
        configLayout.addWidget(self.searchReleaseBox)
        self.mediumContainerBox = QtWidgets.QCheckBox(self.tr('add containers for discs'))
        self.mediumContainerBox.stateChanged.connect(self.makeElements)
        self.forceBox = QtWidgets.QCheckBox(self.tr('...even without title'))
        self.forceBox.stateChanged.connect(self.makeElements)
        configLayout.addWidget(self.mediumContainerBox)
        configLayout.addWidget(self.forceBox)
        btbx = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btbx.accepted.connect(self.finalize)
        btbx.rejected.connect(self.reject)

        lay = QtWidgets.QVBoxLayout()
        topLayout = QtWidgets.QHBoxLayout()
        topLayout.addLayout(configLayout)
        topLayout.addWidget(self.maestroView)
        lay.addLayout(topLayout, stretch=5)
        lay.addWidget(QtWidgets.QLabel(self.tr("Alias handling:")))
        lay.addWidget(self.aliasWidget, stretch=2)
        lay.addWidget(QtWidgets.QLabel(self.tr("New tagtypes:")))
        lay.addWidget(self.newTagWidget, stretch=1)
        lay.addWidget(btbx, stretch=1)
        self.setLayout(lay)
        self.makeElements()
        self.resize(mainwindow.mainWindow.size() * 0.9)

    def makeElements(self, *args, **kwargs):
        self.maestroModel.clear()
        self.level.removeElements(list(self.level.elements.values()))
        elemConfig = elements.ElementConfiguration(self.newTagWidget.tagMapping)
        elemConfig.searchRelease = self.searchReleaseBox.isChecked()
        elemConfig.mediumContainer = self.mediumContainerBox.isChecked()
        elemConfig.forceMediumContainer = self.forceBox.isChecked()
        self.container = self.release.makeElements(self.level, elemConfig)
        self.maestroModel.insertElements(self.maestroModel.root, 0, [self.container])

    def finalize(self):
        mbplugin.updateDBAliases(self.aliasWidget.activeEntities())
        for mbname, maestroTag in self.newTagWidget.tagMapping.items():
            config.storage.musicbrainz.tagmap[mbname] = maestroTag.name if maestroTag else None
        self.level.commit()
        self.accept()


class SimpleRipDialog(QtWidgets.QDialog):
    """Dialog for ripping CDs that are not found in the MusicBrainz database. Allows to enter album
    title, artist, date, and a title for each track,
    """
    def __init__(self, discId, trackCount, level):
        super().__init__(mainwindow.mainWindow)
        self.setModal(True)
        self.level = level
        self.discid = discId
        topLayout = QtWidgets.QHBoxLayout()
        topLayout.addWidget(QtWidgets.QLabel(self.tr('Album title:')))
        self.titleEdit = tagwidgets.TagValueEditor(tags.TITLE)
        self.titleEdit.setValue('unknown album')
        topLayout.addWidget(self.titleEdit)
        midLayout = QtWidgets.QHBoxLayout()
        midLayout.addWidget(QtWidgets.QLabel(self.tr('Artist:')))
        self.artistEdit = tagwidgets.TagValueEditor(tags.get('artist'))
        self.artistEdit.setValue('unknown artist')
        midLayout.addWidget(self.artistEdit)
        midLayout.addStretch()
        midLayout.addWidget(QtWidgets.QLabel(self.tr('Date:')))
        self.dateEdit = tagwidgets.TagValueEditor(tags.get('date'))
        self.dateEdit.setValue(utils.FlexiDate(1900))
        midLayout.addWidget(self.dateEdit)
        layout = QtWidgets.QVBoxLayout()
        description = QtWidgets.QLabel(self.tr('The MusicBrainz database does not contain a release '
            'for this disc. Please fill the tags manually.'))
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addLayout(topLayout)
        layout.addLayout(midLayout)

        tableLayout = QtWidgets.QGridLayout()
        edits = []
        for i in range(1, trackCount+1):
            tableLayout.addWidget(QtWidgets.QLabel(self.tr('Track {:2d}:').format(i)), i-1, 0)
            edits.append(tagwidgets.TagValueEditor(tags.TITLE))
            edits[-1].setValue('unknown title')
            tableLayout.addWidget(edits[-1], i-1, 1)
        layout.addLayout(tableLayout)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.finish)
        box.rejected.connect(self.reject)
        layout.addWidget(box)
        self.setLayout(layout)
        self.edits = edits

    def finish(self):
        elems = []
        for i, edit in enumerate(self.edits, start=1):
            url = urls.URL("audiocd://{0}.{1}{2}/{0}/{1}.flac".format(
                            self.discid, i, os.path.abspath(config.options.audiocd.rippath)))
            elem = self.level.collect(url)
            elTags = tags.Storage()
            elTags[tags.TITLE] = [edit.getValue()]
            elTags[tags.ALBUM] = [self.titleEdit.getValue()]
            elTags[tags.get('artist')] = [self.artistEdit.getValue()]
            elTags[tags.get('date')] = [self.dateEdit.getValue()]
            diff = tags.TagStorageDifference(None, elTags)
            self.level.changeTags({elem: diff})
            elems.append(elem)
        contTags = tags.Storage()
        contTags[tags.TITLE] = [self.titleEdit.getValue()]
        contTags[tags.ALBUM] = [self.titleEdit.getValue()]
        contTags[tags.get('date')] = [self.dateEdit.getValue()]
        contTags[tags.get('artist')] = [self.artistEdit.getValue()]
        cont = self.level.createContainer(contents=elems, type=ContainerType.Album,
                                          domain=domains.default(), tags=contTags)
        self.container = cont
        self.accept()

