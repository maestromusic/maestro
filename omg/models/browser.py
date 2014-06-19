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
translate = QtCore.QCoreApplication.translate

from . import rootedtreemodel
from .. import config, search, database as db, logging, utils, search
from ..core import tags, levels, elements
from ..core.elements import Element
from ..core.nodes import Node, RootNode, Wrapper, TextNode
from ..gui import selection


# Registered layer classes. Maps names -> (title, class)
layerClasses = collections.OrderedDict()


def addLayerClass(name, title, theClass):
    """Register a class that can be used for the browser's layers under the given name."""
    theClass.className = name
    layerClasses[name] = (title, theClass)


class BrowserModel(rootedtreemodel.RootedTreeModel):
    """ItemModel for the BrowserTreeViews (a browser may have several views and hence several models).
    
    Parameters:
        - *domain*: A BrowserModel only displays elements from this domain (exception: Usually all contents
          of an element are displayed; so if a container from this domain contains elements from another
          domain, they will be displayed).
        - *layers*: Used to group elements, see below. Basically each layer is asked to group the contents
          of the nodes of the previous layer. A special ContainerLayer is used after all layers in *layers*.
          In particular *layers* may be an empty list.
        - *filter*: A search criterion or None. The browser will only display elements matching the
          criterion. Use setFilter to change it.
    
    To build its tree structure, the BrowserModel performs the following steps:
        1. The search module is used to find the set of elements matching self.filter. If the latter is None,
           all elements will be displayed.
        2. The first layer is asked to create a list of nodes grouping these elements. For this the layer's
           'build'-method is used.
        3. Nodes returned by a layer must either have their contents already loaded or provide the method
           'getElids' to define the set of elements below this node, or provide the method getCriterion.
           In the latter case the node will contain all elements contained in the parent node matching the
           additional criterion returned by getCriterion.
        4. When a node is expanded whose contents are not loaded yet, getElids/getCriterion is used to
           determine the set of elements below the node. Also the layer of the node is determined (usually
           one layer after the parent node's layer). Then the layer is asked to group the elements.
           
    All these steps are performed in a separate worker thread.
    """
    nodeLoaded = QtCore.pyqtSignal(Node)
    hasContentsChanged = QtCore.pyqtSignal(bool)
    
    def __init__(self, domain, layers, filter):
        super().__init__()
        self.domain = domain
        self.level = levels.real # this is used by the selection-module
        self.layers = layers
        self.containerLayer = ContainerLayer()
        self.filter = filter
        self.worker = utils.worker.Worker(dbConnection=True)
        self.worker.done.connect(self._loaded)
        self.worker.start()
        self._startLoading(self.root)
    
    def shutdown(self):
        """Stop the internal worker thread."""
        self.worker.quit()
        
    def getDomain(self):
        """Return the domain whose elements are displayed."""
        return self.domain
    
    def setDomain(self, domain):
        """Define the domain whose elements are displayed."""
        if domain != self.domain:
            self.domain = domain
            self.reset()
                
    def getLayer(self, index):
        """Return the layer at the given index."""
        assert index >= 0
        if index < len(self.layers):
            return self.layers[index]
        else: return self.containerLayer
        
    def setLayers(self, layers):
        """Set all layers of this model at once."""
        self.layers = layers
        self.reset()
        
    def addLayer(self, layer):
        """Add a layer to the model, after all existing layers."""
        self.insertLayer(len(self.layers), layer)
    
    def insertLayer(self, index, layer):
        """Insert a layer at the given index."""
        self.layers.insert(index, layer)
        self.reset()
    
    def changeLayer(self, layer, newLayer):
        """Replace a layer without changing its position."""
        self.layers[self.layers.index(layer)] = newLayer
        self.reset()
        
    def moveLayer(self, fromIndex, toIndex):
        """Move a layer. *toIndex* must pertain to the list after *fromIndex* has been deleted."""
        if toIndex in (fromIndex, fromIndex+1):
            return # no change
        layer = self.layers[fromIndex]
        del self.layers[fromIndex]
        self.layers.insert(toIndex, layer)
        self.reset()
        
    def removeLayer(self, index):
        """Remove the layer specified by *index*."""
        del self.layers[index]
        self.reset()
    
    def setFilter(self, filter):
        """The model will only display elements matching the given filter. Set *filter* to None to see
        all elements."""
        self.filter = filter
        self.reset()
        
    def hasContents(self):
        """Return whether the current model contains elements."""
        # A textnode is only used in empty models to display e.g. "no search results"
        return self.root.contents is not None and len(self.root.contents) >= 1 \
                and not (isinstance(self.root.contents[0], TextNode))
    
    def reset(self):
        """Reset and reload the browser completely."""
        self.worker.reset()
        super().reset()
        self._startLoading(self.root)
            
    def flags(self, index):
        defaultFlags = rootedtreemodel.RootedTreeModel.flags(self,index)
        if index.isValid():
            return defaultFlags | Qt.ItemIsDragEnabled
        else: return defaultFlags
    
    def mimeTypes(self):
        return [config.options.gui.mime]
        
    def mimeData(self, indexes):
        return BrowserMimeData.fromIndexes(self, indexes)

    def createWrapperToolTip(self, wrapper, showFileNumber=False, **kwargs):
        # disable filenumbers by default because containers in the browser often do not contain all of their
        # element's contents. Also BrowserWrappers might not have loaded their contents yet.
        return super().createWrapperToolTip(wrapper, showFileNumber=showFileNumber, **kwargs)
                
    def _getLayerIndex(self, node):
        """Return the index of the layer to which the given node belongs. Return -1 for the root node."""
        if isinstance(node, Wrapper): 
            return len(self.layers) # always use containerLayer
        elif node is self.root:
            return -1
        elif hasattr(node, 'layer'):
            return self.layers.index(getattr(node, 'layer'))
        else: return self._getLayerIndex(node.parent) + 1
        
    def _startLoading(self, node, block=False):
        """Start loading the contents of *node*, which must be either root or a CriterionNode (The contents
        of containers are loaded via Container.loadContents). If *node* is a CriterionNode, start a search
        for the contents. The actual loading will be done in the searchFinished event. Only the root node is
        loaded directly. If *block* is True this method will block until the node is loaded. 
        """
        layer = self.getLayer(self._getLayerIndex(node) + 1)
        task = None
        if hasattr(node, 'getElids'):
            elids = node.getElids()
            if elids is not None:
                task = LoadTask(self.domain, node, layer, elids=elids)
        if task is None:
            criteria = []
            if self.filter is not None:
                criteria.append(self.filter)
            if node is not self.root:
                criteria.extend(p.getCriterion() for p in node.getParents(includeSelf=True)
                                                 if isinstance(p, CriterionNode))
            criterion = search.criteria.combine('AND', criteria)
            task = LoadTask(self.domain, node, layer, criterion=criterion)
        self.worker.submit(task)
        if block:
            self.worker.join()
            # Usually nodes are only loaded when the _loaded-signal arrives. But usually when block=True
            # is used, the caller expects nodes to be loaded after this method.
            # So: Don't wait for the signal. 
            self._loaded(task) # Do not wait for the signal to arrive because the caller often expe
    
    def _loaded(self, task):
        """This is called (in the main thread) when a task has been processed. It will insert the loaded
        contents into the node."""
        # If _startLoading is called with block=True, _loaded is called twice for the corresponding task.
        # After the first time we set .node to None.
        if task.node is None:
            return
        contents = task.contents
        node = task.node
        task.node = None
        
        if node is self.root:
            hadContents = self.hasContents()
            if len(contents) == 0: 
                if self.filter is None:
                    text = self.tr("Your database is empty or there is no element in domain '{}'."
                                   " Drag files from the filesystembrowser into the editor,"
                                   " modify them and click 'Commit'.".format(self.getDomain().name))
                else:
                    text = self.tr("No elements found.")
                contents = [TextNode(text, wordWrap=True)]
        
        if node.contents is not None:
            # Only use beginRemoveRows and friends if there are already contents. If we add contents for
            # the first time, we must not call those methods or Qt will try to access the contents...
            # resulting in _startLoading.
            self.beginRemoveRows(self.getIndex(node), 0, len(node.contents)-1)
            node.setContents([])
            self.endRemoveRows()
            self.beginInsertRows(self.getIndex(node), 0, len(contents)-1)
            if node is self.root:
                print("SETTING ROOT CONTENTS", len(node.contents), len(contents))
            node.setContents(contents)
            self.endInsertRows()
        else:
            node.setContents(contents)
        
        self.nodeLoaded.emit(node)
        
        if node is self.root and self.hasContents() != hadContents:
            self.hasContentsChanged.emit(self.hasContents())

    
