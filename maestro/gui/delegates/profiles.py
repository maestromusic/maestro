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


import copy, collections

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt
from maestro import config, profiles, logging
from maestro.core import tags

translate = QtCore.QCoreApplication.translate
category = None


class DelegateProfileCategory(profiles.TypedProfileCategory):
    """The delegates' profile category prefers the default delegates of each type."""
    def getFromStorage(self,name,restrictToType):
        if name is not None:
            profile = self.get(name)
            if profile is not None and restrictToType is None and profile.type == restrictToType:
                return profile
        return restrictToType.default()


def init():
    global category
    category = DelegateProfileCategory(
           name = "delegates",
           title = translate("Delegates","Item display"),
           storageOption = config.getOption(config.storage, 'gui.delegates'),
           description = translate("Delegates",
                    "Configure how elements are rendered in treeviews like browser, editor and playlist."),
           iconName='preferences-delegates',
    )

    profiles.manager.addCategory(category)


class ProfileType(profiles.ProfileType):
    """Class of profile types used by the delegates. Different views (browser, editor etc.) support different
    options and each has its own default configuration.
    
    For each instance of this class a default profile for this type will be created. The default profile will
    have the type's title as name. Its values may be changed by the user. However, the profile may not be
    deleted. If the user deletes the profile from the storage file, it will be recreated with the default
    values stored in the type.
    
    The constructor takes the name and title of the type, an (ordered) dict mapping option names to
    DelegateOptions (these include the options' default values for the default delegate) and two lists of
    DataPieces that are displayed by default in the left and right column of the default delegate profile.
    """  
    def __init__(self,name,title,options,leftData,rightData):
        super().__init__(name,title,profileClass=DelegateProfile)
        self.options = options
        self.leftData = leftData
        self.rightData = rightData
    
    def default(self):
        """Return the default profile for this type. Note that the values of this profile may differ
        from self.options, self.leftData, self.rightData because the user is allowed to change the default
        delegate.
        """
        return category.get(self.title)
        
    def defaultState(self):
        """Return a state object that - if passed to the constructor of Profile - will create a profile
        with the default values for this type."""
        optionDict = {option.name: option.export(self.options[option.name].default)
                      for option in self.options.values()}
        left = [dataPiece.export() for dataPiece in self.leftData]
        right = [dataPiece.export() for dataPiece in self.rightData]
        return {
            'title': self.title,
            'options': optionDict,
            'left': left,
            'right': right,
            'type': self.name
        }
    
    def load(self,category):
        profile = category.get(self.title)
        if profile is None:
            profile = category.addProfile(self.title,self)
        elif profile.type is not self:
            category.deleteProfile(profile)
            profile = category.addProfile(self.title,self)
        profile.builtIn = True
        

def createProfileType(name,title,*,options=None,leftData=None,rightData=None,overwrite={},addOptions=[]):
    """Create a profile type and an associated default profile and add them to the delegate profile category.
    This should be called once inside the class definition of each treeview-subclass that needs its own
    type of delegate profiles.
    
    Arguments are:
    
        - name: internal name of the type,
        - title: displayed name of the type and name of the profile,
        - options: list of DelegateOptions. This defines which options can be modified by the user.
           If this is None, then the default options defined in this module will be used.
        - leftData: default DataPieces for the left column,
        - rightData: default DataPieces for the right column,
        - overwrite: dict mapping option names to values which will overwrite the values from *options*,
        - addOptions: like options, will be added to *options* (or to the default options if *options* is
          None).
    
    """
    if options is None:
        options = defaultOptions # defined below
    
    options = collections.OrderedDict([(option.name,copy.copy(option)) for option in options])
    for optionName, value in overwrite.items():
        options[optionName].default = value
    for option in addOptions:
        options[option.name] = option
    
    leftData = [DataPiece.fromString(string) for string in leftData]
    rightData = [DataPiece.fromString(string) for string in rightData]
    
    type = ProfileType(name,title,options,leftData,rightData)
    category.addType(type) # this will in particular load the profiles of this type from storage
    return type
    
    
