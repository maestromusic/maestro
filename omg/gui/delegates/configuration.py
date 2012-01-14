# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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

import copy

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ... import utils, tags, config, logging

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

# Registered DelegateConfigurationTypes and registered DelegateConfigurations
_types = []
_configs = []

# Type of a change
ADDED,CHANGED,DELETED = 1,2,3


class DelegateConfigurationType:
    """Delegate configurations have a specific type (e.g. Browser, Playlist, ...) and usually each treeview
    can only use delegate configurations of one type. Types are identified by an id and have a title that is
    displayed to the user.
    """
    def __init__(self,id,title):
        self.id = id
        self.title = title
        self.default = None
        
    @staticmethod
    def fromId(id):
        """Return the type with the given id."""
        for type in _types:
            if type.id == id:
                return type
        raise ValueError("Unknown delegate configuration type '{}'.format(id)")


def addType(type):
    """Register a DelegateConfigurationType."""
    _types.append(type)


def removeType(type):
    """Unregister a DelegateConfigurationType."""
    del _types[type]
    
    
def getTypes():
    """Return a list of all registered DelegateConfigurationTypes."""
    return _types
    
    
def createConfigType(id,title,options,leftData,rightData,overwrite={},addOptions={}):
    """Create a DelegateConfigurationType, a DelegateConfigurationType storing the default values for this
    type and a default DelegateConfiguration for this type. The first configuration's values are used
    whenever a configuration using this type is resetted. In particular the first configuration must not be
    changed. The second configuration (the type's default configuration) is used as initial configuration
    whenever a widget using configurations of this type is created. It may be changed, but not deleted, by
    the user (it is a built-in configuration).
    """ 
    type = DelegateConfigurationType(id,title)
    type.default = DelegateConfiguration(title,type,builtin=True,setDefaults=False)
    type.default.options = copyOptions(options)
    for k,v in overwrite.items():
        type.default.options[k].value = v
    for k,v in addOptions.items():
        type.default.options[k] = v
    type.default.leftData = []
    for string in leftData:
        try:
            type.default.leftData.append(DataPiece.fromString(string))
        except ValueError: pass # This happens if the default configuration contains non-existent tags
    type.default.rightData = []
    for string in rightData:
        try:
            type.default.rightData.append(DataPiece.fromString(string))
        except ValueError: pass # This happens if the default configuration contains non-existent tags
    addType(type)
    
    config = DelegateConfiguration(title,type,True,setDefaults=True)
    addDelegateConfiguration(config)
    
    return type,config
    
    
class DelegateConfigurationEvent:
    """A event for the delegate configuration dispatcher. It simply stores a configuration and a type from
    ADDED,CHANGED,DELETED."""
    def __init__(self,config,type=CHANGED):
        self.config = config
        self.type = type
        

class Dispatcher(QtCore.QObject):
    """Delegate configuration dispatcher that emits events whenever a configuration is added, changed or
    deleted."""
    changes = QtCore.pyqtSignal(DelegateConfigurationEvent)
 
dispatcher = Dispatcher()
 
 
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
            return self.tag.translated()
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
            #DataPiece("bpm",translate("Delegates","BPM")),
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
    def __init__(self,id,title,type,default):
        self.id = id
        self.title = title
        self.type = type
        self.value = default # load from storageself.
        self.typeOptions = None #TODO support max/mins for integer values etc
    
    def export(self):
        """Export the value of this option to a string so that it can be restored with ''fromString''."""
        if self.type == 'tag':
            return self.value.name
        elif self.type == 'datapiece':
            if self.value is None:
                return 'none'
            else: return self.value.export()
        else: return str(self.value)
        
    def fromString(self,value):
        """Read a value from the string *value* and store it in this option. The format of *value* depends
        on the type of the option, see ''export''."""
        if self.type == 'string':
            self.value = value
        elif self.type == 'int':
            try:
                self.value = int(value)
            except ValueError:
                logger.warning("Invalid int in delegate configuration in storage file.")
                return None
        elif self.type == 'bool':
            if value == 'True':
                self.value = True
            elif value == 'False':
                self.value = False
        elif self.type == 'tag':
            if tags.exists(value):
                self.value = tags.get(value)
        elif self.type == 'datapiece':
            if value == 'none':
                self.value = None
            else: 
                try:
                    self.value = DataPiece.fromString(value)
                except ValueError:
                    logger.warning("Invalid datapiece in delegate configuration in storage file.")
                    return None
                        
        
