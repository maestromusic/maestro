# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2012-2014 Martin Altmayer, Michael Helmling
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

import functools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import dialogs
from ... import profiles, utils


def showPreferences(category, profile=None):
    """Open the preferences dialog on the panel for the given profile category. Optionally pre-select a
    profile."""
    from .. import mainwindow
    from . import PreferencesDialog
    dialog = PreferencesDialog(mainwindow.mainWindow)
    dialog.showPanel('profiles/'+category.name)
    if profile is not None:
        dialog.getConfigurationWidget('profiles/'+category.name).showProfile(profile)
    dialog.exec_()


class CreateProfileDialog(QtGui.QDialog):
    """Small dialog that is used to create a new profile of a TypedProfileCategory. It asks the user for 
    the type and name of the new profile. NewProfileDialog works only with typed categories. For normal
    categories, simply use suggestProfileName and create an instance of the profile-class.
    """
    def __init__(self, category, parent=None):
        assert isinstance(category, profiles.TypedProfileCategory)
        assert len(category.types) > 0
        super().__init__(parent)
        self.setWindowTitle(self.tr("Create profile"))
        self.category = category
        self.profile = None # stores new profile, when created
        
        layout = QtGui.QVBoxLayout(self)
        label = QtGui.QLabel(self.tr("Choose a name and type for the new profile:"))
        layout.addWidget(label)
        
        formLayout = QtGui.QFormLayout()
        formLayout.setSizeConstraint(QtGui.QLayout.SetFixedSize)
        layout.addLayout(formLayout)
        self.typeBox = QtGui.QComboBox()
        self.typeBox.addItems([type.title for type in self.category.types])
        self.typeBox.currentIndexChanged.connect(self._handleTypeChanged)
        formLayout.addRow(self.tr("Type:"), self.typeBox)
        self.nameLineEdit = QtGui.QLineEdit()
        self._handleTypeChanged(0) # fill line edit with a suitable name
        formLayout.addRow(self.tr("Name:"), self.nameLineEdit)
        
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        layout.addWidget(buttonBox)
        
    def _handleTypeChanged(self, i):
        """Whenever the user selects a new type, fill a suitable name into the name-lineedit."""
        type = self.category.types[i]
        self.nameLineEdit.setText(self.category.suggestProfileName(type))
        
    def accept(self):
        """Check the data in the input fields and create a new profile."""
        name = self.nameLineEdit.text()
        type = self.category.types[self.typeBox.currentIndex()]
        
        if len(name) == 0:
            return
        
        if self.category.get(name) is not None:
            dialogs.warning(self.tr("Invalid name"), self.tr("There is already a profile of this name."))
        else: 
            self.profile = self.category.addProfile(name, type)
        super().accept()
            
    @staticmethod
    def execute(category, parent=None):
        dialog = CreateProfileDialog(category, parent=None)
        dialog.exec_()
        return dialog.profile
        
        
