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


# This module provides a system to manage configuration profiles in OMG. 

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from . import config, logging
import collections

logger = logging.getLogger(__name__)

class ProfileConfiguration(QtCore.QObject):
    """A class for managing configurations which are organized profiles.
    
    Provides methods to add, remove and modify profiles, signals for such
    changes, and more."""
    
    profileModified = QtCore.pyqtSignal(str)
    profileRenamed  = QtCore.pyqtSignal(str, str) # oldName, newName
    profileRemoved  = QtCore.pyqtSignal(str) # name 
    profileAdded    = QtCore.pyqtSignal(str)
    
    classAdded = QtCore.pyqtSignal(str)
    classRemoved = QtCore.pyqtSignal(str)
    
    def __init__(self, name, configSection, profileClasses = None):
        super().__init__()
        self.name = name
        self.classes = {}
        if profileClasses is not None:
            for cls in profileClasses:
                self.classes[cls.className] = cls
        self.configSection = configSection
        self.profiles = collections.OrderedDict()
        
    def loadConfig(self):
        for name, clsName, *config in self.configSection["profiles"]:
            if clsName in self.classes:
                self.profiles[name] = self.classes[clsName](name, *config)
                print('initalized profile {} with *config={}'.format(name, config))
                
            else:
                logger.warning("could not load {} profile {}: class {} not found".format(self.name, name, clsName))
    
    def saveConfig(self):
        configContents = []
        for name, profile in self.profiles.items():
            configContents.append( (name, profile.className) + tuple(profile.config())  )
        self.configSection["profiles"] = configContents
        print(self.configSection["profiles"])
            
    def addClass(self, cls):
        if cls.className not in self.classes:
            self.classes[cls.className] = cls
            # load profiles for this class
            for name, className, *config in self.configSection["profiles"]:
                if className == cls.className:
                    self.profiles[name] = self.classes[className](name, *config)
                    print('initalized profile {} with *config={}'.format(name, config))
            self.classAdded.emit(cls.className)
    
    def removeClass(self, cls):
        if cls.className in self.classes:
            toRemove = [ name for name,profile in self.profiles.items() if profile.className == cls.className ]
            for name in toRemove:
                self.removeProfile(name)
            self.classRemove.emit(cls.className)
    
    def newProfile(self, name = None, className = None):
        if name is None:
            name = self.tr("newProfile")
        while name in self.profiles:
            name += "_"
        if className is None:
            className = next(iter(self.classes))
        self.profiles[name] = self.classes[className](name)
        self.saveConfig()
        self.profileAdded.emit(name)
    
    def removeProfile(self, name):
        del self.profiles[name]
        self.saveConfig()
        self.profileRemoved.emit(name)
    
    def renameProfile(self, oldName, newName):
        self.profiles = collections.OrderedDict((newName if n==oldName else n, p) for n, p in self.profiles.items() )
        self.saveConfig()
        self.profileRenamed.emit(oldName, newName)
    
    def modifyProfile(self, name, className, config):
        self.profiles[name] = self.classes[className](name, *config)
        self.saveConfig()
        self.profileModified.emit(name)
    
    def profileChooser(self, *args, **kwargs):
        """Creates a profile combo box for this configuration. All other arguments
        of the ProfileComboBox constructor may be passed."""
        return ProfileComboBox(self, *args, **kwargs)
    
    def configurationDisplay(self, currentProfile = None, parent = None):
        return ProfileConfigurationDisplay(self, currentProfile, parent)
    
    def __contains__(self, name):
        return self.profiles.__contains__(name)
        
    def __getitem__(self, name):
        """For convenience, you can access the ProfileConfiguration directly to obtain a profile by its name."""
        return self.profiles[name]
    
    def openConfigDialog(self, currentProfile = None):
        dialog = ProfileConfigurationDialog(self, currentProfile)
        dialog.exec_()
        
             
class Profile(QtCore.QObject):
    """Base class for a profile implementation. """
    className = "undefined"
    def __init__(self, name):
        super().__init__()
        self.name = name
    
    def config(self):
        """Return the configuration of the current profile, which, passed to the constructor,
        yield an equivalent profile."""
        raise NotImplementedError()
    
    @classmethod   
    def configurationWidget(cls, profile = None):
        """Return a widget for configuring profiles of this class. If *profile* is not None, it
        is the name of the initial profile."""
        raise NotImplementedError()

class ConfigurationWidget(QtGui.QWidget):
    
    temporaryModified = QtCore.pyqtSignal(object)
    
    def currentConfig(self):
        """Returns the current configuration represented by the state of the widget.
        
        Subclasses must implement this method; it should return a tuple of data suitable
        to pass to the Profile's constructor"""
        raise NotImplementedError()
    
