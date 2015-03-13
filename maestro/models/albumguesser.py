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


import os, re, itertools
from collections import OrderedDict

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from maestro import config, profiles, utils
from maestro.core import flags, tags
from maestro.core.elements import ContentList, ContainerType
from maestro.gui.tagwidgets import TagTypeButton

translate = QtCore.QCoreApplication.translate

                
class StandardGuesser(profiles.Profile):
    """The default album guesser. Albums are recognized by files having a certain set of tags in common,
    and optionally being in the same directory.
    Optionally, the title of the guessed album is matched against a regular expression in order to
    detect meta-containers."""
    
    defaultMetaRegex = r" ?[([]?(?:cd|disc|part|teil|disk|vol)[^a-zA-Z]\.? ?([iI0-9]+)[)\]]?"

    def __init__(self, name, type, state):
        """Initialize a guesser profile with the given *name*.
        
        *albumGroupers* is the list of grouper tags;
        the elements may be anything accepted by tags.get. The first grouper tag determines the title
        of the album container.
        If *directoryMode* is True, an additional condition for albums is that all files are in the
        same directory.
        *metaRegex* is a regular expression that finds meta-container indicators; if it is None, this
        will be skipped."""
        super().__init__(name, type, state)
        
        if state is None:
            state = {}
        if 'groupTags' in state:
            self.groupTags = [tags.get(t) for t in state['groupTags']]
        else:
            self.groupTags = [tags.get("album")]
        self.albumTag = self.groupTags[0] if len(self.groupTags) > 0 else None
        self.directoryMode = 'directoryMode' in state and state['directoryMode']
        if 'metaRegex' in state:
            self.metaRegex = state['metaRegex']
        else:
            self.metaRegex = self.defaultMetaRegex
        try:
            self.compilationFlag = flags.get(state['compilationFlag'])
        except (KeyError, ValueError):
            self.compilationFlag = None
        
    def save(self):
        return dict(groupTags=[tag.name for tag in self.groupTags],
                    directoryMode=self.directoryMode,
                    metaRegex=self.metaRegex,
                    compilationFlag=None if self.compilationFlag is None else self.compilationFlag.name)
    
    def guessAlbums(self, level, files):
        """Perform the album guessing on *level*. *files* is a dictionary mapping
        directory name to a list of File objects."""
        self.albums = []
        self.toplevels = set()
        self.level = level
        self.orders = {}
        self.currentOrder = 0
        if len(self.groupTags) == 0 and not self.directoryMode:
            # no grouping -> concatenate filesByFolder
            self.toplevels = list(itertools.chain(*files.values()))
        else:
            self.level.stack.beginMacro(self.tr('guess albums'))
            if self.directoryMode:
                for _, v in sorted(files.items()):
                    self._guessHelper(v)
            else:
                self._guessHelper(itertools.chain(*files.values()))
            
            if self.metaRegex is not None:
                self.guessMetaContainers()
            self.toplevels = sorted(self.toplevels, key=lambda elem: self.orders[elem])    
            self.level.stack.endMacro()

    def _guessHelper(self, files):
        files = list(files)
        domain = files[0].domain
        byKey = OrderedDict()
        existingParents = []
        pureDirMode = self.directoryMode and len(self.groupTags) == 0
        for element in files:
            self.orders[element] = self.currentOrder
            self.currentOrder += 1
            if len(element.parents) > 0:
                # there are already parents -> use the first one
                if element.parents[0] not in existingParents:
                    existingParents.append(element.parents[0])
            else:
                if pureDirMode:
                    key = os.path.dirname(element.url.path)
                else:
                    key = tuple( (tuple(element.tags[tag]) if tag in element.tags else None)
                                                           for tag in self.groupTags)
                if key not in byKey:
                    byKey[key] = []
                byKey[key].append(element)
        existing = self.level.collect(existingParents)
        for elem in existing:
            self.orders[elem] = self.currentOrder
            self.currentOrder += 1
        self.albums.extend(existing)
        self.toplevels.update(existing)
        for key, elements in byKey.items():
            flags = set()
            if self.compilationFlag is not None:
                for elem in elements:
                    if hasattr(elem, "specialTags") and "compilation" in elem.specialTags \
                                    and elem.specialTags["compilation"][0] not in ("0", ""):
                        flags.add(self.compilationFlag)
            if pureDirMode or (self.albumTag in elements[0].tags):
                def position(elem):
                    if hasattr(elem, "specialTags") and "tracknumber" in elem.specialTags:
                        return utils.parsePosition(elem.specialTags["tracknumber"][0])
                    return None
                elementsWithoutPos = { e for e in elements if position(e) is None }
                elementsWithPos = sorted(set(elements) - elementsWithoutPos, key = lambda e: position(e))
                children = {}
                for element in elementsWithPos:
                    if position(element) in children:
                        from ..gui.dialogs import warning
                        warning(self.tr("Error guessing albums"),
                                self.tr("position {} appears twice in {}").format(position(element), key))
                        self.level.removeElements([element])
                    else:
                        children[position(element)] = element.id
                firstFreePosition = position(elementsWithPos[-1])+1 if len(elementsWithPos) > 0 else 1
                for i, element in enumerate(elementsWithoutPos, start=firstFreePosition):
                    children[i] = element.id
                albumTags = tags.findCommonTags(elements)
                albumTags[tags.TITLE] = [key] if pureDirMode else elements[0].tags[self.albumTag]
                cType = ContainerType.Work if tags.get('composer') in albumTags else ContainerType.Album
                container = self.level.createContainer(domain=domain, tags=albumTags,
                                                       flags=list(flags), type=cType,
                                                       contents=ContentList.fromPairs(children.items()))
                self.orders[container] = self.orders[elements[0]]
                self.albums.append(container)
                self.toplevels.add(container)
            else:
                self.toplevels.update(elements)
                
    def guessMetaContainers(self):
        byKey = {}
        for album in self.albums:
            name = ", ".join(album.tags[tags.TITLE])
            discstring = re.findall(self.metaRegex, name,flags=re.IGNORECASE)
            if len(discstring) > 0:
                discnumber = discstring[0]
                if discnumber.lower().startswith("i"): #roman number, support I-III :)
                    discnumber = len(discnumber)
                else:
                    discnumber = int(discnumber)
                discname_reduced = re.sub(self.metaRegex,"",name,flags=re.IGNORECASE)
                key = tuple( (tuple(album.tags[tag]) if tag in album.tags else None) for tag in self.groupTags[1:])
                if (key, discname_reduced) not in byKey:
                    byKey[(key, discname_reduced)] = {}
                if discnumber in byKey[(key,discname_reduced)]:
                    from ..gui.dialogs import warning
                    warning(self.tr("Error guessing meta-containers"),
                            self.tr("disc-number {} appears twice in meta-container {}").format(discnumber, key))
                else:
                    byKey[(key,discname_reduced)][discnumber] = album
        for key, contents in byKey.items():
            metaTags = tags.findCommonTags(contents.values())
            metaTags[tags.TITLE] = [key[1]]
            self.level.setTypes({album: ContainerType.Container for album in contents.values()})
            domain = next(iter(contents.values())).domain
            container = self.level.createContainer(domain=domain, tags=metaTags,
                                                   contents=ContentList.fromPairs(contents.items()),
                                                   type=ContainerType.Album)
            self.orders[container] = self.orders[contents[min(contents)]]
            self.albums.append(container)
            self.toplevels.add(container)
            for c in contents.values():
                if c in self.albums:
                    self.albums.remove(c)
                if c in self.toplevels:
                    self.toplevels.remove(c)

    @classmethod
    def configurationWidget(cls, profile,parent):
        return GuessProfileConfigWidget(profile, parent)


