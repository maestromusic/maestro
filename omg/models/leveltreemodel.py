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

from .. import application, config, database as db, logging, utils
from ..core import commands, levels, tags
from ..core.nodes import RootNode, Wrapper
from ..core.elements import ContentList, Container
from ..models import rootedtreemodel, albumguesser
from .. import modify
from ..modify import real

logger = logging.getLogger(__name__)
        
class LevelTreeModel(rootedtreemodel.RootedTreeModel):
    """Model class for the editors where users can edit elements before they are commited into
    the database."""
    
    def __init__(self, level, ids = None):
        """Initializes the model. A new RootNode will be set as root.
        
        If *ids* is given, these elements will be initially loaded under the root node"""
        super().__init__()
        self.level = level
        if ids:
            self._changeContents(QtCore.QModelIndex(), ids)
        level.changed.connect(self._handleLevelChanged)

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def flags(self,index):
        defaultFlags = super().flags(index)
        if index.isValid():
            return defaultFlags | Qt.ItemIsDropEnabled | Qt.ItemIsDragEnabled
        else: return defaultFlags | Qt.ItemIsDropEnabled
        
    def dropMimeData(self,mimeData,action,row,column,parentIndex):
        """Drop stuff into a leveltreemodel. Handles OMG mime and text/uri-list.
        
        If URLs are dropped, they are loaded into the level. If there is an album
        guesser specified, it is run on the URLs before they are inserted.
        
        Elements dropped on the top layer are just inserted under the RootNode. Otherwise,
        the level is modified accordingly."""
        
        if action == Qt.IgnoreAction:
            return True
        if action == Qt.TargetMoveAction:
            raise ValueError()
        parent = self.data(parentIndex, Qt.EditRole)
        # if something is dropped on a file, make it a sibling instead of a child of that file
        if parent is not self.root and parent.element.isFile():
            parent = parent.parent
            row = parentIndex.row() + 1
        # if something is dropped on no item, append it to the end of the parent
        if row == -1:
            row = parent.getContentsCount()
        if parent is not self.root:
            if row == 0:
                insertPosition = 1
            else:
                insertPosition = parent.contents[row-1].position + 1
        else:
            insertPosition = None
        application.stack.beginMacro(self.tr("drop"))
        if mimeData.hasFormat(config.options.gui.mime):
            ids = [ node.element.id for node in mimeData.getNodes() if isinstance(node, Wrapper) ]
            if action == Qt.MoveAction:
                removals = utils.listDict(( (node.parent, node.parent.contents.index(node))
                                                if isinstance(node.parent, RootNode)
                                                else (node.parent.element.id,node.position) )
                                            for node in mimeData.getNodes() if isinstance(node, Wrapper))
                for rparent, positions in removals.items():
                    if isinstance(rparent, int):
                        commands.removeElements(self.level, rparent, positions, self.tr("remove elements"))
                        if parent is not self.root and parent.element.id == rparent:
                            row -= len([pos for pos in positions if pos < insertPosition])
                for rparent, rows in removals.items():
                    if not isinstance(rparent, int):
                        rparent.model.removeElements(rparent, rows)
                
        else: # text/uri-list
            ids = self.prepareURLs(mimeData.urls(), parent)
        
        ret = len(ids) != 0        
        self.insertElements(parent, row, ids)
        application.stack.endMacro()
        return ret   
    
    def removeRows(self, row, count, parent):
        """Qt should not handle removals."""
        return True
        
    def insertElements(self, parent, row, ids):
        """Undoably insert elements with *ids* (a list) under *parent*, which
        is a wrapper. This convenience function either fires a ChangeRootCommand, if the parent
        is the RootNode, or updates the level, if it's an element. In the latter case, a list
        of positions for the new elements may be given; if not, it is automatically inferred."""
        if parent is self.root:
            oldContentIDs = [node.element.id for node in self.root.contents ]
            newContentIDs = oldContentIDs[:row] + ids + oldContentIDs[row:]
            application.stack.push(ChangeRootCommand(self, oldContentIDs, newContentIDs))
        else:
            commands.insertElements(self.level, parent.element.id, row, ids)
    
    def removeElements(self, parent, rows):
        """Undoably remove elements in *rows* under *parent* (a wrapper)."""
        if parent is self.root:
            oldContentIDs = [node.element.id for node in self.root.contents ]
            newContentIDs = [oldContentIDs[i] for i in range(len(oldContentIDs)) if i not in rows]
            application.stack.push(ChangeRootCommand(self, oldContentIDs, newContentIDs))
        else:
            commands.removeElements(self.level, parent.element.id,
                                    [parent.contents[i].position for i in rows],
                                    self.tr("Remove elements"))
        
    def prepareURLs(self, urls, parent):
        '''This method is called if url MIME data is dropped onto this model, from an external file manager
        or a filesystembrowser widget.'''
        files = utils.collectFiles(sorted(url.path() for url in urls))
        numFiles = sum(len(v) for v in files.values())
        progress = QtGui.QProgressDialog()
        progress.setLabelText(self.tr("Importing {0} files...").format(numFiles))
        progress.setRange(0, numFiles)
        progress.setMinimumDuration(200)
        progress.setWindowModality(Qt.WindowModal)
        filesByFolder = {}
        ids = []
        try:
            # load files into editor level
            for folder, filesInOneFolder in files.items():
                filesByFolder[folder] = []
                for file in filesInOneFolder:
                    progress.setValue(progress.value() + 1)
                    element = self.level.get(file)
                    filesByFolder[folder].append(element)
                    ids.append(element.id)
                    
            progress.close()
            # call album guesser
            if self.guessProfile is None:
                return ids
            else:
                profile = albumguesser.profileConfig[self.guessProfile]
                profile.guessAlbums(self.level, filesByFolder)
                return profile.albums + profile.singles

        except levels.ElementGetError as e:
            print(e)
            return []
        
            
    def _handleLevelChanged(self, event):
        dataIds = event.dataIds
        contentIds = event.contentIds
        for node, contents in utils.walk(self.root):
            if isinstance(node, Wrapper):
                if node.element.id in dataIds:
                    self.dataChanged.emit(self.getIndex(node), self.getIndex(node))
                if node.element.id in contentIds:
                    self._changeContents(self.getIndex(node), self.level.get(node.element.id).contents)
                    contents[:] = [wrapper for wrapper in contents if wrapper in node.contents ]

    def _changeContents(self, index, new):
        parent = self.data(index, Qt.EditRole)
        old = [ node.element.id for node in parent.contents ]
        if isinstance(new, ContentList):
            newP = new.positions
            new = new.ids
        else:
            newP = None
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
                    index = self.getIndex(parent.contents[i])
                    self.dataChanged.emit(index, index)
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
        self.beginRemoveRows(index, first, last)
        del self.data(index, Qt.EditRole).contents[first:last+1]
        self.endRemoveRows()
        
    def _insertContents(self, index, row, ids, positions = None):
        self.beginInsertRows(index, row, row + len(ids) - 1)
        wrappers = [Wrapper(self.level.get(id)) for id in ids]
        if positions:
            for pos, wrap in zip(positions, wrappers):
                wrap.position = pos
        for wrapper in wrappers:
            wrapper.loadContents(recursive = True)
        self.data(index, Qt.EditRole).insertContents(row, wrappers) 
        self.endInsertRows()            


