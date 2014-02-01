# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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
from .. import config, search, database as db, logging, utils, search as searchmodule
from ..core import tags, levels, elements
from ..core.elements import Element
from ..core.nodes import Node, RootNode, Wrapper, TextNode
from ..gui import selection

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

searchEngine = None # The search engine used by all browsers

# Registered layer classes. Maps names -> (title, class)
layerClasses = collections.OrderedDict()


def addLayerClass(name, title, theClass):
    """Register a class that can be used for the browser's layers under the given name."""
    theClass.className = name
    layerClasses[name] = (title, theClass)
    

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
    
    def __init__(self, view, layers):
        super().__init__()
        self.table = None
        self.level = levels.real
        self.layers = layers
        self.view = view
        self.containerLayer = ContainerLayer()
        self._searchRequests = []
        
        if searchEngine is None:
            initSearchEngine()
        searchEngine.searchFinished.connect(self._handleSearchFinished)
    
    def getLayer(self, index):
        assert index >= 0
        if index < len(self.layers):
            return self.layers[index]
        else: return self.containerLayer
        
    def setLayers(self, layers):
        self.layers = layers
        self.reset()
        
    def addLayer(self, layer):
        self.insertLayer(len(self.layers), layer)
    
    def insertLayer(self, index, layer):
        self.layers.insert(index, layer)
        self.reset()
    
    def changeLayer(self, layer, newLayer):
        self.layers[self.layers.index(layer)] = newLayer
        self.reset()
        
    def moveLayer(self, fromIndex, toIndex):
        if toIndex in (fromIndex, fromIndex+1):
            return # no change
        layer = self.layers[fromIndex]
        del self.layers[fromIndex]
        self.layers.insert(toIndex, layer)
        self.reset()
        
    def removeLayer(self, index):
        del self.layers[index]
        self.reset()
        
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
            super().reset()
    
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

    def createWrapperToolTip(self, wrapper, showFileNumber=False, **kwargs):
        # disable filenumbers because containers in the browser often do not contain all of their element's
        # contents. Also BrowserWrappers might not have loaded their contents yet.
        return super().createWrapperToolTip(wrapper, showFileNumber=showFileNumber, **kwargs)
        
    def _startLoading(self, node, block=False):
        """Start loading the contents of *node*, which must be either root or a CriterionNode (The contents of
        containers are loaded via Container.loadContents). If *node* is a CriterionNode, start a search for
        the contents. The actual loading will be done in the searchFinished event. Only the rootnode is
        loaded directly. If *block* is True this method will block until the node is loaded. 
        """
        if node == self.root:
            oldHasContents = self.hasContents()
            # No need to search...load directly
            layer = self.getLayer(0)
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
            layer = self.getLayer(self._getLayerIndex(node) + 1)
            criteria = [p.getCriterion() for p in node.getParents(includeSelf=True)
                        if isinstance(p, CriterionNode)]
            method = searchEngine.search if not block else searchEngine.searchAndBlock
            searchRequest = method(self.table, criteria, data=(layer, node),
                                   postProcessing=[searchmodule.findExtendedToplevel])
            if not block:
                self._searchRequests.append(searchRequest)
                # further loading is done when the search is finished
            else:
                # Load directly
                layer, node = searchRequest.data
                self.load(layer, node, ElementSource(request=searchRequest), _loadContainersRecursively=True)
                for child in node.getContents():
                    if isinstance(child, CriterionNode):
                        self._startLoading(child, block=True)
                
    def _getLayerIndex(self, node):
        if isinstance(node, Wrapper): 
            return len(self.layers) # always use containerLayer
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
            self.load(layer, node, ElementSource(request=searchRequest))
    
    def load(self, layer, node, elementSource, _loadContainersRecursively=False):
        if isinstance(layer, ContainerLayer):
            contents = layer.load(self, node, elementSource, recursive=_loadContainersRecursively)
        else: contents = layer.load(self, node, elementSource)
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
    def __init__(self, table=None, request=None):
        assert table is not None or request is not None
        if table is not None:
            self.table = table
            self.ids = None
            if self.table == db.prefix + 'elements':
                majorContainers = db.query("SELECT id FROM {}elements WHERE file = 0 AND type IN ({})"
                                           .format(db.prefix, db.csList(elements.MAJOR_TYPES)))\
                                           .getSingleColumn()
            else:
                majorContainers = db.query("""
                            SELECT el.id
                            FROM {}elements AS el JOIN {} AS res ON el.id = res.id
                            WHERE el.file = 0 AND el.type IN ({})
                            """.format(db.prefix, table, db.csList(elements.MAJOR_TYPES))).getSingleColumn()
            descendantsOfMajor = db.csList(db.contents(majorContainers, recursive=True))
            if len(descendantsOfMajor) > 0:
                self.extendedToplevel = set(db.query("SELECT id FROM {} WHERE id NOT IN  ({})"
                                                     .format(table, descendantsOfMajor)).getSingleColumn())
            else:
                self.extendedToplevel = set(db.query("SELECT id FROM {}".format(table)).getSingleColumn())
        else:
            self.table = None
            self.ids = request.result
            self.extendedToplevel = request.extendedToplevel
            
    def computeToplevel(self):
        self.toplevel = set(db.query("""
                    SELECT res.id
                    FROM {} AS res LEFT JOIN {}contents AS c ON res.id = c.element_id
                    WHERE c.element_id IS NULL 
                    """.format(self.table, db.prefix)).getSingleColumn())
        

