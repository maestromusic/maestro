# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2012-2014 Martin Altmayer, Michael Helmling
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
from PyQt4.QtCore import Qt

from . import leveltreemodel
from ..core import elements, levels, tags, stack
from ..core.elements import Element
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
        if url in self.level:
            return self.level[url]
        else:
            #TODO leveltreemodel.loadFile loads each element separately and is thus inefficient
            element = self.level.collect(url)
            _processor.perform(element)
            return element
        
    def removeElements(self, parent, rows):
        """This reimplements LevelTreeModel.removeElements so that elements that have been removed from
        the tree are also removed from editor level (unless they still appear in some EditorModel)."""
        stack.beginMacro(self.tr("Remove elements"))
        
        # All elements from toCheck that are nowhere present in the editor will be removed.
        if isinstance(parent, Element):
            toCheck = [parent.contents[i] for i in rows]
        else: toCheck = [parent.contents[i].element.id for i in rows]
        super().removeElements(parent, rows)
        
        checked = set()
        elementsToRemove = []
        rootIds = [w.element.id for editorModel in EditorModel.instances for w in editorModel.root.contents]
        i = 0
        while i < len(toCheck):
            elid = toCheck[i]
            i += 1
            if elid in checked or elid not in self.level:
                continue
            element = self.level[elid]
            if not any(id in rootIds for id in self._getAncestorsInEditorLevel(element)):
                elementsToRemove.append(element)
                if element.isContainer():
                    toCheck.extend(element.contents) # check contents recursively
            checked.add(elid)
        
        if len(elementsToRemove) > 0:
            empty = elements.ContentList()
            contentsDict = {element: empty for element in elementsToRemove if element.isContainer()}
            self.level.changeContents(contentsDict)
            self.level.removeElements(elementsToRemove)

        stack.endMacro()
        
    def _getAncestorsInEditorLevel(self, element):
        yield element.id
        for pid in element.parents:
            if pid in self.level:
                yield self.level[pid]
                for ancestor in self._getAncestorsInEditorLevel(self.level[pid]):
                    yield ancestor
    
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
        for element in self.level.elements.values():
            # Get infos of type 'deleted' and 'replaced' from the processor
            if element in _processor.processed:
                for info in _processor.processed[element]:
                    # newTag is None for type 'deleted'
                    self._addToExtTagInfo(info.type,info.tag,info.newTag,element)
                        
            # Compute infos of type 'external'
            for tag in element.tags:
                if not tag.isInDb():
                    self._addToExtTagInfo('external',tag,None,element)

        self.extTagInfosChanged.emit()
    
    def _changeContents(self,index,new):
        super()._changeContents(index,new)
        parent = self.data(index,Qt.EditRole)
        if parent is self.root:
            self._updateExtTagInfos()
        
    def _handleLevelChanged(self, event):
        super()._handleLevelChanged(event)
        if not isinstance(event, levels.LevelChangedEvent):
            return
        
        if len(event.addedIds) > 0 or len(event.removedIds) > 0:
            # Rebuild infos from scratch
            self._updateExtTagInfos()
            return
        
        # Only update infos of type 'external'
        changed = False
        for id in event.dataIds:
            if id not in self.level:
                continue
            element = self.level[id]
            for tag in element.tags:
                if not tag.isInDb():
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
                        changes[element] = tags.SingleTagDifference(info.tag,additions=procInfo.values)
                    elif info.type == 'replaced':
                        changes[element] = tags.TagDifference(
                                            additions=[(info.tag,value) for value in procInfo.values],
                                            removals=[(info.newTag,value) for value in procInfo.newValues]
                                            )
                    break
                
        levels.editor.changeTags(changes)
            
    def containsExternalTags(self):
        """Return whether the editor contains any external tags. While this is the case, a commit is not
        possible."""
        return any(info.type == 'external' for info in self.extTagInfos)
        
    def containsUncommitedData(self):
        """Return whether the editor contains uncommited data."""
        for wrapper in self.root.getAllNodes(True):
            element = wrapper.element
            if not element.isInDb():
                return True
            realElement = levels.real.collect(element.id)
            if not element.equalsButLevel(realElement):
                return True
        return False
    
    def commit(self):
        """Commit the contents of this editor."""
        _processor.removeElements(levels.editor.elements.values())
        levels.editor.commit()
        for editorModel in EditorModel.instances:
            editorModel._updateExtTagInfos()
            
              
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
        if element in self.processed:
            # element is being reload
            del self.processed[element]
            
        for tag in list(element.tags.keys()): # copy because dict will be modified
            if tag.isInDb():
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
            
    def removeElements(self,elements):
        """Forget the auto tag processing information about the given elements."""
        for element in elements:
            if element in self.processed:
                del self.processed[element]
            
