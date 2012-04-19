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
from ..models import rootedtreemodel, RootNode, Wrapper, albumguesser, levels
from ..utils import collectFiles

logger = logging.getLogger(__name__)
                    
class EditorModel(rootedtreemodel.RootedTreeModel):
    """Model class for the editors where users can edit elements before they are commited into
    the database."""
    
    def __init__(self):
        """Initializes the model. A new RootNode will be set as root."""
        super().__init__(RootNode(self), levels.editor)
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

        modify.stack.beginMacro(self.tr("drop into editor"))
        if mimeData.hasFormat("text/uri-list"):
            # files and/or folders are dropped from outside or from a filesystembrowser.
            ids = self.prepareURLs(mimeData.urls(), parent)
            
        elif mimeData.hasFormat(config.options.gui.mime):
            ids = [ node.element.id for node in mimeData.getNodes() if isinstance(node, Wrapper) ]
            # first case: OMG mime data -> wrappers from an editor, browser etc.
        else:
            raise RuntimeError('HÄÄÄÄÄ???')
        
        if len(ids) == 0:
            ret = False
        if parent is self.root:
            oldContentIDs = [ node.element.id for node in self.root.contents ]
            newContentIDs = oldContentIDs[:row] + ids + oldContentIDs[row:]
            modify.stack.push(rootedtreemodel.ChangeRootCommand(self, oldContentIDs, newContentIDs))
            ret = True
        else:
            ret = False
        modify.stack.endMacro()
        return ret   
        
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
        
