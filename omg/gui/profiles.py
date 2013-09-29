# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2012-2013 Martin Altmayer, Michael Helmling
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

from . import dialogs
from .. import profiles, utils

  
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
        

class ProfileDialog(QtGui.QDialog):
    """A dialog that allows to configure all profiles of a given category. Depending on the number of
    profiles in the category, it has two states:
    
        - if there is no profile it displays a form to add a profile (see NoProfileYetWidget),
        - otherwise it contains a box to select a profile a form to configure it, and button to add new
          profiles (ChooseAndConfigureProfileWidget)
          
    *profile* is the profile that is selected at the beginning.
    """
    def __init__(self, category, profile=None):
        super().__init__()
        self.setWindowTitle(self.tr("Profile Configuration: {}").format(category.title))
        self.resize(500,300)
        layout = QtGui.QVBoxLayout(self)
        layout.addWidget(ProfileConfigurationWidget(self, category, profile))
        
        
class ProfileConfigurationWidget(QtGui.QWidget):
    def __init__(self, dialog, category, profile=None):
        super().__init__()
        self.category = category
        self.category.profileAdded.connect(self._handleProfileAdded)
        self.category.profileRemoved.connect(self._handleProfileRemoved)
        
        layout = QtGui.QVBoxLayout(self)
        
        if len(category.infoText) > 0:
            label = QtGui.QLabel(category.infoText)
            label.setWordWrap(True)
            layout.addWidget(label)
        
        self.stackedWidget = QtGui.QStackedWidget()
        self.stackedWidget.addWidget(NoProfileYetWidget(self))
        self.stackedWidget.addWidget(ChooseAndConfigureProfileWidget(self, profile))
        if len(category.profiles()) > 0:
            self.stackedWidget.setCurrentIndex(1)
        layout.addWidget(self.stackedWidget)
        
    def _handleProfileAdded(self, profile):
        """Handle profileAdded-signal of the profile category."""
        self.stackedWidget.setCurrentIndex(1)
        
    def _handleProfileRemoved(self, profile):
        """Handle profileRemoved-signal of the profile category."""
        if len(self.category.profiles()) == 0:
            self.stackedWidget.setCurrentIndex(0)
        
            
class NoProfileYetWidget(QtGui.QWidget):
    """This widget is displayed in a ProfileConfigurationWidget if the underlying profile category does
    not have a profile yet."""
    def __init__(self, parent):
        super().__init__(parent)
        self.category = parent.category
        layout = QtGui.QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        
        if isinstance(self.category, profiles.TypedProfileCategory):
            if len(self.category.types) == 0:
                label = QtGui.QLabel()
                label.setWordWrap(True)
                layout.addWidget(label)
                label.setText(self.tr("There is no profile type. Probably you need to install a plugin"
                                      " that adds support for '{}'.").format(self.category.name))
                return
        
        self.createButton = QtGui.QPushButton(self.tr("Create profile"))
        self.createButton.clicked.connect(functools.partial(CreateProfileDialog.execute, self.category))
        self.createButton.setSizePolicy(QtGui.QSizePolicy.Fixed,QtGui.QSizePolicy.Fixed)
        layout.addWidget(self.createButton)
           
        layout.addStretch(1)
        frame = QtGui.QFrame()
        frame.setFrameShape(QtGui.QFrame.HLine)
        layout.addWidget(frame)
        
        buttonLayout = QtGui.QHBoxLayout()
        layout.addLayout(buttonLayout)
        buttonLayout.addStretch()
        closeButton = QtGui.QPushButton(self.tr("Close"))
        closeButton.clicked.connect(lambda: self.window().close())
        buttonLayout.addWidget(closeButton)
        

