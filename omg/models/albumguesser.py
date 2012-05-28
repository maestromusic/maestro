# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import application, config, logging, profiles
from ..core import tags, levels
from ..core.elements import Container
from ..utils import relPath

logger = logging.getLogger(__name__)
translate = QtCore.QCoreApplication.translate

class AlbumGuessCommand(QtGui.QUndoCommand):
    
    def __init__(self, level, containerTags, children, meta = False):
        super().__init__()
        self.level = level
        self.ids = list(children.values())
        self.containerTags = containerTags
        self.containerID = None
        self.children = children
        self.meta = meta
    
    def redo(self):
        if self.containerID is None:
            self.containerID = levels.createTId()
            self.ids.append(self.containerID)
            self.contents = [self.containerID]
        album = Container(self.level, self.containerID, major = True)
        album.tags = self.containerTags
        self.level.elements[self.containerID] = album
        for position, childID in self.children.items():
            child = self.level.get(childID)
            child.parents.append(self.containerID)
            album.contents.insert(position, childID)
            if self.meta and child.isContainer():
                child.major = False
    
    def undo(self):
        del self.level.elements[self.containerID]
        for childID in self.children.values():
            child = self.level.get(childID)
            child.parents.remove(self.containerID)
            if self.meta and child.isContainer():
                child.major = True
                
class StandardGuesser(profiles.Profile):
    """The default album guesser. Albums are recognized by files having a certain set of tags in common,
    and optionally being in the same directory.
    Optionally, the title of the guessed album is matched against a regular expression in order to
    detect meta-containers."""
    
    className = "standardGuesser"
    
    def __init__(self, name, albumGroupers = ["album"],
                  directoryMode = False,
                  metaRegex = r" ?[([]?(?:cd|disc|part|teil|disk|vol)\.? ?([iI0-9]+)[)\]]?"):
        """Initialize a guesser profile with the given *name*. *albumGroupers* is the list of grouper tags;
        the elements may be anything accepted by tags.get. The first grouper tag determines the title
        of the album container.
        If *directoryMode* is True, an additional condition for albums is that all files are in the
        same directory.
        *metaRegex* is a regular expression that finds meta-container indicators; if it is None, this
        will be skipped."""
        super().__init__(name)
        self.groupTags = [tags.get(t) for t in albumGroupers]
        self.albumTag = self.groupTags[0] if len(self.groupTags) > 0 else None
        self.directoryMode = directoryMode
        self.metaRegex = metaRegex
        
    def config(self):
        return [tag.name for tag in self.groupTags], self.directoryMode, self.metaRegex
    
    def guessAlbums(self, level, files):
        """Perform the album guessing on *level*. *files* is a dictionary mapping
        directory name to a list of File objects."""
        self.albums = []
        self.singles = []
        self.level = level
        if len(self.groupTags) == 0 and not self.directoryMode:
            # no grouping -> concatenate filesByFolder
            self.singles = [f.id for f in itertools.chain(*files.values())]
        else:
            application.stack.beginMacro(self.tr('Guess Albums'))
            if self.directoryMode:
                for k, v in sorted(files.items()):
                    self._guessHelper(v)
            else:
                self._guessHelper(itertools.chain(*files.values()))
            
            if self.metaRegex is not None:
                self.guessMetaContainers()    
            application.stack.endMacro()

    def _guessHelper(self, files):
        byKey = {}
        existingParents = set()
        pureDirMode = self.directoryMode and len(self.groupTags) == 0
        for element in files:
            if len(element.parents) > 0:
                # there are already parents -> use the first one
                existingParents.add(element.parents[0])
            else:
                if pureDirMode:
                    key = relPath(os.path.dirname(element.path))
                else:
                    key = tuple( (tuple(element.tags[tag]) if tag in element.tags else None) for tag in self.groupTags)
                if key not in byKey:
                    byKey[key] = []
                byKey[key].append(element)
        for key, elements in byKey.items():
            if pureDirMode or (self.albumTag in elements[0].tags):
                elementsWithoutPos = { e for e in elements if e.tags.position is None }
                elementsWithPos = sorted(set(elements) - elementsWithoutPos, key = lambda e: e.tags.position)
                children = {}
                for element in elementsWithPos:
                    if element.tags.position in children:
                        from ..gui.dialogs import warning
                        warning(self.tr("Error guessing albums"),
                                self.tr("position {} appears twice in {}").format(element.tags.position, key))
                        self.errors.append(elements)
                    else:
                        children[element.tags.position] = element.id
                firstFreePosition = elementsWithPos[-1].tags.position+1 if len(elementsWithPos) > 0 else 1
                for i, element in enumerate(elementsWithoutPos, start = firstFreePosition):
                    children[i] = element.id
                albumTags = tags.findCommonTags(elements)
                albumTags[tags.TITLE] = [key] if pureDirMode else elements[0].tags[self.albumTag]
                command = AlbumGuessCommand(self.level, albumTags, children)
                application.stack.push(command)
                self.albums.append(command.containerID)
            else:
                self.singles.extend(element.id for element in elements)
                
    def guessMetaContainers(self):
        byKey = {}
        for albumID in self.albums:
            album = self.level.get(albumID)
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
            command = AlbumGuessCommand(self.level, metaTags, {pos:album.id for pos,album in contents.items()}, meta = True)
            application.stack.push(command)
            self.albums.append(command.containerID)
            for c in contents:
                self.albums.remove(c.id)

    @classmethod    
    def configurationWidget(cls, profile = None, parent = None):
        widget = GuessProfileConfigWidget(parent, profile)
        return widget


profileConfig = profiles.ProfileConfiguration("albumguesser", config.storage.editor.albumguesser, [StandardGuesser])
profileConfig.loadConfig()

