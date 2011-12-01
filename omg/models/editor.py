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
from ..models import rootedtreemodel, RootNode, File, albumguesser
from ..modify import events, commands
from ..utils import collectFiles, relPath
from ..constants import EDITOR, CONTENTS
from collections import OrderedDict
import itertools

logger = logging.getLogger(__name__)
                    
class EditorModel(rootedtreemodel.RootedTreeModel):
    """Model class for the editors where users can edit elements before they are commited into
    the database."""
    
    def __init__(self):
        """Initializes the model. A new RootNode will be set as root."""
        super().__init__(RootNode())
        modify.dispatcher.changes.connect(self.handleChangeEvent)
        self.albumGroupers = []
        self.metacontainer_regex=r" ?[([]?(?:cd|disc|part|teil|disk|vol)\.? ?([iI0-9]+)[)\]]?"

    
    def handleChangeEvent(self, event):
        """React on an incoming ChangeEvent by applying all changes that affect the
        current model."""
        if isinstance(event, events.ElementChangeEvent):
            if event.level == EDITOR:
                self.handleElementChangeEvent(event)
        elif isinstance(event, events.ElementsDeletedEvent):
            pass
        elif isinstance(event, events.TagTypeChangedEvent):
            pass #TODO: was macht man da??
        elif isinstance(event, events.FlagTypeChangedEvent):
            pass
        elif isinstance(event, events.SortValueChangedEvent):
            pass # editor contents are only sorted by hand
        elif isinstance(event, events.HiddenAttributeChangedEvent):
            pass # editor does not use this
        else:
            logger.warning('WARNING UNKNOWN EVENT {}, RESETTING EDITOR'.format(event))
            self.clear()

    
    def applyChangesToNode(self, node, event):
        """Helper function for the handling of ElementChangeEvents. Ensures proper application
        to a single node."""
        modelIndex = self.getIndex(node)
        if not event.contentsChanged:
            # this handles SingleElementChangeEvent, all TagChangeEvents, FlagChangeEvents, ...
            event.applyTo(node)
            ret = isinstance(event, events.SingleElementChangeEvent)
        elif isinstance(event, events.PositionChangeEvent):
            self.changePositions(node, event.positionMap)
            ret = True #PositionChangeEvent handles only _one_ parent -> no children can be affected
        elif isinstance(event, events.InsertContentsEvent):
            self.insert(node, event.insertions[node.id])
            ret = False   
        elif isinstance(event, events.RemoveContentsEvent):
            self.remove(node, event.removals[node.id])
            ret = False
        elif event.__class__ == events.ElementChangeEvent:
            if node.isFile():
                event.applyTo(node)
            else:
                self.beginRemoveRows(modelIndex, 0, node.getContentsCount())
                temp = node.contents
                node.contents = []
                self.endRemoveRows()
                node.contents = temp
                self.beginInsertRows(modelIndex, 0, event.getNewContentsCount(node))
                event.applyTo(node)
                self.endInsertRows()
            ret = True
        else:
            logger.warning('unknown element change event: {}'.format(event))
        self.dataChanged.emit(modelIndex, modelIndex)
        return ret
        
    def flags(self,index):
        defaultFlags = super().flags(index)
        if index.isValid():
            return defaultFlags | Qt.ItemIsDropEnabled | Qt.ItemIsDragEnabled
        else: return defaultFlags | Qt.ItemIsDropEnabled

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def dropMimeData(self,mimeData,action,row,column,parentIndex):
        """This function does all the magic that happens if elements are dropped onto this editor."""
        QtGui.QApplication.changeOverrideCursor(Qt.ArrowCursor) # dont display the DnD cursor during the warning
        if action == Qt.IgnoreAction:
            return True
        parent = self.data(parentIndex, Qt.EditRole)
        # if something is dropped on a file, make it a sibling instead of a child of that file
        if parent is not self.root and parent.isFile():
            parent = parent.parent
            row = parentIndex.row() + 1
        # if something is dropped on no item, append it to the end of the parent
        if row == -1:
            row = parent.getContentsCount()
        #parent = parent.copy()
        if mimeData.hasFormat(config.options.gui.mime):
            # first case: OMG mime data -> nodes from an editor, browser etc.
            return self._dropOMGMime(mimeData, action, parent, row)
        elif mimeData.hasFormat("text/uri-list"):
            # files and/or folders are dropped from outside or from a filesystembrowser.
            nodes = self._dropURLMime(mimeData.urls())
            if not nodes:
                return False
            if parent.id == self.root.id:
                insertPosition = row
            else:
                insertPosition = 1 if row == 0 else parent.contents[row-1].position+1
            ins = []
            for node in nodes:
                ins.append( (insertPosition, node) )
                if parent.id != self.root.id:
                    node.position = insertPosition
                else:
                    node.position = None
                insertPosition += 1
            modify.beginMacro(EDITOR, self.tr("drop URIs"))
            # now check if the positions of the subsequent nodes have to be increased
            if parent.id != self.root.id and parent.getContentsCount() >= row+1:
                positionOverflow  = insertPosition - parent.contents[row].position
                if positionOverflow > 0:
                    positionChanges = [ (n.position, n.position + positionOverflow) for n in parent.contents[row:] ]
                    pc = commands.PositionChangeCommand(EDITOR, parent.id, positionChanges, self.tr('adjust positions'))
                    modify.push(pc)
                        
            command = commands.InsertElementsCommand(EDITOR, {parent.id: ins}, 'dropCopy->insert')
            modify.push(command)
            modify.endMacro()
            return True
    
    def importNode(self, node):
        """Helper function to import a node into the editor. Checks if a node with the same ID already
        exists in some editor. If so, a copy of that is returned; otherwise the argument itself is returned."""
        if self.dropFromOutside:
            from ..gui import editor
            for model in editor.activeEditorModels():
                for e_node in model.root.getAllNodes(True):
                    if node.id == e_node.id:
                        return e_node.copy()                 
        return node
    
    def importFile(self, path):
        """The same as importNode, but for a file given by a path."""
        if self.dropFromOutside:
            from ..gui import editor
            for model in editor.activeEditorModels():
                for e_file in model.root.getAllFiles():
                    if e_file.path == relPath(path):
                        logger.debug('importing existing file ...')
                        return e_file.copy()
        file = File.fromFilesystem(path)
        file.fileTags = file.tags.copy()
        return file
     
    def _dropOMGMime(self, mimeData, action, parent, row):
        """handles drop of OMG mime data into the editor.
        
        Various cases (and combinations thereof)must be handled: Nodes might be copied or moved
        within the same parent, or moved / copied from the "outside"."""
        orig_nodes = OrderedDict()
        for node in mimeData.getElements():
            orig_nodes[node.id] = self.importNode(node) 
        # check for recursion error
        for node in itertools.chain.from_iterable( (o.getAllNodes() for o in orig_nodes.values() )):
            if node.id == parent.id:
                QtGui.QMessageBox.critical(None, self.tr('recursion error'),
                                           self.tr('Cannot place a container below itself.'))
                return False       
        
        move = OrderedDict()
        insert_same, insert_other = [], []
        for id, node in orig_nodes.items():
            if hasattr(node.parent, 'id') and node.parent.id == parent.id:
                if action == Qt.MoveAction:
                    move[id] = node
                else:
                    insert_same.append(node.copy())
            else:
                insert_other.append(node.copy())
        movedBefore = 0
        positionChanges = []
        currentPosition = 0 if isinstance(parent, RootNode) else 1
        commandsToPush = []
        for node in parent.contents[:row]:
            if node.id in move: # node moved away
                movedBefore += 1
            else:
                position = node.iPosition()
                currentPosition = position - movedBefore + 1
                if movedBefore > 0:
                    positionChanges.append( (position, position - movedBefore) )
        
        if action == Qt.MoveAction and len(insert_other) > 0:
            removeCommand = commands.RemoveElementsCommand(EDITOR,
                                                           insert_other,
                                                           mode = CONTENTS,
                                                           text = 'drop->remove')
            commandsToPush.append(removeCommand)
        for node in move.values():
            positionChanges.append( (node.iPosition(), currentPosition) )
            currentPosition += 1
        insertions = { parent.id:[] }
        for node in insert_same + insert_other:
            insertions[parent.id].append( (currentPosition, node) )
            if isinstance(parent, RootNode):
                node.position = None
            else:
                node.position = currentPosition
            currentPosition += 1
        
        # adjust positions behind
        for node in parent.contents[row:]:
            if node.id not in move and node.iPosition() < currentPosition:
                positionChanges.append( (node.iPosition(), currentPosition) )
                currentPosition += 1        
            
        command = commands.PositionChangeCommand(EDITOR, parent.id, positionChanges, self.tr('adjust positions'))
        commandsToPush.append(command)
        
        if len(insertions[parent.id]) > 0:
            insertCommand = commands.InsertElementsCommand(EDITOR, insertions, 'drop->insert')
            commandsToPush.append(insertCommand)
        modify.beginMacro(EDITOR, self.tr('drop elements'))
        for command in commandsToPush:
            modify.push(command)
        modify.endMacro()
        return True
        
    def _dropURLMime(self, urls):
        '''This method is called if url MIME data is dropped onto this model, from an external file manager
        or a filesystembrowser widget.'''
        files = collectFiles(sorted(url.path() for url in urls))
        numFiles = sum(len(v) for v in files.values())
        progress = QtGui.QProgressDialog()
        progress.setLabelText(self.tr("Importing {0} files...").format(numFiles))
        progress.setRange(0, numFiles)
        progress.setMinimumDuration(800)
        progress.setWindowModality(Qt.WindowModal)
        #elements = OrderedDict(files.keys())
        for path, pFiles in files.items():
            elems = []
            for f in pFiles:
                progress.setValue(progress.value() + 1)
                QtGui.QApplication.processEvents()
                if progress.wasCanceled():
                    return False
                readOk = False
                while not readOk:
                    try:
                        theFile = self.importFile(f)
                        elems.append(theFile)
                        readOk = True
                    except tags.UnknownTagError as e:
                        from ..gui.tagwidgets import NewTagTypeDialog
                        text = self.tr('Unknown tag\n{1}={2}\n found in \n{0}.\n What should its type be?').format(relPath(f), e.tagname, e.values)
                        dialog = NewTagTypeDialog(e.tagname, text = text,
                          includeDeleteOption = True)
                        ret = dialog.exec_()
                        if ret == dialog.Accepted:
                            pass
                        elif ret == dialog.Delete or ret == dialog.DeleteAlways:
                            
                            if ret == dialog.DeleteAlways:
                                config.options.tags.always_delete = config.options.tags.always_delete + [e.tagname]
                            logger.debug('REMOVE TAG {0} from {1}'.format(e.tagname, f))
                            real = realfiles.get(f)
                            real.remove(e.tagname)
                        else:
                            progress.cancel()
                            return False
            files[path] = elems
        if len(self.albumGroupers) > 0:            
            if "DIRECTORY" in self.albumGroupers:
                albums = []
                singles = []
                for k,v in sorted(files.items()):
                    try:
                        al, si = albumguesser.guessAlbums(v, self.albumGroupers)
                        albums.extend(al)
                        singles.extend(si)
                    except albumguesser.GuessError as e:
                        from ..gui.dialogs import warning
                        warning(self.tr("Error guessing albums"), str(e))
                        singles.extend(v)
            else:
                try:
                    albums, singles = self.guessAlbums(itertools.chain(*files.values()), self.albumGroupers)
                except albumguesser.GuessError as e:
                    from ..gui.dialogs import warning
                    warning(self.tr("Error guessing albums"), str(e))
                    singles.extend(itertools.chain(*files.values()))
            if self.albumGroupers == ["DIRECTORY"]:
                return albums + singles
            else:
                return albumguesser.guessMetaContainers(albums,
                                                    self.albumGroupers,
                                                    self.metacontainer_regex) + singles
        else:
            return list(itertools.chain(*files.values()))
