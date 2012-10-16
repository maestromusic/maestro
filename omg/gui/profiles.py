# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2012 Martin Altmayer, Michael Helmling
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


from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import dialogs 
from ..profiles import Profile


class ProfileDialog(QtGui.QDialog):
    """A dialog that contains a ProfileConfigurationWidget."""
    def __init__(self,category,profile=None):
        super().__init__()
        layout = QtGui.QVBoxLayout(self)
        
        layout.addWidget(ProfileConfigurationWidget(category,profile))
        layout.addStretch()
        
        frame = QtGui.QFrame()
        frame.setFrameShape(QtGui.QFrame.HLine)
        layout.addWidget(frame)
        
        self.buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Close)
        self.buttonBox.rejected.connect(self.accept)
        layout.addWidget(self.buttonBox)
        
        
class ProfileConfigurationWidget(QtGui.QWidget):
    """A widget that allows to configure all profiles of a given category. It contains some buttons
    to add/rename/delete profiles and the widget returned by the current profile's configurationWidget
    method.
    *profile* is the profile that is selected at the beginning.
    """
    profileChosen = QtCore.pyqtSignal(Profile)
    
    def __init__(self,category,profile=None):
        super().__init__()
        self.category = category
        category.profileRenamed.connect(self._handleProfileRenamed)
        self.setWindowTitle(self.tr("Profile Configuration: {}").format(category.title))
        layout = QtGui.QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        
        self.topLayout = QtGui.QHBoxLayout()
        layout.addLayout(self.topLayout)
        self.topLayout.addWidget(QtGui.QLabel(self.tr("Choose a profile: ")))
        self.profileChooser = ProfileComboBox(category,
                                              default=profile,
                                              includeConfigure=False)
        self.profileChooser.profileChosen.connect(self.setProfile)
        self.profileChooser.profileChosen.connect(self.profileChosen)
        self.topLayout.addWidget(self.profileChooser)
        if len(self.category.types) == 0:
            self.addButton = QtGui.QPushButton(self.tr("Add new profile"))
            self.addButton.clicked.connect(self._handleAddButton)
            self.topLayout.addWidget(self.addButton)
        else:
            self.addBox = QtGui.QComboBox()
            self.addBox.addItem(self.tr("Add new profile"))
            for type in self.category.types:
                self.addBox.addItem(self.tr("...of type {}").format(type.title))
            self.addBox.currentIndexChanged.connect(self._handleAddBox)
            self.topLayout.addWidget(self.addBox)
        
        self.topLayout.addStretch()
        
        self.frame = QtGui.QFrame()
        self.frame.setFrameShape(QtGui.QFrame.HLine)
        layout.addWidget(self.frame)
        self.titleLabel = QtGui.QLabel() # title will be set in setProfile
        layout.addWidget(self.titleLabel)
        
        configLayout = QtGui.QHBoxLayout()
        layout.addLayout(configLayout)
        self.renameButton = QtGui.QPushButton(self.tr("Rename"))
        self.renameButton.clicked.connect(self._handleRenameButton)
        configLayout.addWidget(self.renameButton)
        self.deleteButton = QtGui.QPushButton(self.tr("Delete"))
        self.deleteButton.clicked.connect(self._handleDeleteButton)
        configLayout.addWidget(self.deleteButton)
        self.builtInLabel = QtGui.QLabel(self.tr("(built-in profile)"))
        configLayout.addWidget(self.builtInLabel)
        configLayout.addStretch()
        
        layout.addStretch()
        
        self.profileWidget = None # Will be created in setProfile
        
        if profile is None and len(category.profiles) > 0:
            profile = category.profiles[0]
        self.setProfile(profile)
        
    def getProfile(self):
        """Return current profile."""
        # once this returned self.profileChooser.currentProfile(). But this created problems when a profile
        # was deleted and the contents of the profileChooser and the current profile changed at the same
        # time.
        return self.profile
            
    def setProfile(self,profile):
        """Set current profile."""
        if not hasattr(self,'profile') or profile != self.profile:
            self.profile = profile
            self.profileChooser.setCurrentProfile(profile)
            self.frame.setVisible(profile is not None)
            self._updateTitleLabel()
            self.titleLabel.setVisible(profile is not None)
            enable = profile is not None and not profile.builtIn
            self.renameButton.setVisible(profile is not None)
            self.renameButton.setEnabled(enable)
            self.deleteButton.setVisible(profile is not None)
            self.deleteButton.setEnabled(enable)
            self.builtInLabel.setVisible(profile is not None and not enable)
            self._createProfileWidget()
        
    def _updateTitleLabel(self):
        """Update the label below the profileChooser."""
        profile = self.getProfile()
        if profile is not None:
            self.titleLabel.setText(self.tr("Configure {}").format(profile.name))
        else: self.titleLabel.setText(self.tr("Configure"))
        
    def _createProfileWidget(self):
        """Create a widget that allows to configure the current profile and insert it into the layout.
        Remove any old profile widget first."""
        if self.profileWidget is not None:
            self.layout().removeWidget(self.profileWidget)
            self.profileWidget.setParent(None)
            self.profileWidget = None
        if self.getProfile() is not None:
            self.profileWidget = self.getProfile().configurationWidget()
            if self.profileWidget is not None:
                self.layout().insertWidget(4,self.profileWidget,stretch=1)
                
    def _handleProfileRenamed(self,profile):
        """React to profileRenamed signals from the profile category."""
        if profile == self.getProfile():
            self._updateTitleLabel()
        
    def _handleAddButton(self):
        """Handle the add button (which is visible only if the category does not use profile types)."""
        text,ok = QtGui.QInputDialog.getText(self,
                                             self.tr("Add new profile"),
                                             self.tr("Choose a profile name"))
        if ok and len(text) > 0:
            if self.category.get(text) is not None:
                dialogs.warning(self.tr("Invalid name"),self.tr("There is already a profile of this name."))
            else:
                profile = self.category.addProfile(text)
                self.setProfile(profile)
                
    def _handleAddBox(self,index):
        """Handle the add button combobox (which is visible only if the category uses profile types)."""
        if index <= 0:
            return # first line does not contain a type
        self.addBox.setCurrentIndex(0) # reset
        type = self.category.types[index-1]
        text,ok = QtGui.QInputDialog.getText(self,self.tr("Profile name"),self.tr("Choose a profile name"))
        if ok and len(text) > 0:
            if self.category.get(text) is not None:
                dialogs.warning(self.tr("Invalid name"),self.tr("There is already a profile of this name."))
            else:
                profile = self.category.addProfile(text,type)
                self.setProfile(profile)
        
    def _handleRenameButton(self):
        """Ask the user for a new name of the current profile and change names."""
        text,ok = QtGui.QInputDialog.getText(self,self.tr("Profile name"),
                                             self.tr("Choose a new name"),
                                             text=self.getProfile().name)
        if ok and len(text) > 0:
            existingProfile = self.category.get(text)
            if existingProfile == self.getProfile():
                return # no change
            elif existingProfile is not None:
                dialogs.warning(self.tr("Invalid name"),self.tr("There is already a profile of this name."))
            else:
                self.category.renameProfile(self.getProfile(),text)
                
    def _handleDeleteButton(self):
        """Ask the user again and delete the current profile."""
        profile = self.getProfile()
        if dialogs.question(self.tr("Delete profile"),
                            self.tr("Should the profile '{}' really be deleted?").format(profile.name)):
            if len(self.category.profiles) > 1:
                index = self.category.profiles.index(profile)
                newProfile = self.category.profiles[index-1 if index > 0 else 1]
            else: newProfile = None
            self.setProfile(newProfile)
            self.category.deleteProfile(profile)


