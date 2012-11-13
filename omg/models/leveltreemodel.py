# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from .. import application, config, logging, utils
from ..core import elements, levels, nodes
from ..models import rootedtreemodel

from collections import OrderedDict

logger = logging.getLogger(__name__)


class LevelTreeModel(rootedtreemodel.RootedTreeModel):
    """A tree model for the elements of a level.
    
    The root may contain arbitrary level elements, but those elements are always in correspondence
    to the level: containers contain the same children (in the same order) as in the level, etc.
    """
    
    def __init__(self, level, elements=None):
        """Initializes the model for *level*. A new RootNode will be set as root.
        
        If *elements* is given, these elements will be initially loaded under the root node.
        """
        super().__init__()
        self.level = level
        if elements:
            self._changeContents(QtCore.QModelIndex(), elements)
        level.connect(self._handleLevelChanged)
        
    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def flags(self,index):
        """Overridden method; returns defaultFlags plus ItemIsDropEnabled."""
        defaultFlags = super().flags(index)
        if index.isValid():
            return defaultFlags | Qt.ItemIsDropEnabled | Qt.ItemIsDragEnabled
        else: return defaultFlags | Qt.ItemIsDropEnabled
        
    def dropMimeData(self, mimeData, action, row, column, parentIndex):
        """Drop stuff into a leveltreemodel. Handles OMG mime and text/uri-list.
        
        If URLs are dropped, they are loaded into the level. If there is an album guesser
        specified, it is run on the URLs before they are inserted.
        Elements dropped on the top layer are just inserted under the RootNode. Otherwise, the
        level is modified accordingly.
        """
        if action == Qt.IgnoreAction:
            return True
        parent = self.data(parentIndex, Qt.EditRole)
        # if the drop is on a file, make it a sibling instead of a child of that file
        if parent is not self.root and parent.element.isFile():
            parent = parent.parent
            row = parentIndex.row() + 1
        # drop onto no specific item --> append at the end of the parent
        if row == -1:
            row = parent.getContentsCount()
        if parent is self.root:
            insertPosition = None
        elif row == 0:
            insertPosition = 1
        else:
            insertPosition = parent.contents[row-1].position + 1
        application.stack.beginMacro(self.tr("drop"))
        if mimeData.hasFormat(config.options.gui.mime):
            ids = [ node.element.id for node in mimeData.wrappers() ]
            elements = self.level.collectMany(ids)
            if action == Qt.MoveAction:
                levelRemovals = {}
                modelRemovals = {}
                for node in mimeData.wrappers():
                    if isinstance(node.parent, nodes.Wrapper):
                        elem, pos = node.parent.element, node.position
                        dct = levelRemovals
                    else:
                        elem, pos = node.parent, node.parent.contents.index(node)
                        dct = modelRemovals
                    if elem not in dct:
                        dct[elem] = [pos]
                    else:
                        dct[elem].append(pos)
                for rparent, positions in levelRemovals.items():
                    self.level.removeContentsAuto(rparent, positions=positions)
                    if isinstance(parent, nodes.Wrapper) and rparent is parent.element:
                        #  when elements above insert position are removed, insert row is decreased
                        row -= len([pos for pos in positions if pos < insertPosition])
                for rparent, rows in modelRemovals.items():
                    rparent.model.removeElements(rparent, rows)
        else:  # text/uri-list
            elements = self.prepareURLs(mimeData.urls(), parent)
        ret = len(elements) != 0
        self.insertElements(parent, row, elements)
        application.stack.endMacro()
        return ret   
    
    def removeRows(self, row, count, parent):
        """Qt should not handle removals: DropMimeData does this for us."""
        return True
        
    def insertElements(self, parent, row, elements):
        """Undoably insert *elements* (a list of Elements) under *parent*, which is a wrapper.
        
        This convenience function either pushes a ChangeRootCommand, if *parent* is this model's
        root, or updates the level otherwise.
        """
        if parent is self.root:
            contents = [ node.element for node in self.root.contents ]
            contents[row:row] = elements
            application.stack.push(ChangeRootCommand(self, contents))
        else:
            self.level.insertContentsAuto(parent.element, row, elements)
    
    def removeElements(self, parent, rows):
        """Undoably remove elements in *rows* under *parent* (a wrapper).
        
        This convenience function either alters the RootNode, if parent is self.root, or updates
        the level.
        """
        application.stack.beginMacro(self.tr('remove elements'))
        if parent is self.root:
            newContents = [ self.root.contents[i].element
                            for i in range(len(self.root.contents))
                            if i not in rows ]
            application.stack.push(ChangeRootCommand(self, newContents))
        else:
            self.level.removeContentsAuto(parent.element, indexes=rows)
            
        application.stack.endMacro()
    
    def clear(self):
        """Remove everything below the root node."""
        application.stack.beginMacro(self.tr('clear'))
        self.removeElements(self.root, range(len(self.root.contents)))
        application.stack.endMacro()
        
    def loadFile(self, url):
        """Load a file into this model. The default implementation calls level.collect()."""
        return self.level.collect(url)
    
    def prepareURLs(self, urls, parent):
        """Prepare *urls* to be dropped under *parent*; returns a list of Elements."""
        
        files = utils.collectFiles(sorted(url.path() for url in urls))
        numFiles = sum(len(v) for v in files.values())
        progress = QtGui.QProgressDialog()
        progress.setLabelText(self.tr("Importing {0} files...").format(numFiles))
        progress.setRange(0, numFiles)
        progress.setMinimumDuration(200)
        progress.setWindowModality(Qt.WindowModal)
        filesByFolder = OrderedDict()
        elements = []
        try:
            # load files into editor level
            for folder, filesInOneFolder in files.items():
                filesByFolder[folder] = []
                for file in filesInOneFolder:
                    progress.setValue(progress.value() + 1)
                    element = self.loadFile(file)
                    filesByFolder[folder].append(element)
                    elements.append(element)
            progress.close()
            if not self.guessingEnabled or self.guessProfile is None:
                return elements
            else:
                self.guessProfile.guessAlbums(self.level, filesByFolder)
                return self.guessProfile.albums + self.guessProfile.singles
        except levels.ElementGetError as e:
            print(e)
            return []
        
    def __contains__(self, arg):
        """If *arg* is an id, returns if an element with that id is contained. Else call superclass."""
        if isinstance(arg, int):
            for node in self.root.getAllNodes():
                try:
                    if node.element.id == arg:
                        return True
                except AttributeError:
                    pass  # not an Element
            return False
        return super().__contains__(arg)
    
    def _handleLevelChanged(self, event):
        """Update elements if the state of the level has changed."""
        if isinstance(event, levels.ElementChangedEvent):
            dataIds = event.dataIds
            contentIds = event.contentIds
            for node, contents in self.walk(self.root):
                if isinstance(node, nodes.Wrapper):
                    if node.element.id in dataIds:
                        self.dataChanged.emit(self.getIndex(node), self.getIndex(node))
                    if node.element.id in contentIds:
                        self._changeContents(self.getIndex(node), self.level[node.element.id].contents)
                        contents[:] = [wrapper for wrapper in contents if wrapper in node.contents ]

    def _changeContents(self, index, new):
        """Change contents of a node in the tree.
        
        The node is specified by a QModelIndex *index*, the new contents must be given as a
        list of elements or an elements.ContentList."""
        parent = self.data(index, Qt.EditRole)
        old = [ node.element.id for node in parent.contents ]
        if isinstance(new, elements.ContentList):
            newP = new.positions
            new = new.ids
        else:
            newP = None
            new = [ elem.id for elem in new ]
        i = 0
        while i < len(new):
            id = new[i]
            try:
                existingIndex = old.index(id)
                if existingIndex > 0:
                    self._removeContents(index, i, i + existingIndex - 1)
                del old[:existingIndex+1]
                if newP and newP[i] != parent.contents[i].position:
                    parent.contents[i].position = newP[i]
                    theIndex = self.getIndex(parent.contents[i])
                    self.dataChanged.emit(theIndex, theIndex)
                i += 1
            except ValueError:
                insertStart = i
                insertNum = 1
                i += 1
                while id not in old and i < len(new):
                    id = new[i]
                    insertNum += 1
                    i += 1
                self._insertContents(index, insertStart, new[insertStart:insertStart+insertNum],
                                    newP[insertStart:insertStart+insertNum] if newP else None)
        if len(old) > 0:
            self._removeContents(index, i, i + len(old) - 1)
    
    def _removeContents(self, index, first, last):
        """Remove nodes from the tree without any undo/redo/event handling."""
        self.beginRemoveRows(index, first, last)
        del self.data(index, Qt.EditRole).contents[first:last+1]
        self.endRemoveRows()
        
    def _insertContents(self, index, row, ids, positions=None):
        """Insert wrappers into the tree without any undo/redo/event handling."""
        self.beginInsertRows(index, row, row + len(ids) - 1)
        wrappers = [nodes.Wrapper(self.level[id]) for id in ids]
        if positions:
            for pos, wrap in zip(positions, wrappers):
                wrap.position = pos
        for wrapper in wrappers:
            wrapper.loadContents(recursive = True)
        self.data(index, Qt.EditRole).insertContents(row, wrappers) 
        self.endInsertRows()


class ChangeRootCommand:
    """Command to change the root node's contents in a LevelTreeModel.
    """
    
    def __init__(self, model, newContents, text="change root"):
        self.text = text
        self.model = model
        self.old = [ wrapper.element for wrapper in model.root.contents ]
        self.new = newContents
    
    def redo(self):
        self.model._changeContents(QtCore.QModelIndex(), self.new )
        
    def undo(self):
        self.model._changeContents(QtCore.QModelIndex(), self.old )
