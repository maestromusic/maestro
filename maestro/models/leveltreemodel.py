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

import collections

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from .. import config, logging, utils, stack
from ..core import elements, levels, nodes
from ..models import rootedtreemodel


class LevelTreeModel(rootedtreemodel.RootedTreeModel):
    """A tree model for the elements of a level.
    
    The root may contain arbitrary level elements, but those elements are always in correspondence
    to the level: containers contain the same children (in the same order) as in the level, etc.
    """
    rowsDropped = QtCore.pyqtSignal(QtCore.QModelIndex, int, int)
    
    def __init__(self, level, elements=None):
        """Initializes the model for *level*. A new RootNode will be set as root.
        
        If *elements* is given, these elements will be initially loaded under the root node.
        """
        super().__init__()
        self._dnd_active = False
        self.level = level
        if elements:
            self._insertContents(QtCore.QModelIndex(), 0, [element.id for element in elements])
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
        """Drop stuff into a leveltreemodel. Handles Maestro mime and text/uri-list.
        
        If URLs are dropped, they are loaded into the level. If there is an album guesser
        specified, it is run on the URLs before they are inserted.
        Elements dropped on the top layer are just inserted under the RootNode. Otherwise, the
        level is modified accordingly.
        """
        if action == Qt.IgnoreAction:
            return True
        
        # Compute drop position
        parent = self.data(parentIndex, Qt.EditRole)
        if parent.isFile(): # Drop onto a file => drop behind it
            row = parent.parent.index(parent) + 1
            parent = parent.parent
        elif row == -1:
            # no specific position: insert at the beginning or end
            if self.dndTarget is not None and self.dndTarget.isExpanded(parentIndex):
                row = 0
            else: row = parent.getContentsCount()

        stack.beginMacro(self.tr("drop"))
        
        # Get elements to insert
        if mimeData.hasFormat(config.options.gui.mime):
            ids = [ node.element.id for node in mimeData.wrappers() ]
            elements = self.level.collectMany(ids)
        else:  # text/uri-list
            elements = self.prepareURLs(mimeData.urls(), parent)

        if len(elements) > 0:
            self.insertElements(parent, row, elements)
            self.rowsDropped.emit(self.getIndex(parent), row, row+len(elements)-1)
            
        stack.endMacro()
        return len(elements) != 0
    
    def startDrag(self):
        """Called by the view, when a drag starts."""
        self._dnd_active = True
        self._dnd_removeTuples = []
    
    def endDrag(self):
        """Called by the view, when a drag ends."""
        self._dnd_active = False
        if len(self._dnd_removeTuples) > 0:
            removeData = collections.defaultdict(set)
            for element, rows in self._dnd_removeTuples:
                removeData[element].update(rows)
            for element, rows in removeData.items():
                self.removeElements(element, rows)
            self._dnd_removeTuples = []
    
    def removeRows(self, row, count, parentIndex):
        parent = self.data(parentIndex)
        if not self._dnd_active or parent is self.root:
            self.removeElements(parent, list(range(row, row+count)))
            return True
        else:
            # After DnD move operations Qt calls removeRows to remove content from the source model.
            # Depending on the selection, several calls to removeRows might be necessary. In models where a
            # remove operation can trigger changes at other places in the model, this can cause problems.
            # Thus, during a drag we collect all such calls and remove their contents only in endDrag.   
            # See ticket #129.
            rows = range(row, row+count)
            if [wrapper.element.id for wrapper in parent.contents] != parent.element.contents.ids:
                # If this is exactly the node in which nodes have been dropped we might have to update rows.
                # See ticket #138.
                assert parent.element.id == self.level.lastInsertId
                insertedRows = set(i for i,pos in enumerate(parent.element.contents.positions)
                                   if pos in self.level.lastInsertPositions)
                rows = _mapOldRowsToNew(rows, len(parent.element.contents), insertedRows)
            self._dnd_removeTuples.append((parent.element, rows))
            return False
        
    def insertElements(self, parent, row, elements):
        """Undoably insert *elements* (a list) under *parent*, which is a wrapper.
        
        This convenience function either pushes an InsertIntoRootCommand, if *parent* is this model's
        root, or updates the level otherwise.
        """
        if parent is self.root:
            stack.push(InsertIntoRootCommand(self, row, [element.id for element in elements]))
        else: self.level.insertContentsAuto(parent.element, row, elements)
    
    def removeElements(self, parent, rows):
        """Undoably remove elements in *rows* under *parent* (a wrapper, an element or the root node).
        
        This convenience function either alters the RootNode, if parent is self.root, or updates
        the level.
        """
        stack.beginMacro(self.tr('remove elements'))
        if parent is self.root:
            stack.push(RemoveFromRootCommand(self, rows))
        else:
            element = parent if isinstance(parent, elements.Element) else parent.element
            self.level.removeContentsAuto(element, indexes=rows)
        stack.endMacro()

    def clear(self):
        """Remove everything below the root node."""
        stack.beginMacro(self.tr('clear'))
        self.removeElements(self.root, range(len(self.root.contents)))
        stack.endMacro()
        
    def loadFile(self, url):
        """Load a file into this model. The default implementation calls level.collect()."""
        return self.level.collect(url)
    
    def prepareURLs(self, urls, parent):
        """Prepare *urls* to be dropped under *parent*; returns a list of Elements."""
        files = utils.files.collect(urls)
        numFiles = sum(len(v) for v in files.values())
        progress = QtGui.QProgressDialog(self.tr("Importing {0} files...").format(numFiles),
                                         self.tr("Cancel"), 0, numFiles)
        progress.setMinimumDuration(1000)
        progress.setWindowModality(Qt.WindowModal)
        filesByFolder = collections.OrderedDict()
        elements = []
        macro = self.level.stack.beginMacro(self.tr("import URLs"))
        try:
            # load files into editor level
            for folder, filesInOneFolder in files.items():
                filesByFolder[folder] = []
                for file in filesInOneFolder:
                    if progress.wasCanceled():
                        self.level.stack.abortMacro()
                        return []
                    progress.setValue(progress.value() + 1)
                    element = self.loadFile(file)
                    filesByFolder[folder].append(element)
                    elements.append(element)
            progress.close()
            if not self.guessingEnabled or self.guessProfile is None:
                self.level.stack.endMacro()
                return elements
            else:
                self.guessProfile.guessAlbums(self.level, filesByFolder)
                self.level.stack.endMacro()
                return self.guessProfile.toplevels
        except levels.ElementGetError:
            logging.exception(__name__, "Error while loading elements.")
            macro.abort()
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
        if not isinstance(event, levels.LevelChangeEvent):
            return
        dataIds = event.dataIds.union(event.dbAddedIds, event.dbRemovedIds)
        for node, contents in self.walk(self.root):
            if isinstance(node, nodes.Wrapper):
                if node.element.id in dataIds:
                    self.dataChanged.emit(self.getIndex(node), self.getIndex(node))
                if node.element.id in event.contentIds:
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
            wrapper.loadContents(recursive=True)
        self.data(index, Qt.EditRole).insertContents(row, wrappers) 
        self.endInsertRows()

    
