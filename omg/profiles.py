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
#

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
        for name, clsName, *config in self.configSection.profiles:
            if clsName in self.classes:
                self.profiles[name] = self.classes[clsName](name, *config)
            else:
                logger.warning("could not load {} profile {}: class {} not found".format(self.name, name, clsName))
    
    def newProfile(self, name = None, className = None):
        if name is None:
            name = self.tr("newProfile")
        while name in self.profiles:
            name += "_"
        if className is None:
            className = next(iter(self.classes))
        self.profiles[name] = self.classes[className](name)
        self.profileAdded.emit(name)
    
    def configurationDisplay(self, currentProfile = None, parent = None):
        return ProfileConfigurationDisplay(self, currentProfile, parent)
             
class Profile:
    
    className = "undefined"
    def __init__(self, name):
        self.name = name
    
    @classmethod    
    def configurationWidget(cls, profile = None):
        """Return a widget for configuring profiles of this class. If *profile* is not None, it
        is the name of the initial profile."""
        raise NotImplementedError()

class ConfigurationWidget(QtGui.QWidget):
    
    temporaryModified = QtCore.pyqtSignal(object)
    
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
        profileConf.profileAdded.connect(lambda name: self.insertItem(self.profileCount(), name))
        self.currentIndexChanged[int].connect(self.handleIndexChange)
        profileConf.profileRenamed.connect(self.handleProfileRenamed)
        
        profileConf.profileRemoved.connect(self.handleProfileRemoved)
        self.profileConf = profileConf
        if default:
            self.setCurrentProfile(default, False)
            
    def profileCount(self):
        if self.includeConfigure:
            return self.count()-1
        else:
            return self.count()
        
    def currentProfile(self):
        """Returns the currently selected profile, or *None* if none is selected.
        
        The latter happens especially in the case that no profile is configured."""
        if self.includeConfigure and self.currentIndex() == self.count()-1:
            return None
        return self.profileConf[self.currentText()]
    
    def setCurrentProfile(self, name, emit = True):
        for i in range(self.profileCount()):
            if self.itemText(i) == name:
                if not emit:
                    self.supressEvent = True
                self.setCurrentIndex(i)
                self.supressEvent = False
                
                return True
        return False
                   
    def handleIndexChange(self, i):
        if i != self.profileCount():
            if not self.supressEvent:
                self.profileChosen.emit(self.itemText(i))
        else:            
            self.profileConf.openConfigDialog(self, self.itemText(self.storedIndex))
            self.setCurrentIndex(self.storedIndex)
            
    def mousePressEvent(self, event):
        if self.includeConfigure and self.count() == 1 and event.button() == Qt.LeftButton:
            self.profileConf.openConfigDialog(self, None)
            event.accept()
        else:
            return super().mousePressEvent(event)
     
    def handleProfileRenamed(self, old, new):
        for i in range(self.profileCount()):
            if self.itemText(i) == old:                
                self.setItemText(i, new)
                break
    
    def handleProfileRemoved(self, name):
        for i in range(self.profileCount()):
            if self.itemText(i) == name:
                self.removeItem(i)
                #TODO: handle removal of current profile: change current profile
                break
            
class ProfileConfigurationDisplay(QtGui.QWidget):
    
    temporaryModified = QtCore.pyqtSignal(object)
    
    def __init__(self, profileConf, currentProfile = None, parent = None):
        super().__init__(parent)
        self.profileConf = profileConf
        topLayout = QtGui.QHBoxLayout()
        topLayout.addWidget(QtGui.QLabel("Profile:"), 0)
        self.profileChooser = ProfileComboBox(profileConf, currentProfile, includeConfigure = False, parent = self)
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
        self.profileChooser.profileChosen.connect(self.setProfile)    
        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addLayout(topLayout)
        mainLayout.addLayout(self.secondLayout)
        self.configWidget  = None
        self.setLayout(mainLayout)
        self.mainLayout = mainLayout
        if currentProfile is None:
            currentProfile = next(iter(self.profileConf.profiles))
        print(currentProfile)
        print(list(self.profileConf.profiles.keys()))
        
        self.setProfile(currentProfile)
    
    def handleNewProfile(self):
        self.profileConf.newProfile()
        self.setProfile(list(self.profileConf.profiles.keys())[-1])
        
    def setProfile(self, name):
        print('set')
        self.nameEdit.setText(name)
        self.profileChooser.setCurrentProfile(name)
        self.setClass(self.profileConf.profiles[name].className, name)
    
    def setClass(self, className, profileName = None):
        self.classChooser.setCurrentClass(className, emit = False)
        if self.configWidget is not None:
            self.mainLayout.removeWidget(self.configWidget)
            self.configWidget.temporaryModified.disconnect(self.temporaryModified)
            self.configWidget.setVisible(False)
        self.configWidget = self.profileConf.classes[className].configurationWidget(profileName)
        self.configWidget.temporaryModified.connect(self.temporaryModified)
        self.mainLayout.insertWidget(2, self.configWidget)
        
    def enableClassChooser(self):
        self.secondLayout.insertWidget(2, QtGui.QLabel(self.tr("Type:")))
        self.secondLayout.insertWidget(3, self.classChooser)
        