class ProfileConfigurationPanel(QtGui.QWidget):
    """Panel to configure profiles of a given category. It consists of a tree of profiles and (for typed
    categories) types on the left and the category-specific configuration widget on the right."""
    def __init__(self, dialog, panel, category, profile=None):
        super().__init__(panel)
        style = QtGui.QApplication.style()
        
        self.category = category
        self.profile = profile
        self.category.profileAdded.connect(self._handleProfileAdded)
        self.category.profileRenamed.connect(self._handleProfileRenamed)
        self.category.profileRemoved.connect(self._handleProfileRemoved)
        
        self.setLayout(QtGui.QHBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)
        self.layout().setSpacing(0)
        
        # Left column
        leftLayout = QtGui.QVBoxLayout()
        self.layout().addLayout(leftLayout)
        
        toolBar = QtGui.QToolBar()
        toolBar.setIconSize(QtCore.QSize(16, 16))
        leftLayout.addWidget(toolBar)
        
        self.createButton = QtGui.QToolButton()
        self.createButton.setIcon(utils.getIcon('add.png'))
        self.createButton.setToolTip(self.tr("Create profile"))
        self.createButton.clicked.connect(self._handleCreateButton)
        toolBar.addWidget(self.createButton)
        self.renameButton = QtGui.QToolButton()
        self.renameButton.setIcon(utils.getIcon('pencil.png'))
        self.renameButton.setToolTip(self.tr("Rename profile"))
        self.renameButton.clicked.connect(self._handleRenameButton)
        toolBar.addWidget(self.renameButton)
        self.deleteButton = QtGui.QToolButton()
        self.deleteButton.setIcon(utils.getIcon('delete.png'))
        self.deleteButton.setToolTip(self.tr("Delete profile"))
        self.deleteButton.clicked.connect(self._handleDeleteButton)
        toolBar.addWidget(self.deleteButton)
        
        self.profileTree = ProfileTree(self.category)
        self.profileTree.itemSelectionChanged.connect(self._handleSelectionChanged)
        self.profileTree.setFrameStyle(QtGui.QFrame.NoFrame)
        leftLayout.addWidget(self.profileTree, 1)
    
        # Line between left and right layout
        frame = QtGui.QFrame()
        frame.setFrameStyle(QtGui.QFrame.VLine)
        palette = frame.palette()
        # Draw frame in the color that is used for the Sunken | 
        palette.setColor(QtGui.QPalette.WindowText, self.palette().color(QtGui.QPalette.Dark)) 
        frame.setPalette(palette)
        self.layout().addWidget(frame)
        
        # Right column
        right = QtGui.QScrollArea()
        right.setWidgetResizable(True)
        right.setFrameStyle(QtGui.QFrame.NoFrame)
        innerRight = QtGui.QWidget()
        right.setWidget(innerRight)
        rightLayout = QtGui.QVBoxLayout(innerRight)
        self.layout().addWidget(right, 1)
        
        self.titleLabel = QtGui.QLabel()
        self.titleLabel.setStyleSheet('QLabel {font-weight: bold}')
        rightLayout.addWidget(self.titleLabel)
        
        self.stackedLayout = QtGui.QStackedLayout()
        self.stackedLayout.setContentsMargins(0,0,0,0)
        rightLayout.addLayout(self.stackedLayout, 1)
        noProfileWidget = NoProfileYetWidget(self)
        noProfileWidget.createButton.clicked.connect(self._handleCreateButton)
        self.stackedLayout.addWidget(noProfileWidget)
        
        self.profileWidgets = {}
        
        if len(self.category.profiles()) > 0:
            self.profileTree.selectProfile(self.category.profiles()[0])
    
    def showProfile(self, profile):
        """Show the configuration widget for the given profile in the right part of the panel."""
        if profile == self.profile or not self.okToClose():
            return
        self.profile = profile
        
        if profile is None:
            self.titleLabel.setText('')
            self.stackedLayout.setCurrentIndex(0)
        else:
            if profile not in self.profileWidgets:
                widget = profile.configurationWidget(self)
                if widget is None:
                    widget = QtGui.QLabel(self.tr("There are no options for this profile."))
                    widget.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                else:
                    widget.layout().setContentsMargins(0,0,0,0)
                self.stackedLayout.addWidget(widget)
                self.profileWidgets[profile] = widget
            
            self.titleLabel.setText(self.tr("Configure profile '{}'".format(profile.name)))
            self.stackedLayout.setCurrentWidget(self.profileWidgets[profile])
            self.profileTree.selectProfile(profile)
            
    def _handleSelectionChanged(self):
        """Show the profile selected by the user. Enable/disable buttons according to the selection:
        Built-in configurations must not be deleted."""
        profile = self.profileTree.selectedProfile()
        if profile is not None:
            self.showProfile(profile)
        self.renameButton.setEnabled(profile is not None and not profile.builtIn)
        self.deleteButton.setEnabled(profile is not None and not profile.builtIn)
            
    def _handleProfileAdded(self, profile):
        """Handle profileAdded-signal of the profile category."""
        if len(self.category.profiles()) == 1:
            self.showProfile(profile)
            
    def _handleProfileRenamed(self, profile):
        """Handle profileRenamed-signal of the profile category."""
        if profile == self.profile:
            self.titleLabel.setText(self.tr("Configure profile '{}'".format(profile.name)))
        
    def _handleProfileRemoved(self, profile):
        """Handle profileRemoved-signal of the profile category."""
        if len(self.category.profiles()) == 0:
            self.showProfile(None)
        if profile in self.profileWidgets:
            widget = self.profileWidgets[profile]
            self.stackedLayout.removeWidget(widget)
            widget.setParent(None)
            del self.profileWidgets[profile]
            
    def _handleCreateButton(self):
        """Handle the add button (which is visible only if the category does not use profile types)."""
        if not isinstance(self.category, profiles.TypedProfileCategory):
            profile = self.category.addProfile(self.category.suggestProfileName())
        else:
            profile = CreateProfileDialog.execute(self.category, self)
        if profile is not None:
            self.profileTree.selectProfile(profile)
                    
    def _handleRenameButton(self):
        """Ask the user for a new name of the current profile and change names."""
        if self.profile is None:
            return
        text, ok = QtGui.QInputDialog.getText(self,
                                              self.tr("Profile name"),
                                              self.tr("Choose a new name:"),
                                              text=self.profile.name)
        if ok and len(text) > 0:
            existingProfile = self.category.get(text)
            if existingProfile == self.profile:
                return # no change
            elif existingProfile is not None:
                dialogs.warning(self.tr("Invalid name"), self.tr("There is already a profile of this name."))
            else:
                self.category.renameProfile(self.profile, text)
                
    def _handleDeleteButton(self):
        """Ask the user again and delete the current profile."""
        if self.profile is not None and dialogs.question(
                            self.tr("Delete profile"),
                            self.tr("Should the profile '{}' really be deleted?").format(self.profile.name),
                            parent=self):
            self.category.deleteProfile(self.profile)
            
    def okToClose(self):
        """Give the current profile configuration widget a chance to abort closing the preferences dialog
        or switching to another profile or preferences panel. Return True if closing is admissible."""
        return not hasattr(self.stackedLayout.currentWidget(), 'okToClose') \
                    or self.stackedLayout.currentWidget().okToClose()
        
        