class DelegateConfiguration:
    """A delegate configuration stores
    
        - two lists of datapieces which configure what information is displayed in the left and in the right
            column when an element is drawn,
        - and a list of options (including their values) which configure how elements are drawn. The list
            of available options depends on the type of the configuration (see DelegateConfigurationType),
            e.g. Browser.
            
    Constructor parameters are
    
        - *title*: A unique title which is used to identify this configuration and to display it to the user.
        - *type*: The DelegateConfigurationType of this configuration
        - *builtin*: Built in configurations cannot be renamed or deleted by the user.
        - *setDefaults*: If true both columns and all options will be set to the default values for
            configurations of this type.
            
    \ """
    def __init__(self,title,type,builtin=False,setDefaults=True):
        self.title = title
        self.type = type
        self.builtin = builtin
        if setDefaults:
            self.resetToDefaults(emitEvent=False)
    
    def setTitle(self,title):
        """Change the title of this configuration unless it is a built-in configuration."""
        if not self.builtin:
            self.title = title
            dispatcher.changes.emit(DelegateConfigurationEvent(self,CHANGED))
        
    def save(self):
        """Return a dict storing this configuration."""
        # Order does not play a role
        optionDict = {title:option.export() for title,option in self.options.items() }
        left = [dataPiece.export() for dataPiece in self.leftData]
        right = [dataPiece.export() for dataPiece in self.rightData]
        return {
            'title': self.title,
            'options': optionDict,
            'left': left,
            'right': right,
            'type': self.type.id
        }

    def restore(self,data):
        """Restore this configuration from a dict created by *save*."""
        assert data['title'] == self.title
        assert data['type'] == self.type.id
        if 'options' in data:
            for title,option in self.options.items():
                if title in data['options']:
                    option.fromString(data['options'][title])
        for column in ['left','right']:
            if column in data:
                aList = []
                for string in data[column]:
                    try:
                        aList.append(DataPiece.fromString(string))
                    except ValueError as e:
                        logger.exception(e)
                        # continue anyway
                setattr(self,'leftData' if column == 'left' else 'rightData',aList)
    
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
            dispatcher.changes.emit(DelegateConfigurationEvent(self,CHANGED))
    
    def removeDataPieces(self,left,index,count):
        """Remove *count* datapieces beginning with index *index* from the left or right column (depending on
        *left*."""
        theList = self.leftData if left else self.rightData
        del theList[index:index+count]
        dispatcher.changes.emit(DelegateConfigurationEvent(self,CHANGED))
        
    def setDataPieces(self,left,dataPieces):
        """Set the datapieces of the left or right column depending on the parameter *left*."""
        if left:
            if self.leftData != dataPieces:
                self.leftData = dataPieces
                dispatcher.changes.emit(DelegateConfigurationEvent(self,CHANGED))
        else:
            if self.rightData != dataPieces:
                self.rightData = dataPieces
                dispatcher.changes.emit(DelegateConfigurationEvent(self,CHANGED))
    
    def setOption(self,option,value):
        """Set the value of the given option."""
        assert option.id in self.options
        if value != option.value:
            option.value = value
            dispatcher.changes.emit(DelegateConfigurationEvent(self,CHANGED))
        
    def resetToDefaults(self,emitEvent=True):
        """Reset all datapieces and options to the default values for this configuration's type. Emit a
        CHANGE-event if *emitEvent* is True."""
        self.copyFrom(self.type.default,emitEvent)
    
    def copyFrom(self,other,emitEvent=True):
        """Copy all datapieces and options from the configuration *other* which must have the same type.
        Emit a CHANGE-event if *emitEvent* is True."""
        newItems = ((id,copy.copy(option)) for id,option in other.options.items())
        self.options = utils.OrderedDict.fromItems(newItems)
        self.leftData = other.leftData[:]
        self.rightData = other.rightData[:]
        if emitEvent:
            dispatcher.changes.emit(DelegateConfigurationEvent(self,CHANGED))
    
    def copy(self):
        """Return a copy of this configuration.""" 
        new = DelegateConfiguration(self.title,self.type,builtin=self.builtin,setDefaults=False)
        new.copyFrom(self,emitEvent=False)
        return new
        
    def __hash__(self):
        return hash(self.title)
        

def getConfigurations(type=None):
    """Return a list of all configurations. If *type* is not None, only configurations of that type will
    be returned."""
    if type is None:
        return _configs
    else: return [c for c in _configs if c.type == type]
    
    
def getConfiguration(title,type=None):
    """Get the configuration identified by *title*. Raise a ValueError if it cannot be found. If *type* is
    not None, ensure that the configuration has the given type and raise a ValueError else."""
    for config in _configs:
        if config.title == title:
            if type is not None and config.type != type:
                raise ValueError("Delegate configuration with title '{}' is not of type '{}'"
                                 .format(config.title,type.id))
            return config
    raise ValueError("There is no delegate configuration with title '{}'".format(title))
        

