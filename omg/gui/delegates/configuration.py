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

from PyQt4 import QtCore

from ... import utils, tags, config, logging

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

_configs = []

# Type of a change
ADDED,CHANGED,DELETED = 1,2,3


class DelegateConfigurationEvent:
    def __init__(self,config,type=CHANGED):
        self.config = config
        self.type = type
        

class Dispatcher(QtCore.QObject):
    changes = QtCore.pyqtSignal(DelegateConfigurationEvent)
 
dispatcher = Dispatcher()
 
class DataPiece:
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
        
    title = property(getTitle)
    
    def __eq__(self,other):
        return self.data == other.data and self.tag == other.tag
    
    def __ne__(self,other):
        return self.data != other.data or self.tag != other.tag
    
    def __str__(self):
        return "<DataPiece {}>".format(self.getTitle())
    
    def export(self):
        if self.tag is not None:
            return "t:{}".format(self.tag.name)
        else: return self.data
        
    @staticmethod
    def fromString(string):
        if string.startswith('t:'):
            return DataPiece(tags.get(string[2:]))
        else: 
            for dataPiece in availableDataPieces():
                if dataPiece.tag is None and dataPiece.data == string:
                    return dataPiece
        raise ValueError("'{}' is not a valid datapiece export.".format(string))
            

def availableDataPieces():
    result = [DataPiece(tag) for tag in tags.tagList if tag != tags.TITLE]
    result.extend([
            DataPiece("length",translate("Delegates","Length")),
            DataPiece("filecount",translate("Delegates","Number of files")),
            #DataPiece("bpm",translate("Delegates","BPM")),
            DataPiece("filetype",translate("Delegates","Filetype"))
        ])
    return result


class DelegateOption:
    def __init__(self,id,title,type,default):
        self.id = id
        self.title = title
        self.type = type
        self.value = default # load from storage
        self.active = True # load from storage
        self.typeOptions = None #TODO support max/mins for integer values etc
    
    def export(self):
        if self.type == "tag":
            return self.value.name
        else: return str(self.value)
        
    def fromString(self,value):
        if self.type == 'string':
            self.value = value
        elif self.type == 'int':
            try:
                self.value = int(value)
            except ValueError: pass
        elif self.type == 'bool':
            if value == 'True':
                self.value = True
            elif value == 'False':
                self.value = False
        elif self.type == 'tag':
            if tags.exists(value):
                self.value = tags.get(value)
                        
        
class DelegateConfiguration:
    def __init__(self,title,theClass,builtin=False):
        self.title = title
        self.theClass = theClass
        self.builtin = builtin
        self.resetToDefaults(emitEvent=False)
        
    def save(self):
        # Order does not play a role
        optionDict = {title:option.export() for title,option in self.options.items() }
        left = [dataPiece.export() for dataPiece in self.leftData]
        right = [dataPiece.export() for dataPiece in self.rightData]
        return {
            'title': self.title,
            'options': optionDict,
            'left': left,
            'right': right,
            'class': self.theClass.__name__
        }

    def restore(self,data):
        assert data['title'] == self.title
        assert data['class'] == self.theClass.__name__
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
        return piece in self.leftData or piece in self.rightData
    
    def getDataPieces(self,left):
        return self.leftData if left else self.rightData
    
    def addDataPiece(self,left,dataPiece):
        if dataPiece not in self.leftData and dataPiece not in self.rightData:
            theList = self.leftData if left else self.rightData
            theList.append(dataPiece)
            dispatcher.changes.emit(DelegateConfigurationEvent(self,CHANGED))
            
    def setDataPieces(self,left,dataPieces):
        if left:
            if self.leftData != dataPieces:
                self.leftData = dataPieces
                dispatcher.changes.emit(DelegateConfigurationEvent(self,CHANGED))
        else:
            if self.rightData != dataPieces:
                self.rightData = dataPieces
                dispatcher.changes.emit(DelegateConfigurationEvent(self,CHANGED))
    
    def setOption(self,option,value):
        assert option.id in self.options
        if value != option.value:
            option.value = value
            dispatcher.changes.emit(DelegateConfigurationEvent(self,CHANGED))
        
    def resetToDefaults(self,emitEvent=True):
        newItems = ((id,copy.copy(option)) for id,option in self.theClass.options.items())
        self.options = utils.OrderedDict.fromItems(newItems)
        self.leftData,self.rightData = self.theClass.getDefaultDataPieces()
        if emitEvent:
            dispatcher.changes.emit(DelegateConfigurationEvent(self,CHANGED))
        
    def __hash__(self):
        return hash(self.title)
        

def getConfigurations(theClass=None):
    if theClass is None:
        return _configs
    else: return [c for c in _configs if c.theClass == theClass]
    
    
def getConfiguration(title,theClass=None):
    for config in _configs:
        if config.title == title:
            if theClass is not None and config.theClass != theClass:
                raise ValueError("Delegate configuration with title '{}' cannot be used for {}"
                                 .format(config.title,theClass.__name__))
            return config
    raise ValueError("There is no delegate configuration with title '{}'".format(title))
        
        
def addDelegateConfiguration(config):
    insertDelegateConfiguration(len(_configs),config)
    
    
def insertDelegateConfiguration(pos,config):
    _configs.insert(pos,config)
    dispatcher.changes.emit(DelegateConfigurationEvent(config,ADDED))


def removeDelegateConfiguration(title):
    for i,config in enumerate(_configs):
        if config.title == title:
            del _configs[i]
            dispatcher.changes.emit(DelegateConfigurationEvent(config,DELETED))
            return


def save():
    config.storage.gui.delegate_configurations = [config.save() for config in _configs]


def load():
    for data in config.storage.gui.delegate_configurations:
        if 'title' not in data or 'class' not in data:
            continue
        title = data['title']
        # Use an existing (builtin) configuration or create one for this title. 
        try:
            theConfig = getConfiguration(title)
        except ValueError:
            theClass = None
            from . import AbstractDelegate
            for subClass in AbstractDelegate.__subclasses__():
                if subClass.__name__ == data['class']:
                    theClass = subClass
                    break
            if theClass is None:
                logger.error("There is not delegate class of name '{}'".format(data['class']))
                continue
            theConfig = DelegateConfiguration(title,theClass)
            _configs.append(theConfig)
        theConfig.restore(data)
            
    
def copyOptions(options):
    """Take an instance of utils.OrderedDict containing DelegateOptions and return a copy of the dict
    containing copies of the options."""
    return utils.OrderedDict.fromItems([(k,copy.copy(option)) for k,option in options.items()])
