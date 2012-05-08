# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from .. import logging, modify, config
from ..models import rootedtreemodel, wrappertreemodel, RootNode, Wrapper, albumguesser, levels
from ..utils import collectFiles

logger = logging.getLogger(__name__)
        
class EditorModel(wrappertreemodel.WrapperTreeModel):
    """Model class for the editors where users can edit elements before they are commited into
    the database."""
    
    def __init__(self):
        """Initializes the model. A new RootNode will be set as root."""
        super().__init__(levels.editor)
        self.albumGroupers = []
        self.metacontainer_regex=r" ?[([]?(?:cd|disc|part|teil|disk|vol)\.? ?([iI0-9]+)[)\]]?"

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def flags(self,index):
        defaultFlags = super().flags(index)
        if index.isValid():
            return defaultFlags | Qt.ItemIsDropEnabled | Qt.ItemIsDragEnabled
        else: return defaultFlags | Qt.ItemIsDropEnabled
        
    def dropMimeData(self,mimeData,action,row,column,parentIndex):
        """This function does all the magic that happens if elements are dropped onto this editor."""
        
        if action == Qt.IgnoreAction:
            return True

        if action == Qt.TargetMoveAction:
            print('wtf target')
            raise ValueError()
        
        parent = self.data(parentIndex, Qt.EditRole)
        # if something is dropped on a file, make it a sibling instead of a child of that file
        if parent is not self.root and parent.element.isFile():
            parent = parent.parent
            row = parentIndex.row() + 1
        # if something is dropped on no item, append it to the end of the parent
        if row == -1:
            row = parent.getContentsCount()

        modify.stack.beginMacro(self.tr("drop into editor"))
        if mimeData.hasFormat(config.options.gui.mime):
            ids = [ node.element.id for node in mimeData.getNodes() if isinstance(node, Wrapper) ]
            
        else: #mimeData.hasFormat(config.options.gui.mime)
            ids = self.prepareURLs(mimeData.urls(), parent)
        
        ret = len(ids) != 0        
        self.insertElements(parent, row, ids)
        modify.stack.endMacro()
        return ret   
    
    def insertElements(self, parent, index, ids, positions = None):
        """Undoably insert elements with *ids* (a list) at index "index" under *parent*, which
        is a wrapper. This convenience function either fires a ChangeRootCommand, if the parent
        is the RootNode, or updates the level, if it's an element. In the latter case, a list
        of positions for the new elements may be given; if not, it is automatically inferred."""
        if parent is self.root:
            oldContentIDs = [node.element.id for node in self.root.contents ]
            newContentIDs = oldContentIDs[:index] + ids + oldContentIDs[index:]
            modify.stack.push(rootedtreemodel.ChangeRootCommand(self, oldContentIDs, newContentIDs))
        else:
            modify.stack.push(InsertCommand(self.level, parent.element.id, index, ids, positions))
            
           
    def prepareURLs(self, urls, parent):
        '''This method is called if url MIME data is dropped onto this model, from an external file manager
        or a filesystembrowser widget.'''
        files = collectFiles(sorted(url.path() for url in urls))
        numFiles = sum(len(v) for v in files.values())
        progress = QtGui.QProgressDialog()
        progress.setLabelText(self.tr("Importing {0} files...").format(numFiles))
        progress.setRange(0, numFiles)
        progress.setMinimumDuration(200)
        progress.setWindowModality(Qt.WindowModal)
        filesByFolder = {}
        
        try:
            # load files into editor level
            for folder, filesInOneFolder in files.items():
                filesByFolder[folder] = []
                for file in filesInOneFolder:
                    progress.setValue(progress.value() + 1)
                    filesByFolder[folder].append(self.level.get(file))
            progress.close()
            # call album guesser
            return albumguesser.guessAlbums(self.level, filesByFolder, parent, self.albumGroupers, self.metacontainer_regex)

        except levels.ElementGetError as e:
            print(e)
            return []
        except albumguesser.GuessError as e:
            print(e)
            return []

class InsertCommand(QtGui.QUndoCommand):
    """A command to insert elements into a container in a level."""
    def __init__(self, level, parentId, index, ids, positions = None):
        super().__init__()
        self.level = level
        self.parentId = parentId
        self.index = index
        self.ids = ids
        if positions is None:
            if index == 0:
                firstPosition = 1
            else:
                parent = self.level.get(parentId)
                firstPosition = parent.contents.positions[index-1] + 1
            positions = list(range(firstPosition, firstPosition + len(ids)))
        self.positions = positions
        
    def redo(self):
        parent = self.level.get(self.parentId)
        parent.contents.ids[self.index:self.index] = self.ids
        parent.contents.positions[self.index:self.index] = self.positions
        for childId in self.ids:
            child = self.level.get(childId)
            if self.parentId not in child.parents:
                child.parents.append(self.parentId)
        self.level.emitEvent(contentIds = [self.parentId])
    
    def undo(self):
        parent = self.level.get(self.parentId)
        del parent.contents.ids[self.index:self.index+len(self.ids)]
        del parent.contents.positions[self.index:self.index+len(self.ids)]
        for childId in self.ids:
            if childId not in parent.contents.ids:
                self.level.get(childId).parents.remove(self.parentId)
        self.level.emitEvent(contentIds = [self.parentId])