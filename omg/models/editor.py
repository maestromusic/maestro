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
#

import weakref

from PyQt4 import QtCore

from . import leveltreemodel
from ..core import levels, tags
from .. import config, logging

logger = logging.getLogger(__name__)

autoDeleteTags = None
autoReplaceTags = None


class ExternalTagInfo:
    def __init__(self,tag,type,newTag=None):
        self.tag = tag
        self.type = type
        self.valueMap = {}
        self.newTag = newTag
        
    def elementCount(self):
        return len(self.valueMap)
    
    def addElement(self,element,values):
        assert element not in self.valueMap
        self.valueMap[element] = values
        

class EditorModel(leveltreemodel.LevelTreeModel):
    
    instances = weakref.WeakSet()
    externalTagInfosChanged = QtCore.pyqtSignal()
    
    def __init__(self, level=levels.editor, ids=None):
        super().__init__(level, ids)
        EditorModel.instances.add(self)
        
        self.externalTagInfos = tags.TagDict()
    
    def loadFile(self, path):
        if path not in self.level:
            element = self.level.get(path)
        else:
            id = levels.idFromPath(path)
            for model in self.instances:
                if id in model:
                    # skip autoDelete and autoReplace if the element is loaded from another editor
                    return self.level.get(path)
            element = self.level.reload(id)
        
        self.performAutoTagProcessing(element)
        return element
    
    def _getExternalTagInfos(self,tag,type):
        if tag not in self.externalTagInfos:
            self.externalTagInfos[tag] = []
        for info in self.externalTagInfos[tag]:
            if info.type == type:
                return info
        else:
            info = ExternalTagInfo(tag,type)
            self.externalTagInfos[tag].append(info)
            return info
        
    def performAutoTagProcessing(self,element):
        _initAutoTagProcessing()
        changed = False
        for tag in list(element.tags.keys()): # copy because dict will be modified
            if tag.isInDB():
                # do not auto process internal tags even if the config file says so
                continue
        
            if tag in autoDeleteTags:
                type = 'delete'
            elif tag in autoReplaceTags:
                type = 'replace'
            else: type = 'unknown'
            
            info = self._getExternalTagInfos(tag, type)
            info.addElement(element,element.tags[tag])
            changed = True
            
            if type == 'delete':
                print("Deleting tag '{}' from {}".format(tag.name,element.path))
                del element.tags[tag]
            elif type == 'replace':
                newTag = autoReplaceTags[tag]
                print("Replacing tag '{}' by '{}' in {}".format(tag.name,newTag.name,element.path))
                info.newTag = newTag
                for string in element.tags[tag]:
                    try:
                        value = newTag.valueFromString(string,crop=True)
                    except ValueError:
                        logger.error("Invalid value for tag '{}' (replacing '{}') found: {}"
                                     .format(newTag.name,tag.name,string))
                    else: element.tags.addUnique(newTag,value)
                del element.tags[tag]
                    
        if changed:
            self.externalTagInfosChanged.emit()

    #def _handleLevelChanged(self,event):
    #    super()._handleLevelChanged(event)
     #   for id in event.dataIds:
     #   for node, contents in utils.walk(self.root):
            
            

def _initAutoTagProcessing():
    global autoDeleteTags, autoReplaceTags
    if autoDeleteTags is not None:
        return # this method has already been called
    autoDeleteTags = []
    for tagName in config.options.tags.auto_delete:
        if not tags.isValidTagName(tagName):
            logger.error("Found an invalid tagname '{}' in config option tags.auto_delete."
                         .format(tagName))
        else: autoDeleteTags.append(tags.get(tagName))
        
    autoReplaceTags = {}
    try:
        pairs = _parseAutoReplace()
    except ValueError:
        logger.error("Invalid syntax in config option tags.auto_replace.")
    else:
        for oldName,newName in pairs:
            for tagName in [oldName,newName]:
                if not tags.isValidTagName(tagName):
                    logger.error("Found an invalid tagname '{}' in config option tags.auto_replace."
                                 .format(tagName))
            if tags.get(oldName) in autoReplaceTags:
                logger.error("Tag '{}' appears twice in config option tags.auto_replace.".format(oldName))
            else: autoReplaceTags[tags.get(oldName)] = tags.get(newName)

def _parseAutoReplace():
    string = config.options.tags.auto_replace.replace(' ','')
    if len(string) == 0:
        return []
    if string[0] != '(' or string[-1] != ')':
        raise ValueError()
    string = string[1:-1]
    
    result = []
    for pair in string.split('),('):
        oldName,newName = pair.split(',') # may raise ValueError
        result.append((oldName,newName))
    return result
