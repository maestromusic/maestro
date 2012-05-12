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
    
    def __init__(self, name, configSection, profileClasses = None):
        super().__init__()
        self.name = name
        self.classes = {}
        if profileClasses is not None:
            for cls in profileClasses:
                self.classes[cls.name] = cls
        self.configSection = configSection
        self.profiles = collections.OrderedDict()
        
    def loadConfig(self):
        for name, clsName, config in self.configSection.profiles:
            if clsName in self.classes:
                self.profiles[name] = self.classes[clsName](name, *config)
            else:
                logger.warning("could not load {} profile {}: class {} not found".format(self.name, name, clsName))
             
class Profile:
    def __init__(self, name):
        self.name = name
        
class ProfileComboBox(QtGui.QComboBox):
    """This class provides a combo box that lets the user choose a profile."""
    
    profileChosen = QtCore.pyqtSignal(str)
    
    def __init__(self, profileConf, default = None, parent = None):
        super().__init__(parent)
        for name in profileConf.profiles:
            self.addItem(name)
        type(self).ignoreSignal = False
        self.storedIndex = 0
        self.addItem(self.tr("configure..."))
        self.currentIndexChanged[int].connect(self.handleIndexChange)
        profileConf.profileRenamed.connect(self.handleProfileRenamed)
        profileConf.profileAdded.connect(lambda name: self.insertItem(self.count()-1, name))
        profileConf.profileRemoved.connect(self.handleProfileRemoved)
        self.profileConf = profileConf
    
    def currentProfile(self):
        """Returns the currently selected profile, or *None* if none is selected.
        
        The latter happens especially in the case that no profile is configured."""
        if self.currentIndex() == self.count()-1:
            return None
        return self.profileConf[self.currentText()]
    
    def setCurrentProfile(self, name):
        for i in range(self.count()-1):
            if self.itemText(i) == name:
                self.setCurrentIndex(i)
                self.backendChanged.emit(name)
                return True
        return False
                     
    def handleIndexChange(self, i):
        if self.__class__.ignoreSignal:
            return
        if i != self.count() - 1:
            self.profileChosen.emit(self.itemText(i))
            self.storedIndex = i
        else:
            self.__class__.ignoreSignal = True            
            self.profileConf.openConfigDialog(self, self.itemText(self.storedIndex))
            self.setCurrentIndex(self.storedIndex)
            self.__class__.ignoreSignal = False
            
    def mousePressEvent(self, event):
        if self.count() == 1 and event.button() == Qt.LeftButton:
            self.__class__.ignoreSignal = True
            self.profileConf.openConfigDialog(self, None)
            self.__class__.ignoreSignal = False
            event.accept()
        else:
            return super().mousePressEvent(event)
     
    def handleProfileRenamed(self, old, new):
        for i in range(self.count()-1):
            if self.itemText(i) == old:                
                self.setItemText(i, new)
                break
    
    def handleProfileRemoved(self, name):
        for i in range(self.count()-1):
            if self.itemText(i) == name:
                wasIgnore = self.__class__.ignoreSignal
                self.__class__.ignoreSignal = True
                self.removeItem(i)
                self.__class__.ignoreSignal = wasIgnore
                #TODO: handle removal of current profile: change current profile
                break   