def _mapOldRowsToNew(rows, newRowCount, insertedRows):
    """Map from old row indexes to new ones after some rows have been inserted: This method assumes that
    in a list of *newRowCount* rows the rows given by *insertedRows* have been inserted. *rows* is a list
    of row indexes before the insertion that should be mapped to indexes after insertion. The method returns
    the list of new row indexes.
    """ 
    if len(rows) == 0:
        return
    nextRowIndex = 0
    newRows = []
    oldRow = -1
    for newRow in range(newRowCount):
        if newRow not in insertedRows:
            oldRow += 1
        if oldRow == rows[nextRowIndex]:
            newRows.append(newRow)
            nextRowIndex += 1
            if nextRowIndex == len(rows):
                break
    return newRows


class InsertIntoRootCommand:
    """Command to insert elements with the given ids into the root node of *model* at *row*."""
    def __init__(self, model, row, ids):
        self.text = translate("LevelTreeModel", "insert root nodes")
        self.model = model
        self.row = row
        self.ids = ids
        
    def redo(self):
        self.model._insertContents(QtCore.QModelIndex(), self.row, self.ids)
        
    def undo(self):
        self.model._removeContents(QtCore.QModelIndex(), self.row, self.row+len(self.ids)-1)
        
        
class RemoveFromRootCommand:
    """Command to remove the elements in the given *rows* from the root node of *model*."""
    def __init__(self, model, rows):
        self.text = translate("LevelTreeModel", "remove root nodes")
        self.model = model
        self.rows = rows
        self.ids = [(row,self.model.root.contents[row].element.id) for row in rows]
        self.ids.sort()
        
    def redo(self):
        startRow = None
        for i,row in enumerate(self.rows):
            if startRow is None:
                startRow = row
            if i+1 < len(self.rows) and self.rows[i+1] == row + 1:
                continue
            self.model._removeContents(QtCore.QModelIndex(), startRow, row)
            startRow = None
            
    def undo(self):
        insertRow = None
        insertIds = []
        shift = 0
        for i, (row, id) in enumerate(self.ids):
            if insertRow is None:
                insertRow = row
            insertIds.append(id)
            if i+1 < len(self.ids) and self.ids[i+1][0] == row + 1:
                continue
            self.model._insertContents(QtCore.QModelIndex(), insertRow+shift, insertIds)
            shift += len(insertIds)
            insertIds = []
            insertRow = None
