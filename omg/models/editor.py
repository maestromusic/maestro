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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import leveltreemodel
from ..core import levels, tags
from .. import application, config, constants, logging

logger = logging.getLogger(__name__)

autoDeleteTags = None
autoReplaceTags = None


class ExternalTagInfo:
    def __init__(self,type,tag,newTag=None):
        self.type = type
        self.tag = tag
        if type == 'unknown':
            self._elements = []
        else: self.valueMap = {}
        self.newTag = newTag
        
    def elementCount(self):
        return len(self._elements) if self.type == 'unknown' else len(self.valueMap)
    
    def addElement(self,element,values=None):
        if self.type == 'unknown':
            assert element not in self._elements
            self._elements.append(element)
        else:
            assert element not in self.valueMap
            assert values is not None
            self.valueMap[element] = values
            
    def removeElement(self,element):
        if self.type == 'unknown':
            self._elements.remove(element)
        else: del self.valueMap[element]
    
    def elements(self):
        if self.type == 'unknown':
            return self._elements
        else: return self.valueMap.keys()
        
    def reduce(self,elementIds):
        if all(element.id in elementIds for element in self.elements()):
            return self
        else:
            copy = ExternalTagInfo(self.type,self.tag,self.newTag)
            if self.type == 'unknown':
                copy._elements = [element for element in self._elements if element.id in elementIds]
            else:
                copy.valueMap = {el: values for el,values in self.valueMap if el.id in elementIds}
            return copy 
        

class EditorModel(leveltreemodel.LevelTreeModel):
    
    instances = weakref.WeakSet()
    extTagInfosChanged = QtCore.pyqtSignal()
    
    _globalExtTagInfos = []
    
    def __init__(self, level=levels.editor, ids=None):
        super().__init__(level, ids)
        EditorModel.instances.add(self)
        application.dispatcher.changes.connect(self._handleDispatcher)
        self.extTagInfos = []
    
    def loadFile(self, url):
        if url not in self.level:
            element = self.level.get(url)
        else:
            id = levels.idFromUrl(url)
            for model in self.instances:
                if id in model:
                    # skip autoDelete and autoReplace if the element is loaded from another editor
                    return self.level.get(url)
            # Delete outdated infos before auto tag processing
            EditorModel._removeFromGlobalExtTagInfos(element)
            element = self.level.reload(id)
        
        EditorModel.performAutoTagProcessing(element)
        return element
    
    @staticmethod
    def performAutoTagProcessing(element):
        _initAutoTagProcessing()
        changed = False
        for tag in list(element.tags.keys()): # copy because dict will be modified
            if tag.isInDB():
                # do not auto process internal tags even if the config file says so
                continue
        
            if tag in autoDeleteTags:
                type = 'delete'
                newTag = None
            elif tag in autoReplaceTags:
                type = 'replace'
                newTag = autoReplaceTags[tag]
            else: continue
            
            info = EditorModel._getGlobalExtTagInfo(type,tag,newTag)
            info.addElement(element,element.tags[tag])
            changed = True
            
            if type == 'delete':
                del element.tags[tag]
            elif type == 'replace':
                for string in element.tags[tag]:
                    try:
                        value = newTag.convertValue(string,crop=True)
                    except ValueError:
                        logger.error("Invalid value for tag '{}' (replacing '{}') found: {}"
                                     .format(newTag.name,tag.name,string))
                    else: element.tags.addUnique(newTag,value)
                del element.tags[tag]
            
    @staticmethod
    def _getGlobalExtTagInfo(type,tag,newTag=None):
        for info in EditorModel._globalExtTagInfos:
            if info.type == type and info.tag == tag and newTag == newTag:
                return info
        else:
            info = ExternalTagInfo(type,tag,newTag)
            EditorModel._globalExtTagInfos.append(info)
            return info
        
    def _getExtTagInfo(self,type,tag,newTag=None):
        for info in self.extTagInfos:
            if info.type == type and info.tag == tag and newTag == newTag:
                return info
        else:
            info = ExternalTagInfo(type,tag,newTag)
            EditorModel.self.extTagInfos.append(info)
            return info
    
    @staticmethod
    def _removeFromGlobalExtTagInfos(element):
        for info in EditorModel._globalExtTagInfos[:]:
            if element in info.elements():
                if len(info.elements()) == 1:
                    EditorModel._globalExtTagInfos.remove(info)
                else: info.removeElement(element)

    def _updateExtTagInfos(self):
        elementIds = set(wrapper.element.id for wrapper in self.root.getAllNodes(skipSelf=True))
        self.extTagInfos = []
        for info in EditorModel._globalExtTagInfos:
            if any(element.id in elementIds for element in info.elements()):
                self.extTagInfos.append(info.reduce(elementIds))
            
        unknownInfos = {}
        for wrapper in self.root.getAllNodes(skipSelf=True):
            element = wrapper.element
            for tag in element.tags:
                if not tag.isInDB():
                    if tag not in unknownInfos:
                        unknownInfos[tag] = ExternalTagInfo('unknown',tag)
                    info = unknownInfos[tag]
                    info.addElement(element)
                    
        self.extTagInfos.extend(unknownInfos.values())
        self.extTagInfosChanged.emit()
    
    def _changeContents(self,index,new):
        super()._changeContents(index,new)
        parent = self.data(index,Qt.EditRole)
        if parent is self.root:
            self._updateExtTagInfos()
        
    def _handleLevelChanged(self,event):
        super()._handleLevelChanged(event)
        
        if len(event.contentIds) > 0:
            # Rebuild infos from scratch
            self._updateExtTagInfos()
        else:
            changed = False
            # Only update infos of type 'unknown'
            for id in event.dataIds:
                element = self.level.get(id)
                for tag in element.tags:
                    if not tag.isInDB():
                        info = self._getExtTagInfo(tag,'unknown')
                        if element not in info.elements():
                            info.addElement(element)
                            changed = True
                            
                for info in self.extTagInfos[:]:
                    if info.type == 'unknown' and info.tag not in element.tags and element in info.elements():
                        info.removeElement(element)
                        if len(info.elements()) == 0:
                            self.extTagInfos.remove(info)
                        changed = True
                        
            if changed:
                self.extTagInfosChanged.emit()
                
    def _handleDispatcher(self,event):
        if isinstance(event,tags.TagTypeChangedEvent) and event.action != constants.CHANGED:
            self._updateExtTagInfos()
            

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
