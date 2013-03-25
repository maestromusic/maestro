# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

import itertools, collections

from PyQt4 import QtCore
from PyQt4.QtCore import Qt

from . import rootedtreemodel
from .. import config, search, database as db, logging, utils
from ..core import tags, levels
from ..core.elements import Element
from ..core.nodes import Node, RootNode, Wrapper, TextNode
from ..gui import selection

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

searchEngine = None # The search engine used by all browsers



def initSearchEngine():
    """Initialize the single search engine used by all browsers. This is called automatically, when the first
    browser is created."""
    global searchEngine
    if searchEngine is None:
        searchEngine = search.SearchEngine()
                
    
class BrowserModel(rootedtreemodel.RootedTreeModel):
    """ItemModel for the BrowserTreeViews (a browser may have several views and hence several models). The
    model will group its contents according to the parameter *layers*. TODO improve comment
    """
    nodeLoaded = QtCore.pyqtSignal(Node)
    hasContentsChanged = QtCore.pyqtSignal(bool)
    
    def __init__(self, layers):
        super().__init__()
        self.table = None
        self.level = levels.real
        self.layers = layers
        self.layers.append(ContainerLayer(sorting=Sorting([tags.TITLE])))
        self._searchRequests = []
        
        if searchEngine is None:
            initSearchEngine()
        searchEngine.searchFinished.connect(self._handleSearchFinished)
    
    def hasContents(self):
        """Return whether the current model contains elements."""
        # A textnode is only used in empty models to display e.g. "no search results"
        return len(self.root.contents) >= 1 and not (isinstance(self.root.contents[0], TextNode))
    
    def reset(self, table=None):
        """Reset the model reloading all data from self.table. If *table* is given, first set self.table to
        *table*."""
        for request in self._searchRequests:
            request.stop()
        self._searchRequests = []
        
        if table is not None:
            self.table = table
        if self.table is not None:
            self._startLoading(self.root)
            rootedtreemodel.RootedTreeModel.reset(self)
    
    def setShowHiddenValues(self, showHiddenValues):
        """Show or hide ValueNodes where the hidden-flag in values_varchar is set."""
        reset = False
        for layer in self.layers:
            if isinstance(layer, TagLayer):
                if layer.showHiddenValues != showHiddenValues:
                    reset = True
                layer.showHiddenValues = showHiddenValues
        if reset:
            self.reset()
            
    def flags(self,index):
        defaultFlags = rootedtreemodel.RootedTreeModel.flags(self,index)
        if index.isValid():
            return defaultFlags | Qt.ItemIsDragEnabled
        else: return defaultFlags
    
    def mimeTypes(self):
        return [config.options.gui.mime]
        
    def mimeData(self, indexes):
        return BrowserMimeData.fromIndexes(self, indexes)

    def _startLoading(self, node, wait=False):
        """Start loading the contents of *node*, which must be either root or a CriterionNode (The contents of
        containers are loaded via Container.loadContents). If *node* is a CriterionNode, start a search for
        the contents. The actual loading will be done in the searchFinished event. Only the rootnode is
        loaded directly. If *wait* is True this method will wait until the node is loaded. 
        """
        if node == self.root:
            oldHasContents = self.hasContents()
            # No need to search...load directly
            layer = self.layers[0]
            self.load(layer, node, ElementSource(table=self.table))
            if len(self.root.contents) == 0:
                if self.table == 'elements':
                    text = self.tr("Your database is empty."
                                   " Drag files from the filesystembrowser into the editor,"
                                   " modify them and click 'Commit'.")
                else:
                    text = self.tr("No elements found.")
                self.beginInsertRows(QtCore.QModelIndex(), 0, 0)
                self.root.setContents([TextNode(text, wordWrap=True)])
                self.endInsertRows()
            if self.hasContents() != oldHasContents:
                self.hasContentsChanged.emit(self.hasContents())
        else:
            layer = self.layers[self._getLayerIndex(node) + 1]
            criteria = [p.getCriterion() for p in node.getParents(includeSelf=True)
                        if isinstance(p, CriterionNode)]
            method = searchEngine.search if not wait else searchEngine.searchAndWait
            searchRequest = method(self.table, criteria, data=(layer, node))
            if not wait:
                self._searchRequests.append(searchRequest)
                
    def _getLayerIndex(self, node):
        if isinstance(node, Wrapper): # always use the container layer self.layers[-1]
            return -1
        elif node.parent is self.root:
            return 0
        elif hasattr(node, 'layer'):
            return self.layers.index(getattr(node, 'layer'))
        else: return self._getLayerIndex(node.parent) + 1
                            
    def _handleSearchFinished(self, searchRequest):
        """Handle the searchFinished-event for *searchRequest*: Load the contents of the node
        ''searchRequest.data'' and emit a nodeLoaded signal.
        """
        if searchRequest in self._searchRequests:
            layer, node = searchRequest.data
            self._searchRequests.remove(searchRequest)
            self.load(layer, node, ElementSource(ids=searchRequest.result, toplevel=searchRequest.toplevel))
    
    def load(self, layer, node, elementSource):
        contents = layer.load(node, elementSource)
        if node.contents is not None:
            # Only use beginRemoveRows and friends if there are already contents. If we are going to add the
            # first contents to node (this happens thanks to the directload shortcut), we must not call
            # those methods as Qt will then try to access the contents...resulting in _startLoading.
            contentsWereNone = False
            self.beginRemoveRows(self.getIndex(node), 0, len(node.contents)-1)
            node.setContents([])
            self.endRemoveRows()
            self.beginInsertRows(self.getIndex(node), 0, len(contents)-1)
            node.setContents(contents)
            self.endInsertRows()
        else:
            node.setContents(contents)
        self.nodeLoaded.emit(node)


