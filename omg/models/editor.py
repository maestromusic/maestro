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

_processor = None # the single instance of AutoTagProcessor used by all EditorModels


class ProcessingInfo:
    """Stores information about auto tag processing that was performed on an element. *type* may be one
    of 'deleted' or 'replaced'. *newTag* and *newValue* are only used for type 'replaced'."""
    def __init__(self,type,tag,values,newTag=None,newValues=None):
        assert isinstance(tag,tags.Tag) and (newTag is None or isinstance(newTag,tags.Tag))
        self.type = type
        self.tag = tag
        self.values = values
        self.newTag = newTag
        self.newValues = newValues
        
        
class ExternalTagInfo:
    """Stores information about external tags in an EditorModel. *type* may be one of:
    
        - 'deleted': *tag* was deleted from self.elements,
        - 'replaced': *tag* was replaced by *newTag* in self.elements,
        - 'external': self.elements contain the external tag *tag* (thus no commit is possible)
    """
    def __init__(self,type,tag,newTag=None):
        self.type = type
        self.tag = tag
        self.newTag = newTag
        self.elements = []
        

class EditorModel(leveltreemodel.LevelTreeModel):
    """Model for the editor. Additional to LevelTreeModel this class handles
    
        - auto tag processing: When external elements are loaded into the editor, tags may be automatically
          deleted or replaced according to the config options tags.auto_delete and tags.auto_replace
        - information about external tags: the model manages a list of ExternalTagInfo-instances which are
          used by the editor's ExternalTagsWidget.
        - reloading elements: When an element is loaded into the editor that does exist on the editor
          level but is not visible in any EditorModel, it will be reset to its state on real level.
          This is necessary, when an element is dropped, changed, removed and dropped again.
    """
    instances = weakref.WeakSet() # all existing editor models
    extTagInfosChanged = QtCore.pyqtSignal() # will be emitted when the list of ExternalTagInfos changed
    
    def __init__(self, level=levels.editor, ids=None):
        super().__init__(level, ids)
        EditorModel.instances.add(self)
        application.dispatcher.connect(self._handleDispatcher)
        self.extTagInfos = []
        global _processor
        if _processor is None:
            _processor = AutoTagProcessor()
    
    def loadFile(self, url):
        if url not in self.level:
            element = self.level.get(url)
        else:
            # if the element is present on editor level, check whether it is visible in any EditorModel
            # otherwise reload it (=reset to its state on real level)
            id = levels.idFromUrl(url)
            for model in self.instances:
                if id in model:
                    # skip auto tag processing if the element is loaded from another editor
                    return self.level.get(url)
            element = self.level.reload(id)
        
        _processor.perform(element)
        return element

    def _addToExtTagInfo(self,type,tag,newTag,element):
        """Add *element* to the ExternalTagInfo specified by *type*, *tag* and *newTag*. Create such an
        object if it does not yet exist."""
        for info in self.extTagInfos:
            if info.type == type and info.tag == tag and info.newTag == newTag:
                if element not in info.elements:
                    info.elements.append(element)
                    return True
                else: return False
        else:
            info = ExternalTagInfo(type,tag,newTag)
            info.elements = [element]
            self.extTagInfos.append(info)
            return True

    def _updateExtTagInfos(self):
        """Rebuild the list of ExternalTagInfos from scratch."""
        self.extTagInfos = []
        for wrapper in self.root.getAllNodes(skipSelf=True):
            element = wrapper.element
            
            # Get infos of type 'deleted' and 'replaced' from the processor
            if element in _processor.processed:
                for info in _processor.processed[element]:
                    # newTag is None for type 'deleted'
                    self._addToExtTagInfo(info.type,info.tag,info.newTag,element)
                        
            # Compute infos of type 'external'
            for tag in element.tags:
                if not tag.isInDB():
                    self._addToExtTagInfo('external',tag,None,element)

        self.extTagInfosChanged.emit()
    
    def _changeContents(self,index,new):
        super()._changeContents(index,new)
        parent = self.data(index,Qt.EditRole)
        if parent is self.root:
            self._updateExtTagInfos()
        
    def _handleLevelChanged(self, event):
        super()._handleLevelChanged(event)
        
        if len(event.contentIds) > 0:
            # Rebuild infos from scratch
            self._updateExtTagInfos()
        else:
            # Only update infos of type 'external'
            changed = False
            for id in event.dataIds:
                element = self.level.get(id)
                for tag in element.tags:
                    if not tag.isInDB():
                        if self._addToExtTagInfo('external',tag,None,element):
                            changed = True
                            
                for info in self.extTagInfos[:]:
                    if info.type == 'external' and info.tag not in element.tags and element in info.elements:
                        info.elements.remove(element)
                        if len(info.elements) == 0:
                            self.extTagInfos.remove(info)
                        changed = True
                        
            if changed:
                self.extTagInfosChanged.emit()
                
    def _handleDispatcher(self,event):
        if isinstance(event,tags.TagTypeChangedEvent) and event.action != constants.CHANGED:
            self._updateExtTagInfos()
          
    def undoExtTagInfo(self,info):
        """Undo the given ExternalTagInfo which must be of type 'deleted' or 'replaced'. This will not
        undo an UndoCommand, but add a ChangeTagsCommand to the stack that will cancel the effect of the
        auto tag processing.
        """ 
        self.extTagInfos.remove(info)
        self.extTagInfosChanged.emit()
        
        changes = {}
        for element in info.elements:
            for procInfo in _processor.processed[element]:
                if procInfo.type == info.type and procInfo.tag == info.tag and procInfo.newTag == info.newTag:
                    if info.type == 'deleted':
                        changes[element] = procInfo.values
                    elif info.type == 'replaced':
                        diff = tags.TagDifference(None,None)
                        diff.additions = [(procInfo.tag,procInfo.values)]
                        diff.removals = [(procInfo.newTag,procInfo.newValues)]
                        changes[element] = diff
                    break
        
        if info.type == 'deleted':
            levels.editor.addTagValues(info.tag,changes)
        elif info.type == 'replaced':
            levels.editor.changeTags(changes)
            
              