class ProfileComboBox(QtGui.QComboBox):
    """This class provides a combo box that lets the user choose a profile. Parameters are
    
        - *profileCategory*: The category where the profiles are taken from,
        - *restrictToType*: if this is not None, the user may only choose profiles of this profile type,
        - *default*: the profile that is selected at the beginning,
        - *includeConfigure*: Add an entry 'Configure...' to the box that will open a ProfileDialog,
        - *showType*: use not only the profile name but also the name of the profile's type to display
          profiles in the box.
    
    """
    profileChosen = QtCore.pyqtSignal(Profile)

    def __init__(self, profileCategory, restrictToType=None, default=None,
                 includeConfigure=True, showTypes=False):
        super().__init__()
        self._profile = None
        self.profileCategory = profileCategory
        self.restrictToType = restrictToType
        self.includeConfigure = includeConfigure
        self.showTypes = showTypes
        self._fillBox()
        profileCategory.profileAdded.connect(self._fillBox)
        profileCategory.profileRenamed.connect(self._fillBox)
        profileCategory.profileRemoved.connect(self._handleProfileRemoved)
        self.currentIndexChanged.connect(self._handleIndexChanged)
        
        if default is not None: 
            self.setCurrentProfile(default)
        else: self._profile = self.currentProfile() # the first one or None
    
    def profiles(self):
        """List of profiles available in the box. If self.restrictToType is not None, this may differ from
        the profiles of the underlying category."""
        if self.restrictToType is None:
            return self.profileCategory.profiles
        else: return [p for p in self.profileCategory.profiles if p.type == self.restrictToType]
    
    def _fillBox(self):
        """Fill the combobox."""
        self._reactToIndexChanges = False
        self.clear()
        for i,profile in enumerate(self.profiles()):
            if self.showTypes and profile.type is not None:
                self.addItem(self.tr("{} (type: {})").format(profile.name,profile.type.title))
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
            self.profileCategory.openConfigDialog(self._profile)
            
    def mousePressEvent(self, event):
        """If this box contains only the entry 'Configure...', a mouse press on it must open the dialog, 
        because it is obviously not possible to trigger currentIndexChanged."""
        if self.includeConfigure and self.count() == 1 and event.button() == Qt.LeftButton:
            self.profileCategory.openConfigDialog(None)
            event.accept()
        else:
            return super().mousePressEvent(event)