class ElementSource:
    def __init__(self, ids=None, toplevel=None, table=None):
        assert table is not None or (ids is not None and toplevel is not None)
        self.ids = ids
        self.toplevel = toplevel
        self.table = table
        
        
class Sorting:
    def __init__(self, sortTags):
        self.sortTags = sortTags
        
    def sort(self, elements):
        for tag in reversed(self.sortTags):
            reverse = tag.type == tags.TYPE_DATE
            p = utils.PointAtInfinity(not reverse)
            elements.sort(
                # TODO: respect sortvalues for e.g. composers
                key = lambda wr: wr.element.tags[tag][0] if tag in wr.element.tags else p,
                reverse = reverse
            )        


class TagLayer:
    def __init__(self, tagList):
        if any(tag.type != tags.TYPE_VARCHAR for tag in tagList):
            logger.warning("Only tags of type varchar are permitted in the browser's layers.")
            tagList = {tag for tag in tagList if tag.type == tags.TYPE_VARCHAR}
        self.tagList = tagList
        self.showHiddenValues = False
        
    def load(self, node, elementSource):
        # Get all values and corresponding ids of the given tag appearing in at least one toplevel result.
        if elementSource.table is not None:
            table = elementSource.table
            idFilter = 'res.toplevel = 1'
        else:
            table = db.prefix+'elements'
            idFilter = ' res.id IN ({}) '.format(db.csList(elementSource.toplevel))
        tagFilter = db.csIdList(self.tagList)
        
        # Get all tag values that should appear in TagNodes 
        #TODO toplevel is wrong in case of id list
        if db.type == 'sqlite':
            collate = 'COLLATE NOCASE'
        else: collate = ''
        result = db.query("""
            SELECT DISTINCT t.tag_id, v.id, v.value, v.hide, v.sort_value
            FROM {1} AS res JOIN {0}tags AS t ON res.id = t.element_id
                     JOIN {0}values_varchar AS v ON t.tag_id = v.tag_id AND t.value_id = v.id
            WHERE t.tag_id IN ({2}) AND {3}
            ORDER BY COALESCE(v.sort_value, v.value) {4}
        """.format(db.prefix, table, tagFilter, idFilter, collate))
    
        nodes = []
        hiddenNodes = []
        values = set()
    
        for row in result:
            tagId, valueId, value, hide, sortValue = row
            if db.isNull(sortValue):
                sortValue = None
                
            if self.showHiddenValues or not hide:
                theList = nodes
            else: theList = hiddenNodes
            
            if value not in values:
                theList.append(TagNode(node, value, [(tagId, valueId)], sortValue))
                values.add(value)
            else:
                # If there is already a value node with this value,
                # add tagId -> valueId to that node
                for aNode in theList:
                    if value in aNode.values:
                        aNode.tagPairs.append((tagId, valueId))
                        break
    
        # Check whether a VariousNode is necessary
        result = db.query("""
            SELECT t.value_id
            FROM {1} AS res LEFT JOIN {0}tags AS t
                                ON res.id = t.element_id AND t.tag_id IN ({2}) AND {3}
            WHERE t.value_id IS NULL
            LIMIT 1
            """.format(db.prefix, table, tagFilter, idFilter))

        if len(result) > 0:
            nodes.append(VariousNode(node, self.tagList))
            
        if len(hiddenNodes) > 0:
            # If hidden nodes are present this layer needs two actual levels in the tree structure
            # Since this interferes with the algorithm to determine the layer of a node, we have to store
            # that layer. See BrowserModel._getLayerIndex
            for node in hiddenNodes:
                node.layer = self
            nodes.append(HiddenValuesNode(node, hiddenNodes))
        
        return nodes