def exists(title):
    """Return whether a configuration with title *title* is registered."""
    return any(c.title == title for c in _configs)


def createDelegateConfiguration(type):
    """Create a delegate configuration of the given DelegateConfigurationType and register it. Initialize
    it with the default datapieces and options for this type."""
    i = 0
    title = 'New {}'.format(type.title)
    while exists(title):
        i += 1
        title = 'New {} ({})'.format(type.title,i)    
    addDelegateConfiguration(DelegateConfiguration(title,type))
    
    
def addDelegateConfiguration(config):
    """Register a DelegateConfiguration."""
    insertDelegateConfiguration(len(_configs),config)
    
    
def insertDelegateConfiguration(pos,config):
    """Insert a DelegateConfiguration at the given position into the list of all configurations."""
    _configs.insert(pos,config)
    dispatcher.changes.emit(DelegateConfigurationEvent(config,ADDED))


def removeDelegateConfiguration(config):
    """Unregister the given configuration."""
    if not config.builtin:
        _configs.remove(config)
        dispatcher.changes.emit(DelegateConfigurationEvent(config,DELETED))


def save():
    """Save all registered configurations to the storage file."""
    config.storage.gui.delegate_configurations = [config.save() for config in _configs]


def load():
    """Load configurations from the storage file."""
    for data in config.storage.gui.delegate_configurations:
        if 'title' not in data or 'type' not in data:
            continue
        title = data['title']
        # Use an existing (builtin) configuration or create one for this title. 
        try:
            theConfig = getConfiguration(title)
            if theConfig.type.id != data['type']:
                logger.warning("Delegate configuration type mismatch: '{}' != '{}'"
                               .format(theConfig.type.id,data['type']))
        except ValueError:
            try:
                type = DelegateConfigurationType.fromId(data['type'])
            except ValueError as e:
                logger.warning(str(e))
                continue
            theConfig = DelegateConfiguration(title,type)
            _configs.append(theConfig)
        theConfig.restore(data)
            
    
def copyOptions(options):
    """Take an instance of utils.OrderedDict containing DelegateOptions and return a copy of the dict
    containing copies of the options."""
    return utils.OrderedDict.fromItems([(k,copy.copy(option)) for k,option in options.items()])


class ConfigurationCombo(QtGui.QComboBox):
    """Combobox which allows to choose a configuration from all configurations of a type *type*. Whenever
    the user chooses a delegate configuration, the delegates of each view in *views* will be updated to use
    this configuration.
    
    Additionally the box contains an entry "Configure..." which opens the delegates panel in the preferences
    dialog.
    """
    def __init__(self,type,views=[]):
        super().__init__()
        self.type = type
        self.views = views
        self.setSizeAdjustPolicy(QtGui.QComboBox.AdjustToContents)
        dispatcher.changes.connect(self._handleDispatcher)
        self._update()
        config = views[0].itemDelegate().config
        for i in range(self.count()):
            if self.itemData(i) == config:
                self.setCurrentIndex(i)
                break
        # Necessary to reset the index after the user has chosen the "Configure..." entry.
        self._lastIndex = self.currentIndex() 
        self.currentIndexChanged.connect(self._handleCurrentIndexChanged)
    
    def _update(self):
        """Update the entries of the box based on the registered delegate configurations."""
        self.clear()
        for config in getConfigurations(self.type):
            self.addItem(config.title,config)
            
        self.insertSeparator(self.count())
        self.addItem(self.tr("Configure..."))
            
    def _handleDispatcher(self,event):
        """Handle the delegate configuration dispatcher."""
        if event.config.type != self.type:
            return
        if event.type != CHANGED:
            self.currentIndexChanged.disconnect(self._handleCurrentIndexChanged)
            current = self.itemData(self.currentIndex())
            self._update()
            for i in range(self.count()):
                if self.itemData(i) == current:
                    self.setCurrentIndex(i)
                    break
            self.currentIndexChanged.connect(self._handleCurrentIndexChanged)
        else:
            # Update the title
            for i in range(self.count()):
                if self.itemData(i) == event.config:
                    self.setItemText(i,event.config.title)
                    break
    
    def _handleCurrentIndexChanged(self,index):
        """Change the configuration of each delegate of the views in self.views or open the preferences if
        the user selected the "Configure..." entry."""
        if index == self.count()-1:
            from .. import preferences
            preferences.show(startPanel="main/delegates",
                             startConfig=self.itemData(self._lastIndex))
            self.setCurrentIndex(self._lastIndex)
        elif index != self._lastIndex: # this is not true when resetting in the line above
            config = self.itemData(index)
            for view in self.views:
                view.itemDelegate().setConfiguration(config)
            self._lastIndex = index
        