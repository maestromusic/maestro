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

from .. import logging, modify, tags, realfiles, config
from ..models import rootedtreemodel, RootNode, Wrapper, albumguesser, levels
from ..modify import events, commands
from ..utils import collectFiles, relPath
from collections import OrderedDict
import itertools

logger = logging.getLogger(__name__)
                    
class EditorModel(rootedtreemodel.RootedTreeModel):
    """Model class for the editors where users can edit elements before they are commited into
    the database."""
    
    def __init__(self):
        """Initializes the model. A new RootNode will be set as root."""
        super().__init__(RootNode(), levels.editor)
        self.albumGroupers = []
        self.metacontainer_regex=r" ?[([]?(?:cd|disc|part|teil|disk|vol)\.? ?([iI0-9]+)[)\]]?"
        
    def flags(self,index):
        defaultFlags = super().flags(index)
        if index.isValid():
            return defaultFlags | Qt.ItemIsDropEnabled | Qt.ItemIsDragEnabled
        else: return defaultFlags | Qt.ItemIsDropEnabled

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

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

        if mimeData.hasFormat(config.options.gui.mime):
            # first case: OMG mime data -> wrappers from an editor, browser etc.
            return self._dropOMGMime(mimeData, action, parent, row)
        elif mimeData.hasFormat("text/uri-list"):
            # files and/or folders are dropped from outside or from a filesystembrowser.
            return self._dropURLMime(mimeData.urls(), action, row, parent)
        else:
            raise RuntimeError('HÄÄÄÄÄ???')
     
    def _dropOMGMime(self, mimeData, action, parent, row):
        """handles drop of OMG mime data into the editor.
        
        Various cases (and combinations thereof)must be handled: Nodes might be copied or moved
        within the same parent, or moved / copied from the "outside"."""
        return False
        
    def _dropURLMime(self, urls, action, row, parent):
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
            for folder, filesInOneFolder in files.items():
                filesByFolder[folder] = []
                for file in filesInOneFolder:
                    progress.setValue(progress.value() + 1)
                    filesByFolder[folder].append(self.level.get(file))
            modify.beginMacro("drop {} files".format(numFiles))
            topIDs = albumguesser.guessAlbums(filesByFolder, self.albumGroupers, self.metacontainer_regex)
            if parent is not self.root:
                raise NotImplementedError()
            wrappers = []
            
            oldContentIDs = [ node.element.id for node in self.root.contents ]
            newContentIDs = oldContentIDs[:]
            newContentIDs[row:row] = topIDs
            command = rootedtreemodel.ChangeRootCommand(self, oldContentIDs, newContentIDs)
            modify.push(command)
            modify.endMacro()
            return True
        
        except levels.ElementGetError as e:
            print(e)
            return False