class ContainerLayer:
    def __init__(self, sorting):
        self.sorting = sorting
        
    def load(self, node, elementSource):
        """Load the contents of *node* into a container-layer, using toplevel elements from *table*. Note that
        this creates all children of *node* and not only the next level of the tree-structure as _loadTagLayer
        does. For performance reasons this method does not load the data (''Element.fromId(loadData=False)'').
        """
        if elementSource.table is None:
            allIds = elementSource.ids
            toplevel = elementSource.toplevel
        else:
           raise NotImplementedError()

        # Load all toplevel elements and all of their ancestors
        newIds = toplevel
        while len(newIds) > 0:
            levels.real.collectMany(newIds)
            nextIds = []
            for id in newIds:
                nextIds.extend(levels.real[id].parents)
            newIds = nextIds

        # Collect all parents in cDict (mapping parent id -> list of children ids)
        # Only add elements which are not direct search results
        cDict = collections.defaultdict(list)
            
        def processNode(id):
            result = False
            for pid in levels.real[id].parents:
                if pid in cDict or pid in allIds or processNode(pid):
                    result = True
                    cDict[pid].append(id)
                    toplevel.discard(id)
                elif levels.real[pid].major:
                    result = True
                    cDict[pid].append(id)
                    toplevel.discard(id)
                    toplevel.add(pid)
                
            return result
        
        for id in list(toplevel): # copy!
            processNode(id)
        
        def createWrapper(id):
            element = levels.real[id]
            if id in cDict:
                wrapper = Wrapper(element)
                wrapper.setContents([createWrapper(cid) for cid in cDict[id]])
                return wrapper
            elif element.isFile() or len(element.contents) == 0:
                return Wrapper(element)
            else:
                return BrowserWrapper(element) # a wrapper that will load its contents when needed
        
        contents = [createWrapper(id) for id in toplevel]
        self.sorting.sort(contents)
        return contents


class CriterionNode(Node):
    """CriterionNode is the base class for nodes used to group elements according to a criterion (confer 
    search.criteria) in a BrowserModel. The level below this node will contain all elements of this level
    that match the criterion."""
    def __init__(self, parent):
        """Initialize this CriterionNode with the parent-node <parent> and the given model and criterion."""
        self.parent = parent
        self.contents = None

    
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
    
    def getAllNodes(self):
        if self.contents is None:
            return
        else: 
            for node in super().getAllNodes():
                yield node
            
    def hasLoaded(self):
        """Return whether this CriterionNode did already load its contents."""
        return self.contents is not None and (len(self.contents) != 1 
                                               or not isinstance(self.contents[0], LoadingNode))
                                               
    def loadContents(self, wait=False):
        """If they are not loaded yet, start to load the contents of this node. The actual loading is done
        by the model when it reacts to the searchFinished event. If *wait* is True, the contents are loaded
        directly, i.e. the method waits for the search to finish.
        """
        if self.contents is None:
            # Only the root node stores an reference to the model
            parent = self.parent
            while parent.parent is not None:
                parent = parent.parent
            model = parent.model
            if not wait:
                self.setContents([LoadingNode()])
                
                model._startLoading(self)
                # The contents will be added in BrowserModel.searchFinished
            else:
                model._startLoading(self, wait=True) # block until the contents are loaded