class MergeCommand(QtGui.QUndoCommand):
    """Merge creates a new container between *parent* and the children at the given *indices*.
    Those child elements will be removed from *parent* and instead inserted as children of
    the new container at indices[0]. The new container will contain all tags that are equal in
    all of its new children; its TITLE tag will be set to *newTitle*.
    
    removeString defines what to remove from the titles of the elements that are moved below the
    new container; this will usually be similar to *newTitle* plus possibly some punctutaion.
    If *adjustPositions* is True, the positions of items that are *not* removed are decreased
    to fill the gaps arising from moved elements.
    Example: Consider the following setting of an album containing a Sonata: 
    
    * parent
    |- pos1: child0 (title = Sonata Nr. 5: Allegro)
    |- pos2: child1 (tilte = Sonata Nr. 5: Adagio)
    |- pos3: child2 (title = Sonata Nr. 5: Finale. Presto)
    |- pos4: child3 (title = Nocturne Op. 13/37)
    |- pos5: child4 (title = Prelude BWV 42)
    
    After a call to merge with *indices=(0,1,2)*, *newTitle='Sonata Nr. 5'*, *removeString='Sonata Nr. 5: '*,
    *adjustPositions = True* the layout would be:
    
    * parent
    |- * pos1: new container (title = Sonata Nr. 5)
       |- pos1: child0 (title = Allegro)
       |- pos2: child1 (title = Adagio)
       |- pos3: child2 (title = Finale. Presto)
    |- pos2: child3 (title = Nocturne Op. 13/37)
    |- pos3: child4 (title = Prelude BWV 42)
    """ 
    def __init__(self, level, parent, indices, newTitle, removeString, adjustPositions):
        
        super().__init__()
        self.insertIndex = indices[0] # where the new container will live
        self.level = level
        self.newTitle = newTitle
        self.tagChanges = {}
        self.parentChanges = {} # maps child id to (position under old parent, position under new container) tuples
        self.positionChanges = {}
        def recordTagChanges(element):
            if tags.TITLE in element.tags:
                tagCopy = element.tags.copy()
                tagCopy[tags.TITLE] = [ t.replace(removeString, '') for t in tagCopy[tags.TITLE]]
                self.tagChanges[id] = tags.TagDifference(element.tags, tagCopy)
        if isinstance(parent, Wrapper):
            self.elementParent = True
            self.insertPosition = parent.element.contents.positions[self.insertIndex]
            self.parentID = parent.element.id
            for index, (position, id) in enumerate(parent.element.contents.items()):
                element = level.get(id)
                if index in indices:
                    self.parentChanges[id] = (position, len(self.parentChanges) + 1)
                    recordTagChanges(element)
                elif adjustPositions and len(self.parentChanges) > 1:
                    self.positionChanges[id] = (position, position - len(self.parentChanges) + 1)
                    
        else:
            self.elementParent = False
            for index, wrapper in enumerate(parent.contents):
                id = wrapper.element.id
                element = level.get(id)
                if index in indices:
                    self.parentChanges[id] = (index, len(self.parentChanges) + 1)
                    recordTagChanges(element)
            
    def redo(self):
        if not hasattr(self, "containerID"):
            if self.level is levels.real:
                self.containerID = db.write.createElements([(False, not self.elementParent, len(self.parentChanges), False)])[0]
            else:
                self.containerID = levels.createTId()
        elif self.level is levels.real:
            db.write.createElementsWithIds([(self.containerID, False, not self.elementParent, len(self.parentChanges), False)])
        container = Container(self.level, self.containerID, major = False)
        elements = []
        self.level.elements[self.containerID] = container
        logger.debug("merge: inserted new container with ID {} into level {}".format(self.containerID, self.level))
        if self.elementParent:
            parent = self.level.get(self.parentID)
            container.parents = [parent.id]
            
        for id, (oldPos, newPos) in self.parentChanges.items():
            element = self.level.get(id)
            if self.elementParent:
                parent.contents.remove(pos = oldPos)
                element.parents.remove(self.parentID)
            element.parents.append(self.containerID)
            container.contents.insert(newPos, id)
            elements.append(element)
            if id in self.tagChanges:
                self.tagChanges[id].apply(element.tags)
        container.tags = tags.findCommonTags(elements)
        container.tags[tags.TITLE] = [self.newTitle]
        if self.elementParent:
            parent.contents.insert(self.insertPosition, self.containerID)
        for id, (oldPos, newPos) in sorted(self.positionChanges.items()):
            element = self.level.get(id)
            parent.contents.positions[parent.contents.positions.index(oldPos)] = newPos
        if self.level is levels.real:
            db.transaction()
            modify.real.changeTags(self.tagChanges)
            modify.real.changeTags({self.containerID: tags.TagDifference(None, container.tags)})
            db.write.addContents([(self.containerID, newPos, id) for (id, (oldPos,newPos)) in self.parentChanges.items()])
            if self.elementParent:
                db.write.removeAllContents([self.parentID])
                db.write.addContents([(self.parentID, pos, childID) for pos,childID in parent.contents.items()])
            db.commit()
            for id, diff in self.tagChanges.items():
                elem = self.level.get(id)
                if elem.isFile() and not diff.onlyPrivateChanges():
                    modify.real.changeFileTags(elem.path, diff)
        
        self.level.emitEvent(dataIds = list(self.positionChanges.keys()),
                             contentIds = [self.containerID, self.parentID] if self.elementParent else [self.containerID])
                  
    def undo(self):
        if self.elementParent:
            parent = self.level.get(self.parentID)
            del parent.contents[self.insertIndex]
            for id, (oldPos, newPos) in self.positionChanges.items():
                element = self.level.get(id)
                parent.contents.positions[parent.contents.positions.index(newPos)] = oldPos
        for id, (oldPos, newPos) in self.parentChanges.items():
            element = self.level.get(id)
            if self.elementParent:
                parent.contents.insert(oldPos, id)
                element.parents.append(self.parentID)
            element.parents.remove(self.containerID)
            if id in self.tagChanges:
                self.tagChanges[id].revert(element.tags)
        if self.level is levels.real:
            db.transaction()
            modify.real.changeTags(self.tagChanges, reverse = True)
            db.write.deleteElements([self.containerID])
            if self.elementParent:
                db.write.removeAllContents([self.parentID])
                db.write.addContents([(self.parentID, pos, childID) for pos,childID in parent.contents.items()])
            db.commit()
            for id, diff in self.tagChanges.items():
                elem = self.level.get(id)
                if elem.isFile() and not diff.onlyPrivateChanges():
                    modify.real.changeFileTags(elem.path, diff)
        del self.level.elements[self.containerID]
        self.level.emitEvent(dataIds = list(self.positionChanges.keys()),
                             contentIds = [self.parentID] if self.elementParent else [])            

class ChangeRootCommand(QtGui.QUndoCommand):
    def __init__(self, model, old, new, text = "<change root>"):
        super().__init__()
        self.model = model
        self.old = old
        self.new = new
        self.setText(text)
        
    def redo(self):
        logger.debug("change root: {} --> {}".format(self.old, self.new))
        self.model._changeContents(QtCore.QModelIndex(), self.new )
        
    def undo(self):
        logger.debug("change root: {} --> {}".format(self.new, self.old))
        self.model._changeContents(QtCore.QModelIndex(), self.old )