class ProfileTree(QtGui.QTreeWidget):
    """TreeWidget that displays all profiles of a given category. For non-typed categories, profiles will
    be displayed as list. In typed categories a tree with types on first level and profiles on second
    level is used.
    """
    def __init__(self, category):
        super().__init__()
        self.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.setItemsExpandable(False)
        self.setRootIsDecorated(False)
        self.header().hide()
        self.header().setResizeMode(QtGui.QHeaderView.ResizeToContents)
        self.header().setStretchLastSection(False)
        
        self.category = category
        self.category.profileAdded.connect(self._handleProfileAdded)
        self.category.profileRemoved.connect(self._handleProfileRemoved)
        self.category.profileRenamed.connect(self._handleProfileRenamed)
        if isinstance(self.category, profiles.TypedProfileCategory):
            for type in self.category.types:
                self._handleTypeAdded(type)
        for profile in self.category.profiles():
            self._handleProfileAdded(profile)
            
    # make the treewidget narrower
    def minimumSizeHint(self):
        return QtCore.QSize(150, 100)
    
    sizeHint = minimumSizeHint
    
    def selectedProfile(self):
        """Return the currently selected profile."""
        items = self.selectedItems()
        if len(items) > 0:
            return items[0].data(0, Qt.UserRole)
        else: return None
    
    def selectProfile(self, profile):
        """Select the given profile."""
        self.clearSelection()
        item, i = self._findProfileItem(profile)
        if item is not None:
            item.setSelected(True)
                    
    def _findToplevelItem(self, data):
        """Return the toplevel QTreeWidgetItem corresponding to *data* which must be a type (in typed
        categories) or a profile (otherwise)."""
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.data(0, Qt.UserRole) == data:
                return item, i
        else: return None, None
                    
    def _findProfileItem(self, profile):
        """Return the QTreeWidgetItem corresponding to the given profile."""
        if not isinstance(self.category, profiles.TypedProfileCategory):
            return self._findToplevelItem(profile)
        else:
            typeItem, i = self._findToplevelItem(profile.type)
            if typeItem is not None:
                for i in range(typeItem.childCount()):
                    item = typeItem.child(i)
                    if item.data(0, Qt.UserRole) == profile:
                        return item, i
            return None, None
                    
    def _handleTypeAdded(self, type):
        """Handle the typeAdded-signal of the profile category."""
        text = self.tr("{}:").format(type.title)
        if type != self.category.types[0]:
            text = '\n' + text # create space between subtrees
        typeItem = QtGui.QTreeWidgetItem([text])
        font = typeItem.font(0)
        font.setItalic(True)
        typeItem.setFont(0, font)
        typeItem.setData(0, Qt.UserRole, type)
        typeItem.setFlags(Qt.ItemIsEnabled)
        self.addTopLevelItem(typeItem)
        typeItem.setExpanded(True)
    
    def _handleTypeRemove(self, type):
        """Handle the typeRemoved-signal of the profile category."""
        item, i = self._findToplevelItem(type)
        if item is not None:
            self.takeToplevelItem(i)
        if i == 0:
            # correct newlines in type widgets
            if self.topLevelItemCount() > 0:
                firstItem = self.topLevelItem(0)
                text = firstItem.text(0)
                if text.startswith('\n'):
                    firstItem.setText(0, text[1:])
    
    def _handleProfileAdded(self, profile):
        """Handle the profileAdded-signal of the profile category."""
        if not isinstance(self.category, profiles.TypedProfileCategory):
            item = QtGui.QTreeWidgetItem([profile.name])
            item.setData(0, Qt.UserRole, profile)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.addTopLevelItem(item)
        else:
            typeItem, i = self._findToplevelItem(profile.type)
            if typeItem is not None:
                item = QtGui.QTreeWidgetItem([profile.name])
                item.setData(0, Qt.UserRole, profile)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                typeItem.addChild(item)
        
    def _handleProfileRemoved(self, profile):
        """Handle the profileRemoved-signal of the profile category."""
        if not isinstance(self.category, profiles.TypedProfileCategory):
            item, i = self._findToplevelItem(profile)
            if item is not None:
                self.takeTopLevelItem(i)
        else:
            item, i = self._findProfileItem(profile)
            if item is not None:
                item.parent().removeChild(item)
                
    def _handleProfileRenamed(self, profile):
        """Handle the profileRenamed-signal of the profile category."""
        item, i = self._findProfileItem(profile)
        if item is not None:
            item.setText(0, profile.name)
                
        