profileCategory = profiles.TypedProfileCategory(
    name='albumguesser',
    title=translate('Albumguesser','Album guesser'),
    description=translate("Albumguesser", "Configure how the editor tries to guess album structure "
                            "when files are dropped into it."),
    storageOption=config.getOption(config.storage, 'editor.albumguesser_profiles'),
    iconName='container',
)

profileCategory.addType(profiles.ProfileType('standard',
                                             translate('Albumguesser', 'standard guesser'),
                                             StandardGuesser))
profiles.manager.addCategory(profileCategory)
if len(profileCategory.profiles()) == 0:
    profileCategory.addProfile(translate("Albumguesser", "Default"),
                               profileCategory.getType('standard'))


class GuessProfileConfigWidget(QtWidgets.QWidget):
    """A widget to configure the profiles used for guessing album structures."""
    
    def __init__(self, profile, parent):
        super().__init__(parent)
        mainLayout = QtWidgets.QVBoxLayout(self)
        descriptionLabel = QtWidgets.QLabel(self.tr('Album guessing is done by means of a list of tags; all files '
                                        'whose tags coincide for this list will then be considered an album.'))
        descriptionLabel.setWordWrap(True)
        mainLayout.addWidget(descriptionLabel)
        toolBar = QtWidgets.QToolBar()

        addTagButton = TagTypeButton()
        addTagButton.setToolTip(self.tr('Add a tag to the grouping conditions'))
        addTagButton.tagChosen.connect(self.addTag)
        toolBar.addWidget(addTagButton)

        removeTagButton = QtWidgets.QToolButton()
        removeTagButton.setIcon(QtGui.QIcon.fromTheme('list-remove'))
        removeTagButton.setToolTip(self.tr('Remove tag from grouping conditions'))
        removeTagButton.clicked.connect(self.removeTag)
        toolBar.addWidget(removeTagButton)
        self.dirModeButton = QtWidgets.QPushButton()
        self.dirModeButton.setIcon(QtGui.QIcon.fromTheme('folder'))
        self.dirModeButton.setCheckable(True)
        self.dirModeButton.setToolTip(self.tr('Only files inside a common directory'))
        self.dirModeButton.clicked.connect(self.updateProfile)
        toolBar.addWidget(self.dirModeButton)
        mainButton = QtWidgets.QToolButton()
        mainButton.setIcon(QtGui.QIcon.fromTheme('media-optical'))
        mainButton.setToolTip(self.tr("Album tag: use this tag's value as container title"))
        mainButton.clicked.connect(self.setMain)
        toolBar.addWidget(mainButton)
        mainLayout.addWidget(toolBar)
        regexLayout = QtWidgets.QHBoxLayout()
        self.regexCheck = QtWidgets.QCheckBox(self.tr('Detect meta-containers:'))
        self.regexEdit = QtWidgets.QLineEdit()
        self.regexEdit.textChanged.connect(self.updateProfile)
        self.regexCheck.toggled.connect(self.regexEdit.setEnabled)
        self.regexCheck.clicked.connect(self.updateProfile)
        resetRegexButton = QtWidgets.QToolButton()
        resetRegexButton.setIcon(QtGui.QIcon.fromTheme('edit-undo'))
        resetRegexButton.setToolTip(self.tr('Reset to default regular expression'))
        self.regexCheck.toggled.connect(resetRegexButton.setEnabled)
        resetRegexButton.clicked.connect(self._handleRegexReset)
        regexLayout.addWidget(self.regexCheck)
        regexLayout.addWidget(self.regexEdit)
        regexLayout.addWidget(resetRegexButton)
        mainLayout.addLayout(regexLayout)
        self.tagListView = QtWidgets.QListWidget()
        mainLayout.addWidget(self.tagListView)
        self.profile = profile
        self.setProfile(profile)
    
    def _handleRegexReset(self):
        self.regexCheck.setChecked(True)
        self.regexEdit.setText(self.profile.defaultMetaRegex)
        
    def setProfile(self, profile: StandardGuesser):
        self.profile = profile
        self.tagListView.clear()
        self.dirModeButton.setChecked(profile.directoryMode)
        for tag in profile.groupTags:
            item = QtWidgets.QListWidgetItem(tag.title)
            item.setData(Qt.UserRole, tag)
            self.tagListView.addItem(item)
        if self.tagListView.count() > 0:
            mainItem = self.tagListView.item(0)
            mainItem.setIcon(QtGui.QIcon.fromTheme('media-optical'))
        if profile.metaRegex:
            self.regexCheck.setChecked(True)
            self.regexEdit.setText(profile.metaRegex)
        else:
            self.regexCheck.setChecked(False)
            self.regexEdit.setDisabled(True)

    def updateProfile(self):
        selectedTags = []
        for i in range(self.tagListView.count()):
            item = self.tagListView.item(i)
            if item.icon():
                selectedTags.insert(0, item.data(Qt.UserRole))
            else:
                selectedTags.append(item.data(Qt.UserRole))
        self.profile.groupTags = selectedTags
        self.profile.albumTag = selectedTags[0] if len(selectedTags) > 0 else None
        if self.regexCheck.isChecked() and len(self.regexEdit.text()):
            self.profile.metaRegex = self.regexEdit.text()
        else:
            self.profile.metaRegex = None
        self.profile.directoryMode = self.dirModeButton.isChecked()
    
    def addTag(self, tag: tags.Tag):
        if tag in self.profile.groupTags:
            return
        newItem = QtWidgets.QListWidgetItem(tag.title)
        newItem.setData(Qt.UserRole, tag)
        self.tagListView.addItem(newItem)
        if self.tagListView.count() == 1:
            self.tagListView.setCurrentRow(0)
            self.setMain()
        self.updateProfile()
        
    def removeTag(self):
        self.tagListView.takeItem(self.tagListView.currentRow())
        self.updateProfile()
    
    def setMain(self):
        if self.tagListView.currentRow() < 0:
            return
        for i in range(self.tagListView.count()):
            item = self.tagListView.item(i)
            if i == self.tagListView.currentRow():
                item.setIcon(QtGui.QIcon.fromTheme('media-optical'))
            else:
                item.setIcon(QtGui.QIcon())
        self.updateProfile()
