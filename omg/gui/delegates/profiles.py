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


import copy

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from ... import config, profiles2 as profiles, logging, utils
from ...core import tags

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

category = profiles.ProfileCategory("delegates",translate("Delegates","Item display"),
                                           config.storageObject.gui.delegates)
profiles.manager.addCategory(category)


class ProfileType(profiles.ProfileType):
    def __init__(self,name,title,options,leftData,rightData):
        super().__init__(name,title,profileClass=DelegateProfile)
        self.options = options
        self.leftData = leftData
        self.rightData = rightData
    
    def default(self):
        profile = category.get(self.title)
        if profile is None:
            print([(p, p.name, p.type) for p in category.profiles])
        return category.get(self.title)
        
    def defaultState(self):
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
        
        
def createProfileType(name,title,*,options=None,leftData=None,rightData=None,overwrite={},addOptions={}):
    #TODO comment
    """Create a , a DelegateConfigurationType storing the default values for this
    type and a default DelegateConfiguration for this type. The first configuration's values are used
    whenever a configuration using this type is resetted. In particular the first configuration must not be
    changed. The second configuration (the type's default configuration) is used as initial configuration
    whenever a widget using configurations of this type is created. It may be changed, but not deleted, by
    the user (it is a built-in configuration).
    """
    if options is None:
        options = defaultOptions # defined below
    options = utils.OrderedDict.fromItems([(k,copy.copy(option)) for k,option in options.items()])
    for optionName, value in overwrite.items():
        options[optionName].default = value
    options.extend(addOptions.items())
    
    leftData = [DataPiece.fromString(string) for string in leftData]
    rightData = [DataPiece.fromString(string) for string in rightData]
    
    type = ProfileType(name,title,options,leftData,rightData)
    category.addType(type) # this will in particular load the profiles of this type from storage
    return type
    
    
class DelegateProfile(profiles.Profile):
    def __init__(self,name,type,state=None):
        super().__init__(name,type,state)
        
        self.options = {option.name: option.default for option in type.options.values()}
        self.leftData = type.leftData[:]
        self.rightData = type.rightData[:]
        
        if state is None:
            state = {}
            
        if 'options' in state:
            for option in type.options.values():
                if option.name in state['options']:
                    self.options[option.name] = option.fromString(state['options'][option.name])
        for column in ['left','right']:
            if column in state:
                aList = []
                for string in state[column]:
                    try:
                        aList.append(DataPiece.fromString(string))
                    except ValueError as e:
                        logger.exception(e)
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
                logger.warning("Invalid int in delegate configuration in storage file.")
                return None
        elif self.type == 'bool':
            return value == 'True'
        elif self.type == 'tag':
            if tags.isInDB(value):
                return tags.get(value)
        elif self.type == 'datapiece':
            if value == 'none':
                return None
            else: 
                try:
                    return DataPiece.fromString(value)
                except ValueError:
                    logger.warning("Invalid datapiece in delegate configuration in storage file.")
                    return None

 
# List of available options for delegates. This list in particular defines the default values.
defaultOptions = utils.OrderedDict.fromItems([(data[0],DelegateOption(*data)) for data in [                                            
        ("fontSize",translate("Delegates","Fontsize"),"int",8),
        ("showMajorAncestors",translate("Delegates","Display major parent containers which are not in the tree."),"bool",False),
        ("showAllAncestors",translate("Delegates","Display all parent containers which are not in the tree."),"bool",False),
        ("showMajor",translate("Delegates","Display major flag"),"bool",False),
        ("showPositions",translate("Delegates","Display position numbers"),"bool",True),
        ("showPaths",translate("Delegates","Display paths"),"bool",False),
        ("showFlagIcons",translate("Delegates","Display flag icons"),"bool",True),
        ("removeParentFlags",translate("Delegates","Remove flags which appear in ancestor elements"),"bool",True),
        ("fitInTitleRowData",translate("Delegates","This datapiece will be displayed next to the title if it fits"),"datapiece",None),
        ("appendRemainingTags",translate("Delegates","Append all tags that are not listed above"),"bool",False),
        #("hideParentFlags",translate("Delegates","Hide flags that appear in parent elements"),"bool",True),
        #("maxRowsTag",translate("Delegates","Maximal number of rows per tag"),"int",4),
        #("maxRowsElement",translate("Delegates","Maximal number of rows per element"),"int",50),
        ("coverSize",translate("Delegates","Size of covers"),"int",40)
    ]])
