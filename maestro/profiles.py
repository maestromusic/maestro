# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2012-2015 Martin Altmayer, Michael Helmling
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


"""This module provides a system to manage configuration profiles in Maestro. Profiles are organized in
categories (e.g. delegates, playback). Profiles of one category may have different types (e.g. MPD
playback, Phonon playback). Profiles and types are managed by their category. Categories are
managed by the ProfileManager.""" 

from PyQt4 import QtCore

from . import config


class Profile(QtCore.QObject):
    """A profile stores the configuration of some object. Profiles are stored persistently in the
    storage file.
    
    A profile has a name and optionally a type. The constructor variable *state* contains the data
    read from the storage file. Because profiles are generally created by the user, there is no
    distinction between name and title (as for profile types and profile categories).
    """
    
    builtIn = False # built-in profiles cannot be renamed or deleted
    
    def __init__(self, name, type=None, state=None):
        super().__init__()
        self.name = name
        assert type is None or isinstance(type, ProfileType)
        self.type = type
    
    def save(self):
        """Return a dict, list, tuple or a simple data type that can be used to store this profile in the
        storage file. The result of this method will be passed as state to the constructor the next time the
        application starts.
        """
        return None

    @classmethod
    def configurationWidget(cls, profile, parent):
        """Return a widget that can be used to configure a profile. Should be a subclass
        of gui.preferences.profiles.ProfileConfigurationWidget."""
        raise NotImplementedError()
    
    def copy(self):
        """Return a copy of this profile."""
        return type(self)(self.name, self.type, self.save())
    
    def __str__(self):
        return "{}(name={})".format(type(self).__name__, self.name)


class ProfileType:
    """Optionally profiles may have a type. This is useful to
    
        - use different subclasses of Profile for profiles (e.g. MPDPlayback, PhononPlayback),
        - restrict some widget to profiles of a certain type (e.g. the Playlist accepts only DelegateProfiles
          of type 'playlist')
    
    *name* is the internal name of the profile. *title* is displayed to the user. *profileClass* is the
    (sub)class of Profile that will be used for profiles of this type.
    """ 
    
    def __init__(self, name, title, profileClass=Profile, defaultProfileName=None):
        self.name = name
        self.title = title
        self.profileClass = profileClass
        if defaultProfileName is not None:
            self.defaultProfileName = defaultProfileName
        else: self.defaultProfileName = title
        
    def load(self,category):
        """This is called after the type has been added to its ProfileCategory and its profiles have been
        loaded. Subclass implementations could use this method to create a default profile if none was
        contained in the storage file.
        """
        pass

        