class ChooseAndConfigureProfileWidget(QtGui.QWidget):
    """This widget is displayed in a ProfileConfigurationWidget if the underlying profile category has at
    least one profile."""
    profileChosen = QtCore.pyqtSignal(profiles.Profile)
    
    def __init__(self, parent, profile=None):
        super().__init__(parent)
        self.category = parent.category
        self.category.profileAdded.connect(self.setProfile)
        self.category.profileRenamed.connect(self._handleProfileRenamed)
        
        layout = QtGui.QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        
        topLayout = QtGui.QHBoxLayout()
        layout.addLayout(topLayout)
        topLayout.addWidget(QtGui.QLabel(self.tr("Choose profile: ")))
        self.profileChooser = ProfileComboBox(self.category,
                                              default=profile,
                                              includeConfigure=False)
        self.profileChooser.profileChosen.connect(self._handleProfileChooser)
        topLayout.addWidget(self.profileChooser)
        topLayout.addStretch()
        
        self.createButton = QtGui.QPushButton(utils.getIcon('add.png'), '')
        self.createButton.clicked.connect(self._handleCreateButton)
        topLayout.addWidget(self.createButton)
        self.renameButton = QtGui.QPushButton(utils.getIcon('pencil.png'), '')
        self.renameButton.clicked.connect(self._handleRenameButton)
        topLayout.addWidget(self.renameButton)
        self.deleteButton = QtGui.QPushButton(utils.getIcon('delete.png'), '')
        self.deleteButton.clicked.connect(self._handleDeleteButton)
        topLayout.addWidget(self.deleteButton)
                
        frame = QtGui.QFrame()
        frame.setFrameShape(QtGui.QFrame.HLine)
        layout.addWidget(frame)
        self.titleLabel = QtGui.QLabel() # title will be set in setProfile
        layout.addWidget(self.titleLabel)
        
        self._profileWidgetPosition = layout.count()
           
        layout.addStretch(1)
        frame = QtGui.QFrame()
        frame.setFrameShape(QtGui.QFrame.HLine)
        layout.addWidget(frame)
        
        buttonLayout = QtGui.QHBoxLayout()
        layout.addLayout(buttonLayout)
        buttonLayout.addStretch()
        if not self.category.saveImmediately:
            self.saveButton = QtGui.QPushButton(self.tr("Save"))
            self.saveButton.clicked.connect(self._handleSaveButton)
            buttonLayout.addWidget(self.saveButton)
        closeButton = QtGui.QPushButton(self.tr("Close"))
        closeButton.clicked.connect(self._handleCloseButton)
        buttonLayout.addWidget(closeButton)
                
        self.profile = None
        self.profileWidget = None # Will be created in setProfile
        self.setProfile(profile)
        
    def setProfile(self, profile):
        """Set current profile."""
        if profile is None:
            return # widget is invisible
        if profile != self.profile:
            self.profile = profile
            self.profileChooser.setCurrentProfile(profile)
            self._updateTitleLabel()
            self.renameButton.setEnabled(not profile.builtIn)
            self.deleteButton.setEnabled(not profile.builtIn)
            self._createProfileWidget()
            
    def _handleSaveButton(self):
        if self.profileWidget is not None:
            self.profileWidget.save()
            
    def _handleCloseButton(self):
        if not self.category.saveImmediately and \
                    self.profileWidget is not None and self.profileWidget.isModified():
            if dialogs.question(self.tr("Save changes?"),
                                self.tr("The profile has been modified. Save changes?"),
                                parent=self):
                self.profileWidget.save()
        self.window().close()
                
    def _handleProfileChooser(self, profile):
        if not self.category.saveImmediately and \
                    self.profileWidget is not None and self.profileWidget.isModified():
            if dialogs.question(self.tr("Save changes?"),
                                self.tr("The profile has been modified. Save changes?"),
                                parent=self):
                self.profileWidget.save()
        self.setProfile(profile)
        
    def _updateTitleLabel(self):
        """Update the label below the profileChooser."""
        if self.profile is not None and self.profile.type is not None:
            text = self.tr("Type: {}".format(self.profile.type.title))
            self.titleLabel.setText(text)
            self.titleLabel.setVisible(True)
        else: self.titleLabel.setVisible(False)
        
    def _createProfileWidget(self):
        """Create a widget that allows to configure the current profile and insert it into the layout.
        Remove any old profile widget first."""
        if self.profileWidget is not None:
            oldSize = self.profileWidget.sizeHint()
            self.layout().removeWidget(self.profileWidget)
            self.profileWidget.setParent(None)
            self.profileWidget = None
        else: oldSize = QtCore.QSize(0,0)
        
        if self.profile is not None:
            self.profileWidget = self.profile.configurationWidget()
            if hasattr(self.profileWidget, 'modified'):
                self.saveButton.setEnabled(False)
                self.profileWidget.modified.connect(self.saveButton.setEnabled)
            if self.profileWidget is not None:
                self.layout().insertWidget(self._profileWidgetPosition, self.profileWidget, stretch=1)
                # sizeHint is not computed correctly until the event loop is entered.
                QtCore.QTimer.singleShot(0, self._resize)
                    
    def _resize(self):
        window = self.window()
        window.resize(max(window.size().width(), window.sizeHint().width()),
                      max(window.size().height(), window.sizeHint().height()))
               
    def _handleProfileRenamed(self, profile):
        """React to profileRenamed signals from the profile category."""
        if profile == self.profile:
            self._updateTitleLabel()
        
    def _handleCreateButton(self):
        """Handle the add button (which is visible only if the category does not use profile types)."""
        if not isinstance(self.category, profiles.TypedProfileCategory):
            profile = self.category.addProfile(self.category.suggestProfileName())
            self.profileChooser.setCurrentProfile(profile)
        else:
            profile = CreateProfileDialog.execute(self.category, self)
            if profile is not None:
                self.profileChooser.setCurrentProfile(profile)
                    
    def _handleRenameButton(self):
        """Ask the user for a new name of the current profile and change names."""
        text, ok = QtGui.QInputDialog.getText(self,
                                              self.tr("Profile name"),
                                              self.tr("Choose a new name"),
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
        if dialogs.question(self.tr("Delete profile"),
                            self.tr("Should the profile '{}' really be deleted?").format(self.profile.name),
                            parent=self):
            if len(self.category.profiles()) > 1:
                # Choose a different profile
                index = self.category.profiles().index(self.profile)
                newProfile = self.category.profiles()[index-1 if index > 0 else 1]
            else: newProfile = None
            profileToDelete = self.profile
            self.setProfile(newProfile)
            self.category.deleteProfile(profileToDelete)


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
            self.category.openConfigDialog(self._profile)
            
    def mousePressEvent(self, event):
        """If this box contains only the entry 'Configure...', a mouse press on it must open the dialog, 
        because it is obviously not possible to trigger currentIndexChanged."""
        if self.includeConfigure and self.count() == 1 and event.button() == Qt.LeftButton:
            self.category.openConfigDialog(None)
            event.accept()
        else:
            return super().mousePressEvent(event)