class LoadTask(utils.worker.Task):
    """When a node (either root node or CriterionNode) must load its contents, the browser submits a LoadTask
    to its worker thread. *layer* is the layer to which the node's contents belong. *criterion* is the
    filter that specifies which elements to load as contents.
    """ 
    def __init__(self, domain, node, layer, elids=None, criterion=None):
        # Note to self: If layer and criterion were not immutable,
        # they should be copied here to avoid concurrent access.
        self.domain = domain
        self.node = node
        self.layer = layer
        self.elids = elids
        self.criterion = criterion
        self.contents = None
        
    def merge(self, node):
        return node == self.node
    
    def process(self):
        if self.elids is not None:
            elids = self.elids
        elif self.criterion is not None:
            yield from search.SearchTask(self.criterion, self.domain).process()
            elids = self.criterion.result
        else: elids = None # display all nodes
        matchingTags = self.criterion.getMatchingTags() if self.criterion is not None else []
        if matchingTags is None:
            matchingTags = []
        self.contents = self.layer.build(self.domain, elids, matchingTags)
    
    def __repr__(self):
        return "<TASK:{},{}>".format(self.node, self.criterion)


class Layer:
    def text(self):
        """Return a text representing this layer, e.g. for configuration dialogs."""
        raise NotImplementedError()
    
    def state(self):
        """Return something that can be used to persistently store the configuration of this layer."""
        return None

    def build(self, domain, elids, matchingTags):
        """Return a set of nodes grouping the elements with ids in the set *elids*. All elements are
        assumed to belong to *domain*. *matchingTags* is the set of (tagId, valueId)-tuples, that were
        directly matched by the search query (see search.criteria.Criterion.getMatchingTags). Layers
        may use this to draw corresponding TagNodes in bold.
        """
        raise NotImplementedError()        
        
        