class GuessProfileConfigWidget(profiles.ConfigurationWidget):
    """A widget to configure the profiles used for "guessing" album structures.
    
    Each profile is determined by its name, and contains a list of tags by which albums are grouped. One
    tag is the "main" grouper tag; this one is used to determine the TITLE-tag of the new album as well as
    for automatic meta-container guessing. Additionally, each profile sets the "directory mode" flag. If 
    that is enabled, only albums within the same directory on the filesystem will be grouped together."""
    def __init__(self, parent, profile = None):
        super().__init__(parent)
        mainLayout = QtGui.QVBoxLayout(self)
        descriptionLabel = QtGui.QLabel(self.tr(
"""Configuration of the "album guessing" profiles. These profiles determine how the editor tries to \
guess the album structure of files which are dropped into the editor.

Album guessing is done by means of a list of tags; all files whose tags coincide for this list will then be \
considered an album. The "main" grouper tag determines the TITLE tag of the new album. If "directory mode" \
is on, files will only be grouped together if they are in the same directory."""))
        descriptionLabel.setWordWrap(True)
        mainLayout.addWidget(descriptionLabel)
        
        configLayout = QtGui.QHBoxLayout()
        self.preview = QtGui.QListWidget()
        configSideLayout = QtGui.QVBoxLayout()
        self.addTagButton = QtGui.QPushButton(self.tr("add tag..."))
        self.tagMenu = QtGui.QMenu()
        self.tagActions = []
        actionGroup = QtGui.QActionGroup(self)
        for tag in tags.tagList:
            tagAction = QtGui.QAction(self)
            tagAction.setText(tag.title)
            tagAction.setData(tag.name)
            actionGroup.addAction(tagAction)
            self.tagMenu.addAction(tagAction)
            self.tagActions.append(tagAction)
        self.addTagButton.setMenu(self.tagMenu)
        actionGroup.triggered.connect(self.addTag)
        self.removeTagButton = QtGui.QPushButton(self.tr("remove tag"))
        self.removeTagButton.clicked.connect(self.removeTag)
        self.directoryModeButton = QtGui.QPushButton(self.tr("directory mode"))
        self.directoryModeButton.setCheckable(True)
        self.directoryModeButton.setToolTip(self.tr(
"""If this is checked, only files within the same directory will be considered for automatic album
guessing. This is useful in most cases, unless you have albums that are split across several folders."""))
        configSideLayout.addWidget(self.addTagButton)
        configSideLayout.addWidget(self.removeTagButton)
        configSideLayout.addWidget(self.directoryModeButton)
        self.setMainGrouperButton = QtGui.QPushButton(self.tr("set to main"))
        self.setMainGrouperButton.clicked.connect(self.setMain)
        configSideLayout.addWidget(self.setMainGrouperButton)
        configSideLayout.addStretch()
        configLayout.addWidget(self.preview)
        configLayout.addLayout(configSideLayout)
        mainLayout.addLayout(configLayout)
        regexLayout = QtGui.QHBoxLayout()
        self.regexCheck = QtGui.QCheckBox(self.tr("Find Meta-Containers"))
        self.regexEdit = QtGui.QLineEdit()
        self.regexCheck.toggled.connect(self.regexEdit.setEnabled)
        regexLayout.addWidget(self.regexCheck)
        regexLayout.addWidget(self.regexEdit)
        mainLayout.addLayout(regexLayout)
        
        self.setCurrentProfile(profile)
        
    def setCurrentProfile(self, name):
        self.profile = name
        self.preview.setEnabled(name != None)
        self.preview.clear()
        if name != None:
            profile = profileConfig[name]
            self.directoryModeButton.setChecked(profile.directoryMode)
            for tag in profile.groupTags:
                item = QtGui.QListWidgetItem(tag.title)
                item.setData(Qt.UserRole, tag.name)
                self.preview.addItem(item)
            if self.preview.count() > 0:
                mainItem = self.preview.item(0)
                f = mainItem.font()
                f.setBold(True)
                mainItem.setFont(f)
                self.preview.setCurrentRow(0)
            for action in self.tagActions:
                action.setDisabled(action.data() in profile.groupTags)
            if profile.metaRegex is not None:
                self.regexCheck.setChecked(True)
                self.regexEdit.setText(profile.metaRegex)
            else:
                self.regexCheck.setChecked(False)
                self.regexEdit.setDisabled(True)
    
    def currentConfig(self):
        tags = []
        for i in range(self.preview.count()):
            item = self.preview.item(i)
            if item.font().bold():
                tags.insert(0, item.data(Qt.UserRole))
            else:
                tags.append(item.data(Qt.UserRole))
        if self.regexCheck.isEnabled():
            regex = self.regexEdit.text()
        else:
            regex = None
        return tags, self.directoryModeButton.isChecked(), regex
            
    
    def addTag(self, action):
        newItem = QtGui.QListWidgetItem(action.text())
        newItem.setData(Qt.UserRole, action.data())
        self.preview.addItem(newItem)
        action.setDisabled(True)
        if self.preview.count() == 1:
            self.preview.setCurrentRow(0)
            self.setMain()
        
    def removeTag(self):
        tagName = self.preview.currentItem().text()
        tag = tags.get(tagName)
        for action in self.tagActions:
            if action.data() == tag:
                action.setEnabled(True)
        self.preview.takeItem(self.preview.currentRow())
    
    def setMain(self):
        item = self.preview.currentItem()
        for i in range(self.preview.count()):
            item = self.preview.item(i)
            font = item.font()
            font.setBold(i == self.preview.currentRow())
            item.setFont(font)