class TagLayer:
    """
        More features:
    
        - Hidden values: Values from values_varchar with the hidden flag are stuffed into HiddenValueNodes
          (unless the showHiddenValues option is set to True).
        - Elements that don't have a value in any of the tags used in a taglayer are stuffed into a
          VariousNode (if a container has no artist-tag the reason is most likely that its children have
          different artists).
          """
    def __init__(self, tagList=None, state=None):
        if tagList is None:
            assert state is not None
            tagList = [tags.get(name) for name in state]
        if any(tag.type != tags.TYPE_VARCHAR for tag in tagList):
            logger.warning("Only tags of type varchar are permitted in the browser's layers.")
            tagList = {tag for tag in tagList if tag.type == tags.TYPE_VARCHAR}
        self.tagList = tagList
        self.showHiddenValues = False
        
    def text(self):
        return '{}: {}'.format(translate("BrowserModel", "Tag layer"),
                               ', '.join(tag.title for tag in self.tagList))
    
    def state(self):
        return [tag.name for tag in self.tagList]
    
    def __repr__(self):
        return "<TagLayer: {}>".format(', '.join(tag.name for tag in self.tagList))
        
    def load(self, model, node, elementSource):
        # Get all tag values that should appear in TagNodes 
        
        if elementSource.table is not None:
            table = elementSource.table
        else: table = db.prefix+'elements'
        if len(elementSource.extendedToplevel) > 0:
            idFilter = 'res.id IN ({}) '.format(db.csList(elementSource.extendedToplevel))
        else: idFilter = '1' # for use in AND-clauses
        tagFilter = db.csIdList(self.tagList)
        
        if db.type == 'sqlite':
            collate = 'COLLATE NOCASE'
        else: collate = ''

        result = db.query("""
            SELECT DISTINCT t.tag_id, v.id, v.value, v.hide, v.sort_value
            FROM {1} AS res JOIN {0}tags AS t ON +res.id = t.element_id
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
                
            if not hide or self.showHiddenValues:
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
    
        # If there are not too many nodes, combine nodes with the same contents.
        if 2 <= len(nodes) <= 10 and 1 <= len(elementSource.extendedToplevel) <= 250:
            valuePart = ' OR '.join('(tag_id={} AND value_id={})'
                                    .format(*node.tagPairs[0]) for node in nodes)
            result = db.query("""
                        SELECT element_id, tag_id, value_id
                        FROM {}tags
                        WHERE element_id IN ({}) AND ({})
                        """.format(db.prefix, db.csList(elementSource.extendedToplevel), valuePart))
            elementDict = {}
            for node in nodes:
                theSet = set() # use the same set for each tagPair of one node
                for tagId, valueId in node.tagPairs:
                    elementDict[(tagId, valueId)] = theSet
            for elid, tid, vid in result:
                elementDict[(tid, vid)].add(elid)   
            
            # EXPERIMENTAL: If there are only a few composers, use them as tag nodes (no artists etc.)
            composerTag = tags.get("composer")
            if composerTag.isInDb():
                composers = [pair for pair in elementDict.keys() if pair[0] == composerTag.id]
                if len(composers) <= 3:
                    inComposers = set().union(*[elementDict[c] for c in composers])
                    if len(inComposers) == len(elementSource.extendedToplevel):
                        for node in nodes[:]:
                            if not any(pair[0] == composerTag.id for pair in node.tagPairs):
                                nodes.remove(node)
                              
            # Combine nodes with the same contents.
            hashs = {}
            for node in nodes[:]:
                elementSet = elementDict[node.tagPairs[0]]
                h = hash(frozenset(elementSet))
                if h not in hashs:
                    hashs[h] = node
                else:
                    hashs[h].addValues(node)
                    nodes.remove(node)
                
        # Check whether a VariousNode is necessary
        result = db.query("""
            SELECT res.id
            FROM {1} AS res LEFT JOIN {0}tags AS t
                                ON res.id = t.element_id AND t.tag_id IN ({2})
            WHERE {3} AND t.value_id IS NULL
            LIMIT 1
            """.format(db.prefix, table, tagFilter, idFilter))

        if len(result) > 0:
            nodes.append(VariousNode(node, self.tagList))
            
        if len(hiddenNodes) > 0:
            # If hidden nodes are present this layer needs two actual levels in the tree structure
            # Since this interferes with the algorithm to determine the layer of a node, we have to store
            # that layer index. See BrowserModel._getLayerIndex
            for node in hiddenNodes:
                node.layer = self
            nodes.append(HiddenValuesNode(node, hiddenNodes))
        
        return nodes
    
    @staticmethod
    def defaultTagList():
        tagList = [tags.get(name) for name in ('artist', 'composer', 'performer')]
        return [tag for tag in tagList if tag.isInDb() and tag.type == tags.TYPE_VARCHAR]
    
    @staticmethod
    def openDialog(parent, layer=None):
        from PyQt4 import QtGui
        tagList = layer.tagList if layer is not None else TagLayer.defaultTagList()
        text, ok = QtGui.QInputDialog.getText(parent, translate("TagLayer", "Configure tag layer"),
                        translate("TagLayer", "Enter the names/titles of the tags that should "
                                  "be used to group elements."),
                        text=', '.join(tag.title for tag in tagList))
        if ok:
            try:
                tagList = [tags.fromTitle(name.strip()) for name in text.split(',')]
                if len(tagList) == 0 \
                        or not all(tag.isInDb() and tag.type == tags.TYPE_VARCHAR for tag in tagList):
                    raise ValueError()
            except:
                QtGui.QMessageBox.error(parent, translate("TagLayer", "Invalid value"),
                        translate("TagLayer", "Only varchar-tags registered in the database may be used."))
            else:
                return TagLayer(tagList)
        return None


addLayerClass('taglayer', translate("BrowserModel", "Tag layer"), TagLayer)


class ContainerLayer:
    def load(self, model, node, elementSource, recursive=False):
        """Load the contents of *node* into a container-layer, using toplevel elements from *table*. Note that
        this creates all children of *node* and not only the next level of the tree-structure as _loadTagLayer
        does.
        """
        if elementSource.table is None:
            allIds = elementSource.ids
            if len(allIds) == 0:
                toplevel = []
            else:
                toplevel = elementSource.extendedToplevel.difference(
                             db.query("SELECT element_id FROM {}contents WHERE container_id IN ({})"
                                      .format(db.prefix, db.csList(allIds))).getSingleColumn())
        else:
            elementSource.computeToplevel()
            toplevel = elementSource.toplevel

        # Load all toplevel elements and all of their ancestors
        newIds = toplevel
        while len(newIds) > 0:
            levels.real.collectMany(newIds)
            nextIds = []
            for id in newIds:
                nextIds.extend(levels.real[id].parents)
            newIds = nextIds

        # Collect all parents in cDict (mapping parent id -> list of children ids)
        # Parents contained as key in this dict, will only contain part of their element's contants in
        # the browser. The part is given by the corresponding value (a list) in this dict.
        # The dict must not contain direct search results as keys, as they should always show all their
        # contents.
        cDict = collections.defaultdict(list)
            
        def processNode(id):
            """Check whether the element with the given id has major parents that need to be added to the 
            browser's tree. If such a parent is found, update cDict and toplevel and return True.
            """
            result = False
            for pid in levels.real[id].parents:
                if pid in cDict: # We've already added this parent
                    result = True
                    cDict[pid].append(id)
                    toplevel.discard(id)
                elif pid in allIds: # This parent belongs to the direct search result
                    result = True
                    toplevel.discard(id)
                elif processNode(pid): # We must add this parent, because it has a major ancestor.
                    result = True
                    cDict[pid].append(id)
                    toplevel.discard(id)
                elif levels.real[pid].isMajor(): # This is a major parent. Add it to toplevel
                    result = True
                    cDict[pid].append(id)
                    toplevel.discard(id)
                    toplevel.add(pid)
            return result
        
        for id in list(toplevel): # copy!
            processNode(id)
        
        def createWrapper(id):
            """Create a wrapper to be inserted in the browser. If the wrapper should contain all of its
            element's contents, create a BrowserWrapper, that will load the contents """
            element = levels.real[id]
            if id in cDict:
                wrapper = Wrapper(element)
                wrapper.setContents([createWrapper(cid) for cid in cDict[id]])
                return wrapper
            elif element.isFile() or len(element.contents) == 0:
                return Wrapper(element)
            elif recursive:
                w = Wrapper(element)
                w.loadContents(recursive=True)
                return w
            else:
                return BrowserWrapper(element) # a wrapper that will load all its contents when needed
        
        contents = [createWrapper(id) for id in toplevel]
        
        contents.sort(key=self.sortFunction)
        return contents
    
    def sortFunction(self, wrapper):
        element = wrapper.element
        date = 0
        if element.isContainer() and element.type == elements.TYPE_ALBUM:
            dateTag = tags.get("date")
            if dateTag.type == tags.TYPE_DATE and dateTag in element.tags: 
                date = -element.tags[dateTag][0].toSql() # minus leads to descending sort
        return (date, element.getTitle())


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
                                               
    def loadContents(self, block=False):
        """If they are not loaded yet, start to load the contents of this node. The actual loading is done
        by the model when it reacts to the searchFinished event. If *block* is True, the contents are loaded
        directly, i.e. the method waits for the search to finish.
        """
        if self.contents is None:
            # Only the root node stores an reference to the model
            parent = self.parent
            while parent.parent is not None:
                parent = parent.parent
            model = parent.model
            if not block:
                self.setContents([LoadingNode()])
                model._startLoading(self)
                # The contents will be added in BrowserModel.searchFinished
            else:
                model._startLoading(self, block=True)


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
    
    def getKey(self):
        return "tag:"+str(self.tagPairs)


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
        
    def __repr__(self):
        return "<Loading>"
        

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
                                                                for node in self.nodes(onlyToplevel=True)))
            #assert self._wrappers[0].contents is not None
            self._wrappersLoaded = True
        return self._wrappers
                                          
    def _getElementsInstantly(self, node):
        """If *node* is a CriterionNode return all (toplevel) elements contained in it. If contents have to
        be loaded, block until the search is finished. If *node* is an element return ''[node]''.
        """
        if isinstance(node, Wrapper):
            node.loadContents(recursive=True) 
            return [node]
        if isinstance(node, CriterionNode):
            if node.contents is None:
                node.loadContents(block=True)
                if node.contents is None: # should never be the case
                    logger.debug("Could not load contents of node instantly: {}".format(node))
                    return []
            return itertools.chain.from_iterable(self._getElementsInstantly(child)
                                                 for child in node.contents)
        else: return [] # Should be a LoadingNode