class ClassComboBox(QtGui.QComboBox):
    """This class provides a combo box for choosing a profile implementation class."""
    
    classChosen = QtCore.pyqtSignal(str)
    def __init__(self, profileConf, default = None, parent = None):
        super().__init__(parent)
        for name in profileConf.classes:
            self.addItem(name)
        self.supressEvent = False
        profileConf.classAdded.connect(self.addItem)
        profileConf.classRemoved.connect(self.handleClassRemoved)
        self.currentIndexChanged[str].connect(lambda name: self.classChosen(name) if self.supressEvent else None)
        
    def handleClassRemoved(self, name):
        for i in range(self.count()):
            if self.itemText(i) == name:
                self.removeItem(i)
                #TODO: handle removal of current profile: change current profile
                break
    
    def setCurrentClass(self, name, emit = True):
        for i in range(self.count()):
            if self.itemText(i) == name:
                if not emit:
                    self.supressEvent = True
                self.setCurrentIndex(i)
                self.supressEvent = False
                return True
        return False  
    
        
class ProfileComboBox(QtGui.QComboBox):
    """This class provides a combo box that lets the user choose a profile."""
    
    profileChosen = QtCore.pyqtSignal(str)

    def __init__(self, profileConf, default = None, includeConfigure = True, parent = None):
        super().__init__(parent)
        for name in profileConf.profiles:
            self.addItem(name)
        self.includeConfigure = includeConfigure
        if includeConfigure:
            self.addItem(self.tr("configure..."))
            self.view().activated.connect(lambda idx: print(idx.row()))
        profileConf.profileAdded.connect(self.handleProfileAdded)
        self.currentIndexChanged[int].connect(self.handleIndexChange)
        self.activated[int].connect(self.handleActivation)
        profileConf.profileRenamed.connect(self.handleProfileRenamed)
        profileConf.profileRemoved.connect(self.handleProfileRemoved)
        
        self.lastProfile = None
        self.profileConf = profileConf
        if default:
            self.setCurrentProfile(default, False)
        if self.profileCount() > 0:
            self.storedProfile = self.currentProfileName()
            
    def profileCount(self):
        if self.includeConfigure:
            return self.count()-1
        else:
            return self.count()
        
    def currentProfile(self):
        """Returns the currently selected profile, or *None* if none is selected.
        
        The latter happens especially in the case that no profile is configured."""
        name = self.currentProfileName()
        if name is None:
            return None
        else:
            return self.profileConf[name]
    
    def currentProfileName(self):
        """Returns the name of the currently selected profile, or *None* if none is selected.
        
        The latter happens especially in the case that no profile is configured."""
        if self.includeConfigure and self.currentIndex() == self.count()-1:
            return None
        return self.currentText()
    
    def setCurrentProfile(self, name, emit = True):
        self.storedProfile = name
        for i in range(self.profileCount()):
            if self.itemText(i) == name:
                self.setCurrentIndex(i)
                return True
        return False
                   
    def handleIndexChange(self, i):
        if i == -1:
            self.profileChosen.emit('')
            return
        if i != self.profileCount():
            self.profileChosen.emit(self.itemText(i))
            self.storedProfile = self.itemText(i)

    def handleActivation(self, i):
        if self.includeConfigure and i == self.profileCount():
            self.profileConf.openConfigDialog(self.storedProfile)
            self.setCurrentProfile(self.storedProfile, False)
            
    def mousePressEvent(self, event):
        if self.includeConfigure and self.count() == 1 and event.button() == Qt.LeftButton:
            self.profileConf.openConfigDialog(None)
            event.accept()
        else:
            return super().mousePressEvent(event)
    
    def handleProfileAdded(self, name):
        self.insertItem(self.profileCount(), name)
        if self.profileCount() == 1 and self.includeConfigure:
            self.setCurrentProfile(name)
    
    def handleProfileRenamed(self, old, new):
        if self.storedProfile == old:
            self.storedProfile = new
        for i in range(self.profileCount()):
            if self.itemText(i) == old:               
                self.setItemText(i, new)
                if i == self.currentIndex():
                    self.profileChosen.emit(new)
                break
    
    def handleProfileRemoved(self, name):
        for i in range(self.profileCount()):
            if self.itemText(i) == name:
                self.removeItem(i)
                break
            