class NoProfileYetWidget(QtGui.QWidget):
    """This widget is displayed in a ProfileConfigurationPanel if the underlying profile category does
    not have a profile yet."""
    def __init__(self, parent):
        super().__init__(parent)
        self.category = parent.category
        layout = QtGui.QVBoxLayout(self)
        label = QtGui.QLabel()
        label.setWordWrap(True)
        layout.addWidget(label)
        
        if isinstance(self.category, profiles.TypedProfileCategory) and len(self.category.types) == 0:
            label.setText(self.tr("There is no profile type. Probably you need to install a plugin"
                                  " that adds support for '{}'.").format(self.category.name))
            return
        
        label.setText(self.tr("There is no profile yet."))
        
        self.createButton = QtGui.QPushButton(utils.getIcon('add.png'), self.tr("Create profile"))
        self.createButton.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        layout.addWidget(self.createButton)
        layout.addStretch()
    

class CategoryMenu(QtGui.QLabel):
    """Simple menu of available profile categories. A click on a category will open the corresponding
    preferences panel."""
    def __init__(self, dialog, panel):
        super().__init__(panel)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.linkActivated.connect(dialog.showPanel)
        self.setIndent(10)
        profiles.manager.categoryAdded.connect(self._updateText)
        profiles.manager.categoryRemoved.connect(self._updateText)
        self._updateText()
        
    def _updateText(self):
        """Reset the HTML text of this label."""
        parts = [self.tr("Choose a profile category:"), "<ul>"]
        for category in profiles.manager.categories:
            parts.append('<li style="margin-bottom: 10px"><a href="profiles/{}">{}</a></li>'
                         .format(category.name, category.title))
        parts.append("</ul>")
        self.setText(''.join(parts))
        