class DelegateProfile(profiles.Profile):
    """Profile to configure a delegate. See profiles.Profile."""
    def __init__(self,name,type=None,state=None):
        if type is None:
            type = defaultProfileType
        super().__init__(name,type,state)
        
        self.options = {option.name: option.default for option in type.options.values()}
        self.leftData = type.leftData[:]
        self.rightData = type.rightData[:]
        
        if state is not None:
            self._updateFromState(state)
            
    def _updateFromState(self,state):
        """Update the values of this profile from *state* which must be a dict like those returned by save.
        """
        if 'options' in state:
            for option in self.type.options.values():
                if option.name in state['options']:
                    self.options[option.name] = option.fromString(state['options'][option.name])
        for column in ['left','right']:
            if column in state:
                aList = []
                for string in state[column]:
                    try:
                        aList.append(DataPiece.fromString(string))
                    except ValueError:
                        logging.exception(__name__, "Exception when updating profile.")
                        # continue anyway
                setattr(self,'leftData' if column == 'left' else 'rightData',aList)
    
    def save(self):
        """Return a dict storing this profile."""
        # Order does not play a role
        optionDict = {option.name: option.export(self.options[option.name])
                      for option in self.type.options.values()}
        left = [dataPiece.export() for dataPiece in self.leftData]
        right = [dataPiece.export() for dataPiece in self.rightData]
        return {
            'title': self.name,
            'options': optionDict,
            'left': left,
            'right': right,
            'type': self.type.name
        }
        
    def hasDataPiece(self,piece):
        """Return whether the given datapiece is contained either in the left or in the right column."""
        return piece in self.leftData or piece in self.rightData
    
    def getDataPieces(self,left):
        """Return the datapieces contained in the left or right column depending on the parameter *left*."""
        return self.leftData if left else self.rightData
    
    def addDataPiece(self,left,dataPiece):
        """Add *datapiece* to the left or right column depending on the parameter *left*.""" 
        self.insertDataPieces(left,len(self.getDataPieces(left)),[dataPiece])
    
    def insertDataPieces(self,left,pos,dataPieces,emitEvent=True):
        """Insert a list of DataPieces at position *pos* to the left or right column depending on the
        parameter *left*. If *emitEvent* is False, no event is send over the dispatcher. This is only needed
        by Drag and Drop between the datapieces listviews (see dropMimeData).
        """
        theList = self.leftData if left else self.rightData
        theList[pos:pos] = dataPieces
        if emitEvent:
            category.profileChanged.emit(self)
    
    def removeDataPieces(self,left,index,count):
        """Remove *count* datapieces beginning with index *index* from the left or right column (depending on
        *left*."""
        theList = self.leftData if left else self.rightData
        del theList[index:index+count]
        category.profileChanged.emit(self)
        
    def setDataPieces(self,left,dataPieces):
        """Set the datapieces of the left or right column depending on the parameter *left*."""
        if left:
            if self.leftData != dataPieces:
                self.leftData = dataPieces
                category.profileChanged.emit(self)
        else:
            if self.rightData != dataPieces:
                self.rightData = dataPieces
                category.profileChanged.emit(self)
    
    def setOption(self,option,value):
        """Set the value of the given option."""
        assert option.name in self.options
        if value != self.options[option.name]:
            self.options[option.name] = value
            category.profileChanged.emit(self)
      
    def resetToDefaults(self):
        """Reset all datapieces and options to the default values for this configuration's type. This does
        not work, if the profile does not have a type."""
        self._updateFromState(self.type.defaultState())
        category.profileChanged.emit(self)

    @classmethod
    def configurationWidget(cls, profile, parent):
        from ..preferences.delegates import DelegateOptionsPanel
        return DelegateOptionsPanel(profile, parent)
        

class DataPiece:
    """Datapieces are used to configure which information a delegate should display. Each datapiece stores
    either a tag (the delegate will display all value of this tag of the element that is drawn) or one of a
    list of special values like 'length', 'filetype' (see availableDataPieces).
    
    If this datapiece should contain a tag, simply pass that tag as *data*. Otherwise the constructor expects
    the identifying string (e.g. 'length') and a title that will be displayed to the user.
    """
    def __init__(self,data,title=None):
        if isinstance(data,tags.Tag):
            self.tag = data
            self.data = None
        else:
            assert isinstance(data,str)
            self.tag = None
            self.data = data
            self._title = title
        
    def getTitle(self):
        if self.tag is not None:
            return self.tag.title
        else: return self._title
        
    # The title of this datapiece.
    title = property(getTitle)
    
    def __eq__(self,other):
        return isinstance(other,DataPiece) and self.data == other.data and self.tag == other.tag
    
    def __ne__(self,other):
        return not isinstance(other,DataPiece) or self.data != other.data or self.tag != other.tag
    
    def __str__(self):
        return "<DataPiece {}>".format(self.getTitle())
    
    def export(self):
        """Return a string from which this datapiece can be reconstructed using ''fromString''."""
        if self.tag is not None:
            return "t:{}".format(self.tag.name)
        else: return self.data
        
    @staticmethod
    def fromString(string):
        """Construct a datapiece from a string. The string must either be one of the special datapiece
        identifiers (e.g. 'length') or something like 't:artist' to construct a datapiece containing a tag.
        """
        if string.startswith('t:'):
            return DataPiece(tags.get(string[2:], True))
        else: 
            for dataPiece in availableDataPieces():
                if dataPiece.tag is None and dataPiece.data == string:
                    return dataPiece
        raise ValueError("'{}' is not a valid datapiece export.".format(string))
            

