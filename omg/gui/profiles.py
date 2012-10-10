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
    def __init__(self,category,profile):
        super().__init__()
        self.category = category
        category.profileRenamed.connect(self._handleProfileRenamed)
        self.setWindowTitle(self.tr("Profile Configuration: {}").format(category.title))
        layout = QtGui.QVBoxLayout(self)
        
        self.topLayout = QtGui.QHBoxLayout()
        layout.addLayout(self.topLayout)
        self.topLayout.addWidget(QtGui.QLabel(self.tr("Choose a profile: ")))
        self.profileChooser = ProfileComboBox(category,
                                              default=profile,
                                              includeConfigure=False)
        self.profileChooser.profileChosen.connect(self.setProfile)
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
        configLayout.addStretch()
        
        self.profileWidget = None # Will be created in setProfile
        
        self.setProfile(profile)
        
    def getProfile(self):
        return self.profileChooser.currentProfile()
            
    def setProfile(self,profile):
        self.profileChooser.setCurrentProfile(profile)
        self._updateTitleLabel()
        self.renameButton.setEnabled(profile is not None)
        self.deleteButton.setEnabled(profile is not None)
        self._createProfileWidget()
        
    def _updateTitleLabel(self):
        profile = self.getProfile()
        if profile is not None:
            self.titleLabel.setText(self.tr("Configure {}").format(profile.name))
        else: self.titleLabel.setText(self.tr("Configure"))
        
    def _createProfileWidget(self):
        if self.profileWidget is not None:
            self.layout().removeWidget(self.profileWidget)
            self.profileWidget.setParent(None)
        if self.getProfile() is not None:
            self.profileWidget = self.getProfile().configurationWidget()
            if self.profileWidget is not None:
                self.layout().insertWidget(4,self.profileWidget,stretch=1)
                
    def _handleProfileRenamed(self,profile):
        if profile == self.getProfile():
            self._updateTitleLabel()
        
    def _handleAddButton(self):
        text,ok = QtGui.QInputDialog.getText(self,self.tr("Profile name"),self.tr("Choose a profile name"))
        if ok and len(text) > 0:
            if self.category.get(text) is not None:
                dialogs.warning(self.tr("Invalid name"),self.tr("There is already a profile of this name."))
            else:
                profile = self.category.addProfile(text)
                self.setProfile(profile)
                
    def _handleAddBox(self,index):
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
    """This class provides a combo box that lets the user choose a profile."""
    
    profileChosen = QtCore.pyqtSignal(Profile)

    def __init__(self, profileCategory, restrictToType=None, default=None,
                 includeConfigure=True, showTypes=False, parent=None):
        super().__init__(parent)
        self.profileCategory = profileCategory
        self.includeConfigure = includeConfigure
        self.showTypes = showTypes
        self._storedProfile = None
        self._fillBox()
        profileCategory.profileAdded.connect(self._fillBox)
        profileCategory.profileRenamed.connect(self._fillBox)
        profileCategory.profileRemoved.connect(self._handleProfileRemoved)
        self.currentIndexChanged.connect(self._handleIndexChanged)
        
        if default is not None: 
            self.setCurrentProfile(default)
        else: self._storedProfile = self.currentProfile() # the first one or None
    
    def _fillBox(self):
        self._reactToIndexChanges = False
        self.clear()
        for i,profile in enumerate(self.profileCategory.profiles):
            if self.showTypes and profile.type is not None:
                self.addItem(self.tr("{} (type: {})").format(profile.name,profile.type.title))
            else: self.addItem(profile.name)
        self._reactToIndexChanges = True
        for i,profile in enumerate(self.profileCategory.profiles):
            if profile == self._storedProfile:
                self.setCurrentIndex(i)
                break
        else: self.setCurrentIndex(-1)
        
        if self.includeConfigure:
            if self.count() > 1: # only use a separator when it is necessary
                self.insertSeparator(self.count())
            self.addItem(self.tr("Configure..."))
            
    def _handleProfileRemoved(self,profile):
        if profile == self._storedProfile:
            self.setCurrentProfile(None)
        self._fillBox()
        
    def currentProfile(self):
        """Returns the name of the currently selected profile, or *None* if none is selected.
        The latter happens especially in the case that no profile is configured.
        """
        if -1 < self.currentIndex() < len(self.profileCategory.profiles):
            return self.profileCategory.profiles[self.currentIndex()]
        else: return None
    
    def setCurrentProfile(self, profile):
        if profile is not None:
            for i in range(self.count()):
                if self.itemText(i) == profile.name:
                    self.setCurrentIndex(i)
                    break
        else: self.setCurrentIndex(-1)  
        if profile != self._storedProfile:
            self._storedProfile = profile
            self.profileChosen.emit(profile)
                   
    def _handleIndexChanged(self, i):
        if not self._reactToIndexChanges:
            return
        if 0 <= i < len(self.profileCategory.profiles):
            self.setCurrentProfile(self.profileCategory.profiles[i])
        elif i == -1:
            self.setCurrentProfile(None)
        else:
            self.setCurrentProfile(self._storedProfile) # to reset the current index
            self.profileCategory.openConfigDialog(self._storedProfile)
            
    def mousePressEvent(self, event):
        if self.includeConfigure and self.count() == 1 and event.button() == Qt.LeftButton:
            self.profileCategory.openConfigDialog(None)
            event.accept()
        else:
            return super().mousePressEvent(event)