class ProfileComboBox(QtGui.QComboBox):
    """This class provides a combo box that lets the user choose a profile. Parameters are
    
        - *category*: The category where the profiles are taken from,
        - *restrictToType*: if this is not None, the user may only choose profiles of this profile type,
        - *default*: the profile that is selected at the beginning,
        - *includeConfigure*: Add an entry 'Configure...' to the box that will open a ProfileDialog,
        - *showType*: use not only the profile name but also the name of the profile's type to display
          profiles in the box.
        - *selectFirstProfile*: When a profile is created after the category did not contain any profiles,
          select this profile.
    
    """
    profileChosen = QtCore.pyqtSignal(profiles.Profile)

    def __init__(self, category, restrictToType=None, default=None,
                 includeConfigure=True, showTypes=False, selectFirstProfile=True):
        super().__init__()
        self._profile = None
        self.category = category
        self.restrictToType = restrictToType
        self.includeConfigure = includeConfigure
        self.showTypes = showTypes
        self.selectFirstProfile = selectFirstProfile
        self._fillBox()
        category.profileAdded.connect(self._handleProfileAdded)
        category.profileRenamed.connect(self._fillBox)
        category.profileRemoved.connect(self._handleProfileRemoved)
        self.currentIndexChanged.connect(self._handleIndexChanged)
        
        if default is not None: 
            self.setCurrentProfile(default)
        else: self._profile = self.currentProfile() # the first one or None
    
    def profiles(self):
        """List of profiles available in the box. If self.restrictToType is not None, this may differ from
        the profiles of the underlying category."""
        if self.restrictToType is None or not isinstance(self.category, profiles.TypedProfileCategory):
            return self.category.profiles()
        else: return self.category.profiles(self.restrictToType)
    
    def _fillBox(self):
        """Fill the combobox."""
        self._reactToIndexChanges = False
        self.clear()
        for i,profile in enumerate(self.profiles()):
            if self.showTypes and profile.type is not None:
                self.addItem(self.tr("{} (type: {})").format(profile.name, profile.type.title))
            else: self.addItem(profile.name)
        self._reactToIndexChanges = True
        for i,profile in enumerate(self.profiles()):
            if profile == self._profile:
                self.setCurrentIndex(i)
                break
        else: self.setCurrentIndex(-1)
        
        if self.includeConfigure:
            if self.count() > 0: # only use a separator when it is necessary
                self.insertSeparator(self.count())
            # Note that if the box is empty so far, Qt will automatically select the 'Configure...' entry.    
            self.addItem(self.tr("Configure..."))
    
    def _handleProfileAdded(self,profile):
        """Add the profile and take care of self.selectFirstProfile."""
        self._fillBox()
        # Note that if self.restrictToType is not None, len(self.profiles) might still be None after the
        # profile has been added to the category.
        if self.selectFirstProfile and len(self.profiles()) == 1 and profile == self.profiles()[0]:
            self.setCurrentProfile(profile)
                
    def _handleProfileRemoved(self,profile):
        """Remove the given profile from the box. If it is the current one, select any other profile."""
        if profile == self._profile:
            if len(self.profiles()) > 0:
                self.setCurrentProfile(self.profiles()[0])
            else:
                self.setCurrentProfile(None)
        self._fillBox()
        
    def currentProfile(self):
        """Returns the name of the currently selected profile, or *None* if none is selected.
        The latter happens especially in the case that no profile is configured.
        """
        self._profile
    
    def setCurrentProfile(self, profile):
        """Set the current profile and emit the profileChosen-signal."""
        if profile != self._profile:
            self._profile = profile
            self._selectProfile(profile)
            self.profileChosen.emit(profile)
            
    def _selectProfile(self, profile):
        """Select the given profile in the combobox."""
        if profile is not None:
            for i in range(len(self.profiles())):
                if self.itemText(i) == profile.name:
                    self.setCurrentIndex(i)
                    break
        else: self.setCurrentIndex(-1) 
        
    def _handleIndexChanged(self, i):
        """Handle the currentIndexChanged event of this combobox."""
        if not self._reactToIndexChanges:
            return
        if 0 <= i < len(self.profiles()):
            self.setCurrentProfile(self.profiles()[i])
        elif i == -1:
            self.setCurrentProfile(None)
        elif self.includeConfigure and i == self.count()-1 and i > 0:
            # The restriction i > 0 is necessary when the last profile is removed and the remaining
            # 'Configure...' entry is selected automatically (see above).
            # If there are no profiles, the dialog is opened in mousePressEvent instead.
            self._selectProfile(self._profile) # to reset the current index
            showPreferences(self.category, self._profile)
            
    def mousePressEvent(self, event):
        """If this box contains only the entry 'Configure...', a mouse press on it must open the dialog, 
        because it is obviously not possible to trigger currentIndexChanged."""
        if self.includeConfigure and self.count() == 1 and event.button() == Qt.LeftButton:
            showPreferences(self.category)
            event.accept()
        else:
            return super().mousePressEvent(event)