class ProfileConfigurationDisplay(QtGui.QWidget):
    """A widget containing all the necessary bits to configure a profile. This is used
    in the ProfileConfigurationDialog, but may also be used in custom dialogs which allow
    to edit and use a profile in one step."""
    temporaryModified = QtCore.pyqtSignal(object)
    profileChanged = QtCore.pyqtSignal(str)
    
    def __init__(self, profileConf, currentProfile = None, parent = None):
        super().__init__(parent)
        self.profileConf = profileConf
        topLayout = QtGui.QHBoxLayout()
        topLayout.addWidget(QtGui.QLabel("Profile:"), 0)
        self.profileChooser = ProfileComboBox(profileConf, currentProfile, includeConfigure = False)
        self.newButton = QtGui.QPushButton(self.tr("New"))
        self.removeButton = QtGui.QPushButton(self.tr("Remove"))
        topLayout.addWidget(self.profileChooser,10)
        topLayout.addStretch(3)
        topLayout.addWidget(self.newButton,0)
        topLayout.addWidget(self.removeButton,0)
        self.secondLayout = QtGui.QHBoxLayout()
        self.secondLayout.setAlignment(Qt.AlignLeft)
        self.secondLayout.addWidget(QtGui.QLabel(self.tr("Name:")),0)
        self.nameEdit = QtGui.QLineEdit()
        self.secondLayout.addWidget(self.nameEdit,7)
        self.secondLayout.addStretch(7)
        self.saveButton = QtGui.QPushButton(QtGui.qApp.style().standardIcon(QtGui.QStyle.SP_DialogSaveButton), "")
        self.saveButton.setIconSize(QtCore.QSize(16,16))
        self.secondLayout.addWidget(self.saveButton,0)
        self.classChooser = ClassComboBox(profileConf)
        if len(self.profileConf.classes) > 1:
            self.enableClassChooser()
        
        self.newButton.clicked.connect(self.handleNewProfile)
        self.removeButton.clicked.connect(self.handleRemoveProfile)
        self.saveButton.clicked.connect(self.handleSaveProfile)
        self.profileChooser.profileChosen.connect(self.setProfile)
            
        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addLayout(topLayout)
        mainLayout.addLayout(self.secondLayout)
        self.configWidget  = None
        self.setLayout(mainLayout)
        self.mainLayout = mainLayout
        
        self.currentProfileName = self.profileChooser.currentProfileName
        self.setProfile(self.profileChooser.currentProfileName())
    
    def handleNewProfile(self):
        self.profileConf.newProfile()
        self.setProfile(list(self.profileConf.profiles.keys())[-1])
    
    def handleRemoveProfile(self):
        self.profileConf.removeProfile(self.profileChooser.currentProfileName())
    
    def handleSaveProfile(self):
        if self.nameEdit.text() == '':
            from .gui import dialogs
            dialogs.warning(self.tr('Invalid Profile Name'), self.tr("The profile must have a non-empty name"))
        else:
            currentProfile = self.profileChooser.currentProfileName()
            newName = str(self.nameEdit.text())
            if currentProfile != '':
                if newName != currentProfile:
                    if newName in self.profileConf:
                        ans = dialogs.question(self.tr('Overwrite profile?'),
                                         self.tr('A profile named "{}" already exists. Do you want to overwrite it?'))
                        if ans:
                            self.profileConf.removeProfile(newName)
                        else:
                            return
                    self.profileConf.renameProfile(currentProfile, newName)
                self.profileConf.modifyProfile(newName, self.classChooser.currentText(), self.configWidget.currentConfig())
            else:
                self.profileConf.newProfile(newName, self.classChooser.currentText(), self.configWidget.currentConfig())
            
            
    def setProfile(self, name):
        if name == '':
            name = None
        if name is None:
            self.nameEdit.setEnabled(False)
            self.setClass('')
        else:
            self.nameEdit.setText(name)
            self.nameEdit.setEnabled(True)
            self.profileChooser.setCurrentProfile(name)
            self.setClass(self.profileConf.profiles[name].className, name)
        self.profileChanged.emit(name)
    
    def setClass(self, className, profileName = None):
        if className == '':
            self.classChooser.setEnabled(False)
            self._removeConfigWidget()
        else:
            self.classChooser.setCurrentClass(className, emit = False)
            self._removeConfigWidget()
            self.configWidget = self.profileConf.classes[className].configurationWidget(profileName)
            self.configWidget.temporaryModified.connect(self.temporaryModified)
            self.mainLayout.insertWidget(2, self.configWidget)
            self.configWidget.setSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Minimum)
    
    def _removeConfigWidget(self):
        if self.configWidget is not None:
            self.configWidget.temporaryModified.disconnect(self.temporaryModified)
            self.mainLayout.removeWidget(self.configWidget)
            self.configWidget.hide()
        self.configWidget = None
        
    def enableClassChooser(self):
        self.secondLayout.insertWidget(2, QtGui.QLabel(self.tr("Type:")))
        self.secondLayout.insertWidget(3, self.classChooser)

class ProfileConfigurationDialog(QtGui.QDialog):

    def __init__(self, profileConf, currentProfile = None, parent = None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(self.tr("Profile Configuration: {}").format(profileConf.name))
        self.profileConf = profileConf
        layout = QtGui.QVBoxLayout()
        self.confDisplay = ProfileConfigurationDisplay(profileConf, currentProfile)
        layout.addWidget(self.confDisplay)
        self.buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Close)
        self.buttonBox.rejected.connect(self.accept)
        layout.addWidget(self.buttonBox)
        self.setLayout(layout)

        