def availableDataPieces():
    """Return all available datapieces (depending on the tag types in the database)."""
    result = [DataPiece(tag) for tag in tags.tagList if tag != tags.TITLE]
    result.extend([
            DataPiece("length",translate("Delegates","Length")),
            DataPiece("filecount",translate("Delegates","Number of files")),
            DataPiece("filetype",translate("Delegates","Filetype")),
            DataPiece("filecount+length",translate("Delegates","Filenumber and length"))
        ])
    return result


class DelegateOption:
    """A delegate option (similar to ConfigOptions in the config package). Parameters are
    
        - *id*: unique identifier of this option,
        - *title*: title as display to the user,
        - *type*: type like 'bool', 'string'. See preferences.delegates.createEditor for a list of available
            types.
        - *default*: default value
    
    \ """
    def __init__(self,name,title,type,default):
        self.name = name
        self.title = title
        self.type = type
        self.default = default # load from storage
        self.typeOptions = None #TODO support max/mins for integer values etc
    
    def export(self,value):
        """Export the value of this option to a string so that it can be restored with ''fromString''."""
        if self.type == 'tag':
            return value.name
        elif self.type == 'datapiece':
            if value is None:
                return 'none'
            else: return value.export()
        else: return str(value)
        
    def fromString(self,value):
        """Read a value from the string *value* and store it in this option. The format of *value* depends
        on the type of the option, see ''export''."""
        if self.type == 'string':
            return value
        elif self.type == 'int':
            try:
                return int(value)
            except ValueError:
                logging.warning(__name__, "Invalid int in delegate configuration in storage file.")
                return None
        elif self.type == 'bool':
            return value == 'True'
        elif self.type == 'tag':
            if tags.isInDb(value):
                return tags.get(value)
        elif self.type == 'datapiece':
            if value == 'none':
                return None
            else: 
                try:
                    return DataPiece.fromString(value)
                except ValueError:
                    logging.warning(__name__, "Invalid datapiece in delegate configuration in storage file.")
                    return None

# List of available options for delegates. This list in particular defines the default values.
defaultOptions = [DelegateOption(*data) for data in [
        ("fontSize", translate("Delegates", "Fontsize"), "int", 8),
        ("showMajorAncestors", translate("Delegates", "Mention major parent containers which are not in the tree."), "bool", False),
        ("showAllAncestors", translate("Delegates", "Mention all parent containers which are not in the tree."), "bool", False),
        ("showType", translate("Delegates", "Display element type"), "bool", False),
        ("showPositions", translate("Delegates", "Display position numbers"), "bool", True),
        ("showPaths", translate("Delegates", "Display paths"), "bool", False),
        ("showFlagIcons", translate("Delegates", "Display flag icons"), "bool", True),
        ("removeParentFlags", translate("Delegates", "Remove flags which appear in ancestor elements"), "bool", True),
        ("fitInTitleRowData", translate("Delegates", "This datapiece will be displayed next to the title if it fits"), "datapiece", None),
        ("appendRemainingTags", translate("Delegates", "Append all tags that are not listed above"), "bool", False),
        #("hideParentFlags",translate("Delegates","Hide flags that appear in parent elements"),"bool",True),
        #("maxRowsTag",translate("Delegates","Maximal number of rows per tag"),"int",4),
        #("maxRowsElement",translate("Delegates","Maximal number of rows per element"),"int",50),
        ("coverSize", translate("Delegates", "Size of covers"), "int", 40)
    ]]

# This type is useful to create profiles which are not configurable
defaultProfileType = ProfileType('default',
                                 translate("Delegates","Standard"),
                                 collections.OrderedDict([(option.name,option)
                                                          for option in defaultOptions]),
                                 [],
                                 [])