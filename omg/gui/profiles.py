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
from .. import profiles


class ProfileDialog(QtGui.QDialog):
    """A dialog that contains a ProfileConfigurationWidget."""
    def __init__(self,category,profile=None):
        super().__init__()
        layout = QtGui.QVBoxLayout(self)
        self.setWindowTitle(self.tr("Profile Configuration: {}").format(category.title))
        
        layout.addWidget(ProfileConfigurationWidget(category,profile))
        layout.addStretch()
        
        frame = QtGui.QFrame()
        frame.setFrameShape(QtGui.QFrame.HLine)
        layout.addWidget(frame)
        
        self.buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Close)
        self.buttonBox.rejected.connect(self.accept)
        layout.addWidget(self.buttonBox)
                         
        
class ProfileConfigurationWidget(QtGui.QStackedWidget):
    """A widget that allows to configure all profiles of a given category. Depending on the number of
    profiles in the category, it has two states:
    
        - if there is no profile it displays a form to add a profile (see NoProfileYetWidget),
        - otherwise it contains a box to select a profile a form to configure it, and button to add new
          profiles (ChooseAndConfigureProfileWidget)
          
    *profile* is the profile that is selected at the beginning.
    """
    profileChosen = QtCore.pyqtSignal(profiles.Profile)
    
    def __init__(self,category,profile=None):
        super().__init__()
        self.category = category
        self.category.profileAdded.connect(self._handleProfileAdded)
        self.category.profileRemoved.connect(self._handleProfileRemoved)
        if profile is None and len(category.profiles) > 0:
            profile = category.profiles[0]
        
        self.addWidget(NoProfileYetWidget(self))
        self.addWidget(ChooseAndConfigureProfileWidget(self,profile))
        if len(category.profiles) > 0:
            self.setCurrentIndex(1)
        
    def _handleProfileAdded(self,profile):
        """Handle profileAdded-signal of the profile category."""
        self.setCurrentIndex(1)
        
    def _handleProfileRemoved(self,profile):
        """Handle profileRemoved-signal of the profile category."""
        if len(self.category.profiles) == 0:
            self.setCurrentIndex(0)
        
        
class NoProfileYetWidget(QtGui.QWidget):
    """This widget is displayed in a ProfileConfigurationWidget if the underlying profile category does
    not have a profile yet."""
    def __init__(self,parent):
        super().__init__(parent)
        self.category = parent.category
        
        layout = QtGui.QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
         
        if isinstance(self.category,profiles.TypedProfileCategory):
            label = QtGui.QLabel(
                        self.tr("There is no profile yet. To create one, choose a name and a type:"))
        else: label = QtGui.QLabel(self.tr("There is no profile yet. To create one, choose a name:"))
        label.setWordWrap(True)
        layout.addWidget(label)
        hLayout = QtGui.QHBoxLayout() # hLayout prevents the form widgets to stretch over the whole width
        layout.addLayout(hLayout)
        formLayout = QtGui.QFormLayout()
        formLayout.setSizeConstraint(QtGui.QLayout.SetFixedSize)
        hLayout.addLayout(formLayout)
        hLayout.addStretch(1)
        self.nameLineEdit = QtGui.QLineEdit()
        if not isinstance(self.category,profiles.TypedProfileCategory):
            self.nameLineEdit.setText(self.category.suggestProfileName())
        formLayout.addRow(self.tr("Name:"),self.nameLineEdit)
        if isinstance(self.category,profiles.TypedProfileCategory):
            self.typeBox = QtGui.QComboBox()
            self.typeBox.addItems([type.title for type in self.category.types])
            formLayout.addRow(self.tr("Type:"),self.typeBox)
        
        self.addButton = QtGui.QPushButton(self.tr("Add profile"))
        self.addButton.clicked.connect(self._handleAddButton)
        self.addButton.setSizePolicy(QtGui.QSizePolicy.Fixed,QtGui.QSizePolicy.Fixed)
        layout.addWidget(self.addButton)
        
        layout.addStretch(1)        
        
    def _handleAddButton(self):
        """Check the data in the input fields and add a new profile."""
        name = self.nameLineEdit.text()
        if isinstance(self.category,profiles.TypedProfileCategory):
            type = self.category.types[self.typeBox.currentIndex()]
        else: type = None
        
        if len(name) == 0:
            return
        
        if self.category.get(name) is not None:
            dialogs.warning(self.tr("Invalid name"),self.tr("There is already a profile of this name."))
        else:
            self.category.addProfile(name,type)
            # reset the fields for the next time this widget is shown)
            if isinstance(self.category, profiles.TypedProfileCategory):
                self.nameLineEdit.setText('')
                self.typeBox.setCurrentIndex(0)
            else:
                self.nameLineEdit.setText(self.category.suggestProfileName())
                

