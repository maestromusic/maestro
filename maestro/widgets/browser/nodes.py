# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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

from PyQt5 import QtCore
translate = QtCore.QCoreApplication.translate

from maestro import search
from maestro.core import levels
from maestro.core.nodes import Node, Wrapper, TextNode


class CriterionNode(Node):
    """CriterionNode is the base class for nodes used to group elements according to a criterion (confer 
    search.criteria) in a BrowserModel. The layer below this node will contain all elements of this layer
    that additionally match the criterion.
    """
    def __init__(self, layerIndex):
        self.parent = None
        self.contents = None
        self.layerIndex = layerIndex

    def getCriterion(self):
        """Return the criterion of this node."""
        assert False # implemented in subclasses

    def hasContents(self):
        # Always return True. The contents of a CriterionNode are loaded when getContents or getContentsCount
        # is called for the first time. Prior to that call hasContents=True will tell the view that the node
        # is expandable and make the view draw a plus-sign in front of the node.
        return True
        
    def getContentsCount(self):
        if self.contents is None:
            self.loadContents()
        return super().getContentsCount()
        
    def getContents(self):
        if self.contents is None:
            self.loadContents()
        return self.contents
    
    def getAllNodes(self, skipSelf=False):
        assert skipSelf
        if self.contents is None:
            return
        else: 
            for node in super().getAllNodes():
                yield node
                
    def getElids(self):
        """Return a set containing the ids of all elements below this node. Return None, if the set has not
        been stored (in that case getCriterion will be used).
        """
        if hasattr(self, 'elids'):
            elids = self.elids
            del self.elids # save memory: elids are only requested once when this node is expanded.
            return elids
        else: return None
            
    def hasLoaded(self):
        """Return whether this CriterionNode did already load its contents."""
        return self.contents is not None and (len(self.contents) != 1 
                                               or not isinstance(self.contents[0], LoadingNode))
                                               
    def loadContents(self, block=False):
        """If they are not loaded yet, start to load the contents of this node. The actual loading is done
        by the model when it reacts to the searchFinished event. If *block* is True, the contents are loaded
        directly, i.e. the method waits for the search to finish.
        """
        if self.contents is None:
            # Only the root node stores an reference to the model
            model = self.getRoot().model
            if not block:
                self.setContents([LoadingNode()])
                model._startLoading(self)
                # The contents will be added in BrowserModel._loaded
            else:
                model._startLoading(self, block=True)
                    

class TagNode(CriterionNode):
    """A TagNode groups elements which have the same value in one or more tags: To be precise it will
    contain all nodes having at least one of the (tagId, valueId)-pairs from self.tagIds in their tags.
    This construction allows TagNodes to represent the same value in different tags and also several
    different values. 
    
    Attributes:
        - 'tagIds': Describes the set of elements below this one, see above.
        - 'values', 'sortValues': List of tuples (value, matching) with the values that should be displayed
          for this node. The second tuple component specifies whether the value is directly matched by
          the current browser search criterion.
        - 'matching': Whether at least one of the values in this node directly matches the search criterion.
    """
    def __init__(self, layerIndex):
        super().__init__(layerIndex)
        self.tagIds = set()
        self.values = []
        self.sortValues = []
        self.hide = True # will be corrected in addTagVaulue
        self.matching = False
    
    def getCriterion(self):
        return search.criteria.TagIdCriterion(self.tagIds)

    def getValues(self):
        """Return a list with all values of this node."""
        return [value for value, matching in self.values]
    
    def addTagValue(self, tagId, valueId, value, hide, sortValue, matching):
        """Add (*tagId*, *valueId*)-mapping to self.tagIds and a *value* and *sortValue* to the list of
        values to display. *matching* specifies whether this value was directly matched by the current
        browser search criterion.
        """
        if (tagId, valueId) not in self.tagIds:
            self.tagIds.add((tagId, valueId))
            self._addValue(self.values, value, matching)
            self._addValue(self.sortValues, sortValue if sortValue is not None else value, matching)
            self.hide = self.hide and hide # node.hide <=> all values are hidden
            if matching:
                self.matching = True
        
    def _addValue(self, list, value, matching):
        """Add the tuple (*value*, *matching*) to the given list (either self.values or self.sortValues).
        """
        for pair in list:
            if pair[0] == value:
                if matching and not pair[1]:
                    pair[1] = True
                return
        list.append([value, matching])
        list.sort(key=lambda t: t[0])
        
    def merge(self, other):
        """Merge the TagNode *other* into this node."""
        for value, matching in other.values:
            self._addValue(self.values, value, matching)
        for value, matching in other.sortValues:
            self._addValue(self.sortValues, value, matching)
        if self.hide and not other.hide:
            self.hide = False
        if not self.matching and other.matching:
            self.matching = True
        
    def __repr__(self):
        return "<ValueNode {} {}>".format(self.values, self.tagIds)
    
    def getKey(self):
        return 'tag:' + str(self.tagIds)

    def toolTipText(self):
        from maestro.core import tags
        return '{} ({})'.format(' or '.join(self.getValues()),
                                '/'.join(tags.get(id).title for (id,_) in self.tagIds))


class VariousNode(CriterionNode):
    """A VariousNode groups elements in a tag-layer which have no tag in any of the tags in the tag-layer's
    tagset."""
    def __init__(self, layerIndex, tagSet):
        """Initialize this VariousNode with the parent-node <parent>, the given model and the tag-layer's
        tagset *tagSet*."""
        super().__init__(layerIndex)
        self.tagSet = tagSet

    def getCriterion(self):
        criterion = search.criteria.AnyTagCriterion(tagList=list(self.tagSet))
        criterion.negate = True
        return criterion
    
    def __repr__(self):
        return "<VariousNode>"
        
    def toolTipText(self):
        return translate('VariousNode', 'Elements that do not appear above')


class HiddenValuesNode(Node):
    """A node that contains hidden value nodes."""
    def __init__(self, nodes):
        super().__init__()
        self.setContents(nodes)
        
    def __repr__(self):
        return "<HiddenValues>"
        
    def toolTipText(self):
        return translate('HiddenValuesNode', 'Values that have been marked as hidden')
               

class BrowserWrapper(Wrapper):
    """For performance reasons the browser does not load contents of Wrappers directly. Instead it uses
    BrowserWrappers which will load their contents when they are requested for the first time."""
    def __init__(self, element, position=None):
        assert element.isContainer() and len(element.contents) > 0
        self.element = element
        self.position = position
        self.parent = None
        self.contents = None
    
    def hasContents(self):
        return True
    
    def getContentsCount(self):
        if self.contents is None:
            self.loadContents(False)
        return super().getContentsCount()
        
    def getContents(self):
        if self.contents is None:
            self.loadContents(False)
        return self.contents
    
    def loadContents(self, recursive):
        if recursive:
            super().loadContents(recursive=True)
        else:
            # Contrary to the parent implementation use BrowserWrapper-instances
            # for non-empty containers in the contents
            elements = levels.real.collect(self.element.contents)
            self.setContents([(BrowserWrapper if el.isContainer() and len(el.contents) > 0 else Wrapper)
                              (el, position=pos)
                          for el, pos in zip(elements, self.element.contents.positions)])
    
        
class LoadingNode(TextNode):
    """This is a placeholder for those moments when we must wait for a search to terminate before we can
    display the real contents. The delegate will draw the string "Loading...".
    """
    def __init__(self):
        super().__init__(translate("BrowserModel", "Loading..."))
        
    def __repr__(self):
        return "<Loading>"