class TagNode(CriterionNode):
    """A TagNode groups elements which have the same tag-value in one or more tags. Not that only the value
    must coincide, the tags need not be the same, but they must be in a given list. This enables BrowserViews
    display e.g. all artists and all composers in one tag-layer.
    """
    def __init__(self, parent, value, tagPairs, sortValue):
        """Initialize this ValueNode with the parent-node *parent* and the given model. *valueIds* is a dict
        mapping tag-ids to value-ids of the tag. This node will contain elements having at least one of the
        value-ids in the corresponding tag. *value* is the value of the value-ids (which should be the same
        for all tags) and will be displayed on the node.
        """
        CriterionNode.__init__(self, parent)
        self.tagPairs = tagPairs
        self.values = [value]
        self.sortValues = [sortValue if sortValue is not None else value]
    
    def getCriterion(self):
        return search.criteria.TagIdCriterion(self.tagPairs)

    def addValues(self, other):
        """Add the values (and sortValues) of *other* to this node. This won't affect the contents of this
        node, so be sure to call this node only when it makes sense.
        """
        self.values.extend(other.values)
        self.values.sort()
        self.sortValues.extend(other.sortValues)
        self.sortValues.sort()
        
    def __repr__(self):
        return "<ValueNode {} {}>".format(self.values, self.tagPairs)
    
    def toolTipText(self):
        if config.options.misc.show_ids: # Display the value-ids
            lines = ["[{}]".format(", ".join("{}->{}".format(tags.get(tagId).name, valueId)
                                    for tagId,valueId in self.tagPairs))]
            lines.extend(self.values)
        else: lines = self.values
        return '\n'.join(lines)


class VariousNode(CriterionNode):
    """A VariousNode groups elements in a tag-layer which have no tag in any of the tags in the tag-layer's
    tagset."""
    def __init__(self, parent, tagSet):
        """Initialize this VariousNode with the parent-node <parent>, the given model and the tag-layer's
        tagset *tagSet*."""
        CriterionNode.__init__(self, parent)
        self.tagSet = tagSet

    def getCriterion(self):
        criterion = search.criteria.TagCriterion(value=None, tagList=list(self.tagSet))
        criterion.negate = True
        return criterion
    
    def __repr__(self):
        return "<VariousNode>"
        
    def toolTipText(self):
        return None


class HiddenValuesNode(Node):
    """A node that contains hidden value nodes."""
    def __init__(self, parent, nodes):
        self.parent = parent
        self.setContents(nodes)
        
    def __repr__(self):
        return "<HiddenValues>"
        
    def toolTipText(self):
        return None
               

class BrowserWrapper(Wrapper):
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
        # Contrary to the parent implementation use BrowserWrapper for non-empty containers in the contents
        if recursive:
            super().loadContents(recursive=True)
            return
        elements = levels.real.collectMany(self.element.contents)
        self.setContents([(BrowserWrapper if el.isContainer() and len(el.contents) > 0 else Wrapper)
                          (el, position=pos)
                          for el, pos in zip(elements, self.element.contents.positions)])
    
        
class LoadingNode(TextNode):
    """This is a placeholder for those moments when we must wait for a search to terminate before we can
    display the real contents. The delegate will draw the string "Loading...".
    """
    def __init__(self):
        super().__init__(translate("BrowserModel", "Loading..."))
        

class BrowserMimeData(selection.MimeData):
    """This is the subclass of selection.MimeData that is used by the browser. The main differences are that
    the browser contains nodes that are no elements and that they may not have loaded their contents yet.   
    """  
    def __init__(self, selection):
        super().__init__(selection)
        self._wrappersLoaded = False

    def wrappers(self):
        if not self._wrappersLoaded:
            # self.nodes() may contain CriterionNodes or (unlikely) LoadingNodes.
            self._wrappers = list(itertools.chain.from_iterable(self._getElementsInstantly(node)
                                                                   for node in self.nodes()))
            self._wrappersLoaded = True
        return self._wrappers
                                          
    def _getElementsInstantly(self,node):
        """If *node* is a CriterionNode return all (toplevel) elements contained in it. If contents have to
        be loaded, wait for the search to finish. If *node* is an element return ''[node]''.
        """
        if isinstance(node, Wrapper):
            return [node]
        if isinstance(node,CriterionNode):
            node.loadContents(wait=True) # This does not load element data
            return itertools.chain.from_iterable(self._getElementsInstantly(child)
                                                    for child in node.getContents())
        else: return [] # Should be a LoadingNode
