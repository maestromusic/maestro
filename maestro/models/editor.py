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
#

import weakref

from PyQt5 import QtCore
from PyQt5.QtCore import Qt

from . import leveltreemodel
from ..core import elements, levels, tags
from ..core.elements import Element
from .. import application, stack


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
    
    def loadFile(self, url):
        if url in self.level:
            return self.level[url]
        else:
            element = self.level.collect(url)
            return element
        
    def removeElements(self, parent, rows):
        """Reimplements LevelTreeModel.removeElements so that elements that have been removed from
        the tree are also removed from editor level (unless they still appear in some EditorModel).
        """
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
            for tag in element.tags:
                if not tag.isInDb():
                    self._addToExtTagInfo('external', tag, None, element)
        self.extTagInfosChanged.emit()
    
    def _changeContents(self,index,new):
        super()._changeContents(index,new)
        parent = self.data(index,Qt.EditRole)
        if parent is self.root:
            self._updateExtTagInfos()
        
    def _handleLevelChanged(self, event):
        super()._handleLevelChanged(event)
        if not isinstance(event, levels.LevelChangeEvent):
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
        if isinstance(event, tags.TagTypeChangeEvent) \
                and event.action != application.ChangeType.changed:
            self._updateExtTagInfos()
            
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
    
    def flags(self, index):
        flags = super().flags(index)
        if flags & Qt.ItemIsSelectable:
            flags |= Qt.ItemIsEditable
        return flags
        
    def commit(self):
        """Commit the contents of this editor."""
        levels.editor.commit()
        for editorModel in EditorModel.instances:
            editorModel._updateExtTagInfos()
