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

from .. import logging, modify, database as db, tags, realfiles
from . import mimedata
from ..models import rootedtreemodel, RootNode, File, Container, Element
from ..config import options
from ..modify import events, commands
from ..utils import hasKnownExtension, collectFiles, relPath
from ..constants import EDITOR, CONTENTS
from collections import OrderedDict
import re, itertools, os

logger = logging.getLogger("models.editor")

def walk(element):
    """A tree iterator for elements, inspired by os.walk: Returns a tuple (element, contents)
    where contents may be modified in-place to influence further processing."""
    contents = element.getContents()[:]
    yield element, contents
    for child in contents:
        for x in walk(child):
            yield x
                    
class EditorModel(rootedtreemodel.RootedTreeModel):
    """Model class for the editors where users can edit elements before they are commited into
    the database."""
    
    
    def __init__(self, name = 'default'):
        """Initializes the model with the given name (used for debugging). A new RootNode will
        be created and set as root."""
        super().__init__(RootNode())
        self.contents = []
        self.name = name
        modify.dispatcher.changes.connect(self.handleChangeEvent)
        self.albumGroupers = []
        self.metacontainer_regex=r" ?[([]?(?:cd|disc|part|teil|disk|vol)\.? ?([iI0-9]+)[)\]]?"

    
    def handleChangeEvent(self, event):
        """React on an incoming ChangeEvent by applying all changes that affect the
        current model."""
        if isinstance(event, events.ElementChangeEvent):
            self.handleElementChangeEvent(event)
        elif isinstance(event, events.ElementsDeletedEvent):
            # real event incoming -- resetting editor ...
            self.clear()
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
            
    def handleElementChangeEvent(self, event):
        if self.root.id in event.ids():
            if self.applyChangesToNode(self.root, event):
                return
        for parent, children in walk(self.root):
            toRemove = []
            for i, node in enumerate(children): 
                if node.id in event.ids():
                    skip = self.applyChangesToNode(node, event)
                    if skip:
                        toRemove.append(i)
            for i in reversed(toRemove):
                del children[i]
    
    def applyChangesToNode(self, node, event):
        id = node.id
        logger.debug('event match ID={0} at {1}'.format(id, self.name))
        modelIndex = self.getIndex(node)
        if not event.contentsChanged:
            # this handles SingleElementChangeEvent, all TagChangeEvents, FlagChangeEvents, ...
            logger.debug('editor - tag change event!')
            event.applyTo(node)
            ret = isinstance(event, events.SingleElementChangeEvent)
        elif isinstance(event, events.PositionChangeEvent):
            self.changePositions(node, event.positionMap)
            ret = False
        elif isinstance(event, events.InsertContentsEvent):
            self.insert(node, event.insertions[id])
            ret = False   
        elif isinstance(event, events.RemoveContentsEvent):
            for i, elem in reversed(list(enumerate(node.contents))):
                position = elem.position if not isinstance(node, RootNode) else node.index(elem)
                if position in event.removals[id]:
                    self.beginRemoveRows(modelIndex, i, i)
                    del node.contents[i]
                    self.endRemoveRows()
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
           
    def setContents(self,contents):
        """Set the contents of this editor and set their parent to self.root.
        All views using this model will be reset."""
        self.contents = contents
        self.root.contents = contents
        for node in contents:
            node.setParent(self.root)
        self.reset()
        
    def flags(self,index):
        defaultFlags = super().flags(index)
        if index.isValid():
            return defaultFlags | Qt.ItemIsDropEnabled | Qt.ItemIsDragEnabled
        else: return defaultFlags | Qt.ItemIsDropEnabled

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction
    
    def mimeTypes(self):
        return (options.gui.mime,"text/uri-list")
    
    def mimeData(self,indexes):
        return mimedata.MimeData.fromIndexes(self,indexes)
    
    def dropMimeData(self,mimeData,action,row,column,parentIndex):
        """This function does all the magic that happens if elements are dropped onto this editor."""
        logger.debug("dropMimeData on {} row {}".format(self.data(parentIndex, Qt.EditRole), row))
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
        if mimeData.hasFormat(options.gui.mime):
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
                insertPosition += 1
            # now check if the positions of the subsequent nodes have to be increased
            if parent.id != self.root.id and parent.getContentsCount() >= row+1:
                positionOverflow  = insertPosition - parent.contents[row].position
                if positionOverflow > 0:
                    positionChanges = [ (n.position, n.position + positionOverflow) for n in parent.contents[row:] ]
                    pc = commands.PositionChangeCommand(EDITOR, parent.id, positionChanges, self.tr('adjust positions'))
                    modify.push(pc)
                        
            command = commands.InsertElementsCommand(modify.EDITOR, {parent.id: ins}, 'dropCopy->insert')
            modify.push(command)
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
            insertCommand = commands.InsertElementsCommand(modify.EDITOR, insertions, 'drop->insert')
            commandsToPush.append(insertCommand)
        modify.beginMacro(modify.EDITOR, self.tr('drop elements'))
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
                                options.tags.always_delete = options.tags.always_delete + [e.tagname]
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
                    al, si = self.guessAlbums(v)
                    albums.extend(al)
                    singles.extend(si)
            else:
                albums, singles = self.guessAlbums(itertools.chain(*files.values()))
            return self.guessMetaContainers(albums) + singles
        else:
            return list(itertools.chain(*files.values()))
    
    def guessAlbums(self, elements):
        groupTags = self.albumGroupers[:]
        albumTag = groupTags[0]
        dirMode = albumTag == "DIRECTORY"
        if "DIRECTORY" in groupTags:
            groupTags.remove("DIRECTORY")
        byKey = {}
        for element in elements:
            if dirMode:
                key = relPath(os.path.dirname(element.path))
            else:
                key = tuple( (tuple(element.tags[tag]) if tag in element.tags else None) for tag in groupTags)
            if key not in byKey:
                byKey[key] = []
            byKey[key].append(element)
            if element.position is None:
                element.position = 1
        singles, albums = [], []
        for key, elements in byKey.items():
            elem = elements[0]
            if dirMode or (albumTag in elem.tags):
                album = Container(modify.newEditorId(), [], tags.Storage(), [], None, True)
                for elem in sorted(elements, key = lambda e: e.position):
                    if len(album.contents) > 0 and album.contents[-1].position == elem.position:
                        raise RuntimeError('multiple positions below same album -- please fix this with TagEditor!!')
                    album.contents.append(elem)
                    elem.parent = album
                album.tags = tags.findCommonTags(album.contents, True)
                album.tags[tags.TITLE] = [key] if dirMode else elem.tags[albumTag]
                albums.append(album)
            else:
                element.position = None
                singles.append(element)
        return albums, singles
    
    def guessMetaContainers(self, albums):
        # search for meta-containers in albums
        groupTags = self.albumGroupers[:]
        albumTag = groupTags[0]
        dirMode = albumTag == "DIRECTORY"
        if "DIRECTORY" in groupTags:
            groupTags.remove("DIRECTORY")
        metaContainers = OrderedDict()
        result = []
        for album in albums:
            name = ", ".join(album.tags[tags.TITLE])
            discstring = re.findall(self.metacontainer_regex, name,flags=re.IGNORECASE)
            if len(discstring) > 0:
                discnumber = discstring[0]
                if discnumber.lower().startswith("i"): #roman number, support I-III :)
                    discnumber = len(discnumber)
                else:
                    discnumber = int(discnumber)
                discname_reduced = re.sub(self.metacontainer_regex,"",name,flags=re.IGNORECASE)
                key = tuple( (tuple(album.tags[tag]) if tag in album.tags else None) for tag in groupTags[1:])
                if (key, discname_reduced) in metaContainers:
                    metaContainer = metaContainers[(key, discname_reduced)]
                else:
                    metaContainer = Container(modify.newEditorId(), None, tags.Storage(), [], None, True)
                    metaContainers[(key, discname_reduced)] = metaContainer
                metaContainer.contents.append(album)
                album.position = discnumber
                album.parent = metaContainer
            else:
                result.append(album)
        for key, meta in metaContainers.items():
            meta.tags = tags.findCommonTags(meta.contents, True)
            meta.tags[tags.TITLE] = [key[1]]
            meta.tags[albumTag] = [key[1]]
            meta.sortContents()
            for i in range(1, len(meta.contents)):
                if meta.contents[i].position == meta.contents[i-1].position:
                    raise RuntimeError('multiple positions below same meta-container -- please fix this with TagEditor!!')
            result.append(meta)
        return result