class AutoTagProcessor:
    """This class performs automatic tag processing in elements. What has been changed is stored in the
    attribute 'processed' which maps elements to lists of ProcessingInfos."""
    def __init__(self):
        # Read the config file options
        self.autoDeleteTags = []
        for tagName in config.options.tags.auto_delete:
            if not tags.isValidTagName(tagName):
                logger.error("Found an invalid tagname '{}' in config option tags.auto_delete."
                             .format(tagName))
            else: self.autoDeleteTags.append(tags.get(tagName))
            
        self.autoReplaceTags = {}
        try:
            pairs = self._parseAutoReplace()
        except ValueError:
            logger.error("Invalid syntax in config option tags.auto_replace.")
        else:
            for oldName,newName in pairs:
                for tagName in [oldName,newName]:
                    if not tags.isValidTagName(tagName):
                        logger.error("Found an invalid tagname '{}' in config option tags.auto_replace."
                                     .format(tagName))
                if tags.get(oldName) in self.autoReplaceTags:
                    logger.error("Tag '{}' appears twice in config option tags.auto_replace.".format(oldName))
                else: self.autoReplaceTags[tags.get(oldName)] = tags.get(newName)
                
        self.processed = {}
    
    def _parseAutoReplace(self):
        """Parse the config option tags.auto_replace and return a list of tuples (oldname,newname) specifying
        the tags that should be replaced. This does not check whether the tag names are valid."""
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

    def perform(self,element):
        """Change tags of *element* according to the config options tags.auto_delete and tags.auto_replace.
        Store information about the performed operations in self.processed."""
        changed = False
        if element in self.processed:
            # element is being reload
            del self.processed[element]
            changed = True
            
        for tag in list(element.tags.keys()): # copy because dict will be modified
            if tag.isInDB():
                # do not auto process internal tags even if the config file says so
                continue
        
            if tag in self.autoDeleteTags:
                if element not in self.processed:
                    self.processed[element] = []
                self.processed[element].append(ProcessingInfo('deleted',tag,list(element.tags[tag])))
                del element.tags[tag]
            elif tag in self.autoReplaceTags:
                newTag = self.autoReplaceTags[tag]
                newValues = []
                for string in element.tags[tag]:
                    try:
                        value = newTag.convertValue(string,crop=True)
                    except tags.TagValueError:
                        logger.error("Invalid value for tag '{}' (replacing '{}') found: {}"
                                     .format(newTag.name,tag.name,string))
                    else:
                        if newTag not in element.tags or value not in element.tags[newTag]:
                            newValues.append(value)
                            element.tags.add(newTag,value)
                if element not in self.processed:
                    self.processed[element] = []
                self.processed[element].append(
                                    ProcessingInfo('replaced',tag,list(element.tags[tag]),newTag,newValues))
                del element.tags[tag]
            else: pass
            