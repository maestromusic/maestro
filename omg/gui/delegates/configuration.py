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

from ... import utils, tags

translate = QtCore.QCoreApplication.translate

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
            self.tag = None
            self.data = data
            self._title = title
        self.data = data
        
    def getTitle(self):
        if self.tag is not None:
            return self.tag.translated()
        else: return self._title
        
    title = property(getTitle)
    
    def __eq__(self,other):
        return self.data == other.data
    
    def __ne__(self,other):
        return self.data != other.data
        

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
        
        
class DelegateConfiguration:
    def __init__(self,title,theClass,values=None,builtin=False):
        self.title = title
        self.theClass = theClass
        self.options = theClass.options.copy()
        if values is not None:
            for option in self.options:
                option.value = values[option.id]
        self.leftData,self.rightData = theClass.getDefaultDataPieces()
        self.builtin = builtin
        
    def copy(self):
        #TODO
        pass
    
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
        print("This is setOption for option {} with value {}".format(option.title,value))
        assert option in self.options.values()
        if value != option.value:
            option.value = value
            dispatcher.changes.emit(DelegateConfigurationEvent(self,CHANGED))
        
    def resetToDefaults(self):
        self.options = theClass.options.copy()
        
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


def copyOptions(options):
    """Take an instance of utils.OrderedDict containing DelegateOptions and return a copy of the dict
    containing copies of the options."""
    return utils.OrderedDict.fromItems([(k,copy.copy(option)) for k,option in options.items()])