class TagLayer(Layer):
    """
    A TagLayer groups elements by their tag values in a predefined set of tags (e.g. artist & composer).
    
    More features:
    
        - Hidden values: Values from values_varchar with the hidden flag are stuffed into HiddenValueNodes
          (unless the browser's showHiddenValues option is set to True).
        - Elements that don't have a value in any of the tags used in a taglayer are stuffed into a
          VariousNode (if a container has no artist-tag the reason is most likely that its children have
          different artists).
    """
    def __init__(self, browser, tagList=None, state=None):
        self.browser = browser
        if tagList is None:
            assert state is not None
            tagList = [tags.get(name) for name in state]
        if any(tag.type != tags.TYPE_VARCHAR for tag in tagList):
            logging.warning(__name__, "Only tags of type varchar are permitted in the browser's layers.")
            tagList = {tag for tag in tagList if tag.type == tags.TYPE_VARCHAR}
        self.tagList = tagList
        
    def text(self):
        return '{}: {}'.format(translate("BrowserModel", "Tag layer"),
                               ', '.join(tag.title for tag in self.tagList))
    
    def state(self):
        return [tag.name for tag in self.tagList]
    
    def __repr__(self):
        return "<TagLayer: {}>".format(', '.join(tag.name for tag in self.tagList))
        
    def build(self, domain, elids, matchingTags):
        # 1. Get toplevel nodes 
        if elids is None:
            toplevel = set(db.query("""
                    SELECT id
                    FROM {p}elements
                    WHERE domain=? AND id NOT IN (SELECT element_id FROM {p}contents)
                    """, domain.id).getSingleColumn())
            if len(toplevel) == 0:
                return []
        elif len(elids) > 0:
            toplevel = set(elids)
            toplevel.difference_update(db.query(
                     "SELECT element_id FROM {p}contents WHERE container_id IN ({elids})",
                     elids=db.csList(elids)).getSingleColumn())
        else:
            return []
        
        # 2. Add contents of permeable nodes
        new = toplevel
        while len(new):
            new = set(db.query("""
                    SELECT c.element_id
                    FROM {p}contents AS c JOIN {p}elements AS el ON c.container_id = el.id
                    WHERE el.type IN ({collection},{container}) AND el.id IN ({parents})
                    """, collection=elements.TYPE_COLLECTION, container=elements.TYPE_CONTAINER,
                    parents=db.csList(new)).getSingleColumn())
            toplevel.update(new)
        
        
        # 3. Get tag values that might form tag nodes
        idFilter = "el.id IN ({})".format(db.csList(toplevel))
        tagFilter = db.csIdList(self.tagList)
        if db.type == 'sqlite':
            collate = 'COLLATE NOCASE'
        else: collate = ''
        result = db.query("""
            SELECT DISTINCT t.tag_id, v.id, v.value, v.hide, v.sort_value, el.id
            FROM {p}elements AS el JOIN {p}tags AS t ON el.id = t.element_id
                     JOIN {p}values_varchar AS v ON t.tag_id = v.tag_id AND t.value_id = v.id
            WHERE t.tag_id IN ({tagFilter}) AND {idFilter}
            """, tagFilter=tagFilter, idFilter=idFilter, collate=collate)
        
        withinMatchingNodes = set()
        elementSets = collections.defaultdict(set)
        visibleNodes, hiddenNodes = {},{}
        for tagId, valueId, value, hide, sortValue, elid in result:
            if db.isNull(sortValue):
                sortValue = None
            nodes = visibleNodes if not hide or self.browser.showHiddenValues else hiddenNodes
            matching = (tagId,valueId) in matchingTags
            if value not in nodes:
                nodes[value] = node = TagNode()
            else: node = nodes[value]
            node.elids.add(elid)
            if not hide:
                elementSets[elid].add(node)
            if matching and not hide:
                withinMatchingNodes.add(elid)
            node.addTagValue(tagId, valueId, value, sortValue, matching)
        
        visibleNodes = list(visibleNodes.values())
        hiddenNodes = list(hiddenNodes.values())
                
        # 4. Filter unnecessary tag nodes
        def processNodes(nodes):
            nodesToRemove = [] 
            if len(nodes) <= 20:
                for node in nodes:
                    if node.matching or node in nodesToRemove:
                        continue
                    superNodes = set.intersection(*(elementSets[elid] for elid in node.elids))
                    if len(superNodes) > 1:
                        if any(len(superNode.elids) > len(node.elids) for superNode in superNodes):
                            nodesToRemove.append(node)
                        else:
                            # Merge
                            for superNode in superNodes:
                                if superNode != node:
                                    print("Merging", node, superNode)
                                    node.merge(superNode)
                                    print("Removing", superNode)
                                    nodesToRemove.append(superNode)
            nodes = [n for n in nodes if (n.matching or not n.elids <= withinMatchingNodes)
                                        and n not in nodesToRemove]
            nodes.sort(key=lambda node: node.sortValues[0])
            return nodes
        
        visibleNodes = processNodes(visibleNodes)
        hiddenNodes = processNodes(hiddenNodes)
        
        
        # 5. Check whether a VariousNode is necessary
        result = db.query("""
            SELECT el.id
            FROM {p}elements AS el LEFT JOIN {p}tags AS t
                                ON el.id = t.element_id AND t.tag_id IN ({tagFilter})
            WHERE domain={domain} AND {idFilter} AND t.value_id IS NULL
            LIMIT 1
            """, tagFilter=tagFilter, idFilter=idFilter, domain=domain.id)

        if len(result) > 0:
            visibleNodes.append(VariousNode(self.tagList))
            
        # 6. Create HiddenNode
        if len(hiddenNodes) > 0:
            # If hidden nodes are present this layer needs two actual levels in the tree structure
            # Since this interferes with the algorithm to determine the layer of a node, we have to store
            # that layer index. See BrowserModel._getLayerIndex
            for node in hiddenNodes:
                node.layer = self
            visibleNodes.append(HiddenValuesNode(hiddenNodes))
        
        return visibleNodes
    
    @staticmethod
    def defaultTagList():
        """Return the default list of tags in a TagLayer."""
        tagList = [tags.get(name) for name in ('artist', 'composer', 'performer')]
        return [tag for tag in tagList if tag.isInDb() and tag.type == tags.TYPE_VARCHAR]
    
    @staticmethod
    def openDialog(parent, model, layer=None):
        """Open a dialog to configure a new or existing TagLayer."""
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
                return TagLayer(model, tagList)
        return None