class ProfileCategory(QtCore.QObject):
    """A category of profiles defines a realm which can be configured via profiles (e.g. delegates,
    playback) and manages the list of profiles.
    
    Constructor arguments:
    
        ⁻ name: internal name of this category,
        - title: displayed to the user,
        - storageOption: an option from config.storage (use config.getOption!). All profiles of this
          category will be saved into this option.
        - profileClass: Python class used for profiles in this category.
        - defaultProfileName: default name for new profiles (defaults to the category title).
        - description: Informative text that is displayed in profile configuration dialogs.
          
    """
    profileAdded = QtCore.pyqtSignal(Profile)
    profileRemoved = QtCore.pyqtSignal(Profile)
    profileChanged = QtCore.pyqtSignal(Profile)
    profileRenamed = QtCore.pyqtSignal(Profile)
    
    # subclass of Profile that is used for profiles.
    # For typed profiles this is overwritten by the profileClass of the profile's type 
    profileClass = Profile
    
    def __init__(self, name, title, storageOption, profileClass=None, defaultProfileName=None,
                 description='', iconPath='', pixmapPath=''):
        super().__init__()
        self.name = name
        self.title = title
        self.iconPath = iconPath
        self.pixmapPath = pixmapPath
        assert isinstance(storageOption,config.Option)
        
        self.storageOption = storageOption
        if not isinstance(self.storageOption.getValue(),list):
            self.storageOption.setValue([])
            
        if profileClass is not None:
            self.profileClass = profileClass
        self._profiles = []
        
        if defaultProfileName is not None:
            self.defaultProfileName = defaultProfileName
        else: self.defaultProfileName = title
        
        self.description = description
    
    def get(self, name):
        """Return the profile with the given name or None if no such profile exists."""
        for profile in self._profiles:
            if profile.name == name:
                return profile
        return None
    
    def profiles(self):
        """Return a list of all profiles of this category."""
        return self._profiles
    
    def addProfile(self, nameOrProfile, type=None, state=None):
        """Add a profile to the category. You can specify the profile either directly or pass a name
        and, optionally, a type and state. In the latter case the arguments will be passed to the constructor
        of the correct subclass of Profile.
        
        The argument *type* is ignored and only available to be compatible with TypedCategory.
        """
        if isinstance(nameOrProfile, str):
            profile = self.profileClass(nameOrProfile, type, state)
        else: profile = nameOrProfile
        self._profiles.append(profile)
        self.profileAdded.emit(profile)
        return profile
    
    def changeProfile(self, profile, newProfile):
        """Change the profile *profile* to the state of *new*. This does not replace the profile instance
        because references to *profile* might be in use. Both profiles must have the same name. *profile*
        must support the Profile.read method."""
        assert profile.name == newProfile.name
        profile.read(newProfile.save())
        self.profileChanged.emit(profile)
    
    def deleteProfile(self,profile):
        """Delete a profile so that it disappears from the storage file at application end."""
        assert not profile.builtIn
        self._profiles.remove(profile)
        self.profileRemoved.emit(profile)
        
    def renameProfile(self, profile, newName):
        """Change the name of *profile* to *newName*."""
        assert not profile.builtIn
        if newName != profile.name:
            profile.name = newName
            self.profileRenamed.emit(profile)
    
    def loadProfiles(self):
        """Load all profiles of known types from the storage file. If *restrictToType* is not None,
        only load profiles of this profile type."""
        for data in self.storageOption.getValue():
            if len(data) != 2: # broken storage option; should not happen
                continue
            name,state = data
            self.addProfile(name, None, state)
            
    def save(self):
        """Save the profiles of this category to the storage options specified in the constructor."""
        self.storageOption.setValue([[profile.name,
                                      profile.save()]
                                      for profile in self._profiles])
        
    def suggestProfileName(self):
        """Suggest an unused name for a new profile of this category. Use self.defaultProfileName for this.
        """
        name = self.defaultProfileName
        i = 2
        while self.get(name) is not None:
            name = "{} {}".format(self.defaultProfileName, i)
            i += 1
        return name
    
    def getFromStorage(self,name):
        """Return the profile of the given name if it exists or any other profile else. Use this method
        to load profiles from states saved in the storage file."""
        if name is not None:
            if self.get(name) is not None:
                return self.get(name)
        if len(self._profiles) > 0:
            return self._profiles[0]
        return None
    
        