class ChooseAndConfigureProfileWidget(QtGui.QWidget):
    """This widget is displayed in a ProfileConfigurationWidget if the underlying profile category has at
    least one profile."""
    def __init__(self,parent,profile):
        super().__init__(parent)
        self.category = parent.category
        self.category.profileAdded.connect(self.setProfile)
        self.category.profileRenamed.connect(self._handleProfileRenamed)
        
        layout = QtGui.QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        
        topLayout = QtGui.QHBoxLayout()
        layout.addLayout(topLayout)
        topLayout.addWidget(QtGui.QLabel(self.tr("Choose a profile: ")))
        self.profileChooser = ProfileComboBox(self.category,
                                              default=profile,
                                              includeConfigure=False)
        self.profileChooser.profileChosen.connect(self.setProfile)
        self.profileChooser.profileChosen.connect(parent.profileChosen)
        topLayout.addWidget(self.profileChooser)
        if isinstance(self.category,profiles.TypedProfileCategory):
            self.addBox = QtGui.QComboBox()
            self.addBox.addItem(self.tr("Add new profile"))
            for type in self.category.types:
                self.addBox.addItem(self.tr("...of type {}").format(type.title))
            self.addBox.currentIndexChanged.connect(self._handleAddBox)
            topLayout.addWidget(self.addBox)
        else:
            self.addButton = QtGui.QPushButton(self.tr("Add new profile"))
            self.addButton.clicked.connect(self._handleAddButton)
            topLayout.addWidget(self.addButton)
        
        topLayout.addStretch()
        
        frame = QtGui.QFrame()
        frame.setFrameShape(QtGui.QFrame.HLine)
        layout.addWidget(frame)
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
        
        self.profile = None
        self.profileWidget = None # Will be created in setProfile
        self.setProfile(profile)
        
    def setProfile(self,profile):
        """Set current profile."""
        if profile is None:
            return # widget is invisible
        if profile != self.profile:
            self.profile = profile
            self.profileChooser.setCurrentProfile(profile)
            self._updateTitleLabel()
            self.renameButton.setEnabled(not profile.builtIn)
            self.deleteButton.setEnabled(not profile.builtIn)
            self.builtInLabel.setVisible(profile.builtIn)
            self._createProfileWidget()
        
    def _updateTitleLabel(self):
        """Update the label below the profileChooser."""
        if self.profile is not None:
            if self.profile.type is not None:
                text = self.tr("Configure {} of type {}").format(self.profile.name,self.profile.type.title)
            else: text = self.tr("Configure {}").format(self.profile.name)
        else: text = self.tr("Configure")
        self.titleLabel.setText(text)
        
    def _createProfileWidget(self):
        """Create a widget that allows to configure the current profile and insert it into the layout.
        Remove any old profile widget first."""
        if self.profileWidget is not None:
            self.layout().removeWidget(self.profileWidget)
            self.profileWidget.setParent(None)
            self.profileWidget = None
        if self.profile is not None:
            self.profileWidget = self.profile.configurationWidget()
            if self.profileWidget is not None:
                self.layout().insertWidget(4,self.profileWidget,stretch=1)
                
    def _handleProfileRenamed(self,profile):
        """React to profileRenamed signals from the profile category."""
        if profile == self.profile:
            self._updateTitleLabel()
        
    def _handleAddButton(self):
        """Handle the add button (which is visible only if the category does not use profile types)."""
        text,ok = QtGui.QInputDialog.getText(self,
                                             self.tr("Add new profile"),
                                             self.tr("Choose a profile name"),
                                             QtGui.QLineEdit.Normal,
                                             self.category.suggestProfileName())
        if ok and len(text) > 0:
            self._tryAddProfile(text,None)
                
    def _handleAddBox(self,index):
        """Handle the add button combobox (which is visible only if the category uses profile types)."""
        if index <= 0:
            return # first line does not contain a type
        self.addBox.setCurrentIndex(0) # reset
        type = self.category.types[index-1]
        text,ok = QtGui.QInputDialog.getText(self,
                                             self.tr("Profile name"),
                                             self.tr("Choose a profile name"),
                                             QtGui.QLineEdit.Normal,
                                             self.category.suggestProfileName(type))
        if ok and len(text) > 0:
            self._tryAddProfile(text, type)
            
    def _tryAddProfile(self,name,type):
        """Check whether *name* is valid and add a new profile with this name and type."""
        if self.category.get(name) is not None:
            dialogs.warning(self.tr("Invalid name"),self.tr("There is already a profile of this name."))
        else:
            self.category.addProfile(name,type)
                    
    def _handleRenameButton(self):
        """Ask the user for a new name of the current profile and change names."""
        text,ok = QtGui.QInputDialog.getText(self,self.tr("Profile name"),
                                             self.tr("Choose a new name"),
                                             text=self.profile.name)
        if ok and len(text) > 0:
            existingProfile = self.category.get(text)
            if existingProfile == self.profile:
                return # no change
            elif existingProfile is not None:
                dialogs.warning(self.tr("Invalid name"),self.tr("There is already a profile of this name."))
            else:
                self.category.renameProfile(self.profile,text)
                
    def _handleDeleteButton(self):
        """Ask the user again and delete the current profile."""
        if dialogs.question(self.tr("Delete profile"),
                            self.tr("Should the profile '{}' really be deleted?").format(self.profile.name)):
            if len(self.category.profiles) > 1:
                # Choose a different profile
                index = self.category.profiles.index(self.profile)
                newProfile = self.category.profiles[index-1 if index > 0 else 1]
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
        if self.restrictToType is None or not isinstance(self.category,profiles.TypedProfileCategory):
            return self.category.profiles
        else: return [p for p in self.category.profiles if p.type == self.restrictToType]
    
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