addLayerClass('taglayer', translate("BrowserModel", "Tag layer"), TagLayer)


class ContainerLayer(Layer):
    """A Container layer organizes nodes in their natural tree structure."""
    def build(self, domain, elids, matchingTags):
        """Build a container structure containing the elements with ids in *elids*."""
        if elids is None:
            toplevel = list(db.query("""
                    SELECT id
                    FROM {p}elements
                    WHERE domain=? AND id NOT IN (SELECT element_id FROM {p}contents)
                    """, domain.id).getSingleColumn())
        elif len(elids) > 0:
            toplevel = set(elids)
            toplevel.difference_update(db.query(
                     "SELECT element_id FROM {}contents WHERE container_id IN ({})"
                    .format(db.prefix, db.csList(elids))).getSingleColumn())
        else:
            return []
            
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
                elif elids is None or pid in elids: # This parent belongs to the direct search result
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
            if id in cDict: # wrapper should contain only a part of its element's contents
                wrapper = Wrapper(element)
                wrapper.setContents([createWrapper(cid) for cid in cDict[id]])
                return wrapper
            elif element.isFile() or len(element.contents) == 0:
                return Wrapper(element)
            else:
                return BrowserWrapper(element) # a wrapper that will load all its contents when needed
        
        contents = [createWrapper(id) for id in toplevel]
        
        contents.sort(key=self.sortFunction)
        return contents
    
    def sortFunction(self, wrapper):
        """Intelligent sort: sort albums by their date, everything else by name."""
        element = wrapper.element
        date = 0
        if element.isContainer() and element.type == elements.TYPE_ALBUM:
            dateTag = tags.get("date")
            if dateTag.type == tags.TYPE_DATE and dateTag in element.tags: 
                date = -element.tags[dateTag][0].toSql() # minus leads to descending sort
        return (date, element.getTitle(neverShowIds=True))