class TypedProfileCategory(ProfileCategory):
    """A subclass of ProfileCategory which uses typed profiles: Each profile in this category must be of
    one of the ProfileTypes that have been added to the category.
    """ 
    typeAdded = QtCore.pyqtSignal(ProfileType)
    typeRemoved = QtCore.pyqtSignal(ProfileType)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.types = []
        
    def profiles(self, type=None):
        """Return a list of all profiles of this category. If *type* is given, return only profiles of that
        ProfileType."""
        if type is None:
            return self._profiles
        else: return [p for p in self._profiles if p.type == type]
        
    def getType(self, name):
        """Return the type of the given name or None if such a type does not exist."""
        for type in self.types:
            if type.name == name:
                return type
        return None
        
    def addType(self, type):
        """Add a type to the category. Load all profiles of this type from the storage file and add them
        to the category."""
        if type not in self.types:
            if self.getType(type.name) != None:
                raise ValueError("There is already a profile type of name '{}'.".format(type.name))
            self.types.append(type)
            self.typeAdded.emit(type)
            self.loadProfiles(restrictToType=type)
            
    def removeType(self, type):
        """Remove a type and all profiles of this type from the storage file. *type* may either be the type
        or its name."""
        if isinstance(type, str):
            type = self.getType(type)
            if type is None:
                raise ValueError("There is no profile type of name '{}'.".format(type))
        for profile in self._profiles:
            if profile.type == type:
                profile.builtIn = False # delete built-in profiles, too
                self.deleteProfile(profile)
        self.types.remove(type)
        self.typeRemoved.emit(type)
    
    def addProfile(self, nameOrProfile, type=None, state=None):
        """Add a profile to the category. You can specify the profile either directly or pass a name
        and, optionally, a type and state. In the latter case the arguments will be passed to the constructor
        of the correct subclass of Profile.
        
        The argument *type* is ignored and only available to be compatible with TypedCategory.
        """
        if isinstance(nameOrProfile, str):
            assert type is not None
            profileClass = type.profileClass if type.profileClass is not None else self.profileClass
            profile = profileClass(nameOrProfile, type, state)
        else: profile = nameOrProfile
        self._profiles.append(profile)
        self.profileAdded.emit(profile)
        return profile
    
    def loadProfiles(self, restrictToType=None):
        """Load all profiles of known types from the storage file. If *restrictToType* is not None,
        only load profiles of this profile type."""
        for data in self.storageOption.getValue():
            if len(data) != 3: # broken storage option; should not happen
                continue
            name, typeName, state = data
            if restrictToType is None:
                if typeName is None:
                    self.addProfile(name, None, state)
                # skip profiles with types
            elif typeName == restrictToType.name:
                self.addProfile(name, restrictToType, state)
        if restrictToType is not None:
            restrictToType.load(self)
            
    def save(self):
        """Save the profiles of this category to the storage options specified in the constructor."""
        self.storageOption.setValue([[profile.name,
                                      profile.type.name if profile.type is not None else None,
                                      profile.save()]
                                      for profile in self._profiles])
        
    def suggestProfileName(self, type):
        """Suggest an unused name for a new profile of the given type of this category. Use
        self.defaultProfileName for this."""
        name = type.defaultProfileName
        i = 2
        while self.get(name) is not None:
            name = "{} {}".format(type.defaultProfileName, i)
            i += 1
        return name
    
    def getFromStorage(self, name, restrictToType=None):
        """Return the profile of the given name if it exists or any other profile else. Use this method
        to load profiles from states saved in the storage file.
        
        If *restrictToType* is not None, return only profiles of this type.
        """
        # Return the profile given by name if it exists and its type fits
        if name is not None:
            profile = self.get(name)
            if profile is not None and (restrictToType is None or profile.type == restrictToType):
                return profile
        # Return the first profile whose type fits
        for profile in self._profiles:
            if restrictToType is None or profile.type == profile.type:
                return profile
        return None
    

class ProfileManager(QtCore.QObject):
    """The single instance of this class manages profile categories."""
    categoryAdded = QtCore.pyqtSignal(ProfileCategory)
    categoryRemoved = QtCore.pyqtSignal(ProfileCategory)
    
    def __init__(self):
        super().__init__()
        self.categories = []
        
    def getCategory(self, name):
        """Return the profile category with the given name."""
        for category in self.categories:
            if category.name == name:
                return category
        raise ValueError("There is no profile category with name '{}'.".format(name))
    
    def addCategory(self, category):
        """Add a profile category. Load all of its profiles whose type has been added to the category yet
        (or which do not have a type) from the storage file."""
        if category not in self.categories:
            self.categories.append(category)
            self.categoryAdded.emit(category)
            category.loadProfiles()
            
    def removeCategory(self, category):
        """Remove the given category without deleting its profiles from the storage file."""
        category.save()
        self.categories.remove(category)
        self.categoryRemoved.emit(category)
        
    def save(self):
        """Save all categories to their respective options in the storage file."""
        for category in self.categories:
            category.save()
            

manager = ProfileManager()