class ProfileActionDialog(QtGui.QDialog):
    def __init__(self, category, parent=None, actionText=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.category = category
        self.category.profileAdded.connect(self._makeMenu)
        self.category.profileRemoved.connect(self._makeMenu)
        self.category.profileRenamed.connect(self._makeMenu)
        
        if len(category.profiles()) == 0:
            profile = category.profileClass(category.suggestProfileName())
        else: profile = category.profiles()[0].copy()
        self.configWidget = profile.configurationWidget(self)
        
        layout = QtGui.QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        topLayout = QtGui.QHBoxLayout()
        style = QtGui.QApplication.style()
        topLayout.setContentsMargins(style.pixelMetric(style.PM_LayoutLeftMargin),
                                     style.pixelMetric(style.PM_LayoutTopMargin),
                                     style.pixelMetric(style.PM_LayoutRightMargin),
                                     1)
                                       
        topLayout.addStretch(1)
        self.profileButton = QtGui.QPushButton(self.tr("Profiles..."))
        topLayout.addWidget(self.profileButton)
        self._makeMenu()
        layout.addLayout(topLayout)
        
        layout.addWidget(self.configWidget)
        
        self.layout().addStretch(1)
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel)
        if actionText is None:
            buttonBox.addButton(QtGui.QDialogButtonBox.Ok)
        else: buttonBox.addButton(actionText, QtGui.QDialogButtonBox.AcceptRole)
        self.layout().addWidget(buttonBox)
        buttonBox.rejected.connect(self.reject)
        buttonBox.accepted.connect(self.accept)
    
    def _makeMenu(self):
        """Fill the menu (only in temporary mode). This is necessary if the name of the current profile
        changes."""
        menu = QtGui.QMenu()
        for profile in self.category.profiles():
            action = menu.addAction(self.tr("Load '{}'").format(profile.name))
            action.triggered.connect(functools.partial(self._setProfile, profile))
        menu.addSeparator()
        action = menu.addAction(self.tr("Save current configuration..."))
        action.triggered.connect(self._handleSave)
        action = menu.addAction(self.tr("Configure profiles..."))
        action.triggered.connect(self._handleConfigure)
        self.profileButton.setMenu(menu)
        
    def _setProfile(self, profile):
        self.configWidget.setProfile(profile.copy())
        
    def _handleSave(self):
        dialog = SaveProfileDialog(self.category, self.configWidget.getProfile(), self)
        dialog.exec_()
        
    def _handleConfigure(self):
        showPreferences(self.category)
        
    
class SaveProfileDialog(QtGui.QDialog):
    def __init__(self, category, profile, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Save configuration as profile"))
        self.category = category
        self.profile = profile
        layout = QtGui.QVBoxLayout(self)
        
        nameLayout = QtGui.QHBoxLayout()
        nameLayout.addWidget(QtGui.QLabel(self.tr("Choose a profile name: ")))
        self.nameEdit = QtGui.QLineEdit(profile.name if profile is not None else '')
        nameLayout.addWidget(self.nameEdit)
        layout.addLayout(nameLayout)
        
        profileListLabel = QtGui.QLabel(self.tr("Or overwrite an existing profile:"))
        layout.addWidget(profileListLabel)
        self.profileList = QtGui.QListWidget()
        self.profileList.addItems([profile.name for profile in category.profiles()])
        self.profileList.itemClicked.connect(lambda item: self.nameEdit.setText(item.text()))
        if len(category.profiles()) == 0:
            profileListLabel.setEnabled(False)
            self.profileList.setEnabled(False)
        layout.addWidget(self.profileList)
        
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel)
        okButton = buttonBox.addButton(QtGui.QDialogButtonBox.Ok)
        okButton.setEnabled(len(self._getProfileName()) > 0)
        self.nameEdit.textChanged.connect(lambda: okButton.setEnabled(len(self._getProfileName()) > 0))
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        layout.addWidget(buttonBox)
        
    def _getProfileName(self):
        return self.nameEdit.text().strip()
        
    def accept(self):
        name = self._getProfileName()
        assert len(name) > 0 # button is deactivated otherwise
        
        self.profile.name = name
        oldProfile = self.category.get(name)
        if oldProfile is None:
            self.category.addProfile(self.profile.copy())
        else: self.category.changeProfile(oldProfile, self.profile)
        super().accept()
        