class CriterionNode(Node):
    """CriterionNode is the base class for nodes used to group elements according to a criterion (confer 
    search.criteria) in a BrowserModel. The layer below this node will contain all elements of this layer
    that additionally match the criterion.
    """
    def __init__(self):
        self.parent = None
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
            parent = self.parent
            while parent.parent is not None:
                parent = parent.parent
            model = parent.model
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
    def __init__(self):
        super().__init__()
        self.tagIds = set()
        self.values = []
        self.sortValues = []
        self.elids = set()
        self.matching = False
    
    def getCriterion(self):
        return search.criteria.TagIdCriterion(self.tagIds)

    def getValues(self):
        """Return a list with all values of this node."""
        return [value for value, matching in self.values]
    
    def addTagValue(self, tagId, valueId, value, sortValue, matching):
        """Add (*tagId*, *valueId*)-mapping to self.tagIds and a *value* and *sortValue* to the list of
        values to display. *matching* specifies whether this value was directly matched by the current
        browser search criterion.
        """
        if (tagId, valueId) not in self.tagIds:
            self.tagIds.add((tagId, valueId))
            self._addValue(self.values, value, matching)
            self._addValue(self.sortValues, value, matching)
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
        if not self.matching and other.matching:
            self.matching = True
        
    def __repr__(self):
        return "<ValueNode {} {}>".format(self.values, self.tagIds)
    
    def getKey(self):
        return "tag:"+str(self.tagIds)

    def toolTipText(self):
        return str(self.values) + '\n' + str(self.tagIds)


class VariousNode(CriterionNode):
    """A VariousNode groups elements in a tag-layer which have no tag in any of the tags in the tag-layer's
    tagset."""
    def __init__(self, tagSet):
        """Initialize this VariousNode with the parent-node <parent>, the given model and the tag-layer's
        tagset *tagSet*."""
        super().__init__()
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
    def __init__(self, nodes):
        super().__init__()
        self.setContents(nodes)
        
    def __repr__(self):
        return "<HiddenValues>"
        
    def toolTipText(self):
        return None
               

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
            self._wrappersLoaded = True
        return self._wrappers

    def _loadContents(self, node):
        """Block until all contents have been recursively loaded."""
        if isinstance(node, CriterionNode):
            if not node.hasLoaded():
                node.loadContents(block=True)
                if node.contents is None: # should never be the case
                    raise RuntimeError("Could not load contents of node instantly: {}".format(node))
        else:
            if node.contents is None:
                node.loadContents(recursive=True)
        for n in node.getContents():
            if n.hasContents():
                self._loadContents(n)
        
    def _getElementsInstantly(self, node):
        """If *node* is a CriterionNode return all (toplevel) elements contained in it. If contents have to
        be loaded, block until the search is finished. If *node* is an element return ''[node]''.
        """
        if isinstance(node, Wrapper):
            node.loadContents(recursive=True) 
            return [node]
        elif isinstance(node, (CriterionNode, HiddenValuesNode)):
            try:
                self._loadContents(node)
            except RuntimeError:
                logging.exception(__name__, "Exception when loading elements instantly.")
                return []
            return itertools.chain.from_iterable(self._getElementsInstantly(child)
                                                 for child in node.contents)
        else: return [] # Should be a LoadingNode
