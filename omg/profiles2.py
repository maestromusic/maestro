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


"""This module provides a system to manage configuration profiles in OMG.""" 

import collections

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import config, logging
from .gui import dialogs 

logger = logging.getLogger(__name__)

#TODO: make sure names are unique
class Profile(QtCore.QObject): # to allow subclasses to have signals
    name = None
    type = None
    builtin = False
    hidden = False # for default profiles
    readOnly = False # necessary?
    
    def __init__(self,name,category,type=None):
        super().__init__()
        self.name = name
        self.category = category
        self.type = type
    
    def save(self):
        pass
    
    def configurationWidget(self):
        return None
    
    
class ProfileType:
    def __init__(self,name,title,profileClass=None):
        self.name = name
        self.title = title
        self.profileClass = profileClass if profileClass is not None else Profile
        self.defaultProfile = None

        
class ProfileCategory(QtCore.QObject):
    typeAdded = QtCore.pyqtSignal(ProfileType)
    typeRemoved = QtCore.pyqtSignal(ProfileType)
    profileAdded = QtCore.pyqtSignal(Profile)
    profileRemoved = QtCore.pyqtSignal(Profile)
    profileChanged = QtCore.pyqtSignal(Profile)
    profileRenamed = QtCore.pyqtSignal(Profile)
    
    profileClass = Profile
    
    def __init__(self,name,title,storageOption):
        super().__init__()
        self.name = name
        self.title = title
        assert isinstance(storageOption,config.Option)
        self.storageOption = storageOption
        if not isinstance(self.storageOption.getValue(),list):
            self.storageOption.setValue([])
        self.types = []
        self.profiles = []
    
    def get(self,name):
        for profile in self.profiles:
            if profile.name == name:
                return profile
        return None
        
    def addType(self,type):
        if type not in self.types:
            self.types.append(type)
            self.typeAdded.emit(type)
            self.loadProfiles(type)
            
    def removeType(self,type):
        for profile in self.profiles:
            if profile.type == type:
                self.deleteProfile(profile)
        self.types.remove(types)
        self.typeRemoved.emit(types)
    
    def addProfile(self,name,type=None,config=None):
        profileClass = type.profileClass if type is not None else self.profileClass
        profile = profileClass(name,self,type,config if config is not None else {})
        self.profiles.append(profile)
        self.profileAdded.emit(profile)
        return profile
    
    def deleteProfile(self,profile):
        # TODO: comment this lines
        for i,data in enumerate(self.storageOption.getValue()):
            if data[0] == profile.name:
                data[2] = profile.save()
                break
        self.profiles.remove(profile)
        self.profileRemoved.emit(profile)
        
    def renameProfile(self,profile,newName):
        if newName != profile.name:
            profile.name = newName
            self.profileRenamed.emit(profile)
    
    def loadProfiles(self,restrictToType=None):
        """Load all profiles from the config file that have not been loaded yet and whose type is 
        *restrictToType*. If the latter is None, load profiles of all known types (i.e. those that have
        been added using addType.
        """
        for data in self.storageOption.getValue():
            if len(data) != 3: # broken storage option; should not happen
                continue
            name,typeName,config = data
            if restrictToType is not None:
                if typeName != restrictToType.name:
                    continue
                loadType = restrictToType
            elif typeName is None:
                loadType = None
            else:
                for type in self.types:
                    if type.name == typeName:
                        loadType = type
                        break
                else: continue # do not load this type
                
            self.addProfile(name,loadType,config)
            
    def save(self):
        self.storageOption.setValue([[profile.name,
                                      profile.type.name if profile.type is not None else None,
                                      profile.save()]
                                      for profile in self.profiles])
    
    def openConfigDialog(self, currentProfile=None):
        from .gui import profiles
        dialog = profiles.ProfileDialog(self, currentProfile)
        dialog.exec_()


class ProfileManager(QtCore.QObject):
    categoryAdded = QtCore.pyqtSignal(ProfileCategory)
    categoryRemoved = QtCore.pyqtSignal(ProfileCategory)
    def __init__(self):
        super().__init__()
        self.categories = []
    
    def addCategory(self,category):
        if category not in self.categories:
            self.categories.append(category)
            self.categoryAdded.emit(category)
            category.loadProfiles()
            
            
    def removeCategory(self,category):
        category.save()
        self.categories.remove(category)
        self.categoryRemoved.emit(category)
        
    def save(self):
        for category in self.categories:
            category.save()


manager = ProfileManager()
