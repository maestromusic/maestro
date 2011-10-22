# -*- coding: utf-8 -*-
# Copyright 2011 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
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
    
    guessAlbums = True # whether to guess album structure on file drop
    
    def __init__(self, name = 'default'):
        """Initializes the model with the given name (used for debugging). A new RootNode will
        be created and set as root."""
        super().__init__(RootNode())
        self.contents = []
        self.name = name
        modify.dispatcher.changes.connect(self.handleChangeEvent)

    
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
            print('editor - tag change event!')
            event.applyTo(node)
            ret = False
        elif isinstance(event, events.PositionChangeEvent):
            event.applyTo(node)
            self.dataChanged.emit(modelIndex.child(0, 0), modelIndex.child(node.getContentsCount()-1, 0))
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
        parent = parent.copy()
        if mimeData.hasFormat(options.gui.mime):
            # first case: OMG mime data -> nodes from an editor, browser etc.
            return self._dropOMGMime(mimeData, action, parent, row)
        elif mimeData.hasFormat("text/uri-list"):
            # easy case: files and/or folders are dropped from outside or from a filesystembrowser.
            nodes = self._handleUrlDrop(mimeData.urls())
            if nodes is False:
                return False
            ins = []
            for index, node in enumerate(nodes, start = row):
                ins.append( (index, node) )
            insertions = {parent.id: ins}
            command = commands.InsertElementsCommand(modify.EDITOR, insertions, 'dropCopy->insert')
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
                position = parent.index(node, True) if isinstance(parent, RootNode) else node.position
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
            positionChanges.append( (node.position, currentPosition) )
            currentPosition += 1
        insertions = { parent.id:[] }
        for node in insert_same + insert_other:
            insertions[parent.id].append( (currentPosition, node) )
            if not isinstance(parent, RootNode):
                node.position = currentPosition
            currentPosition += 1
        
        # adjust positions behind
        for node in parent.contents[row:]:
            if node.id not in move and node.position < currentPosition:
                positionChanges.append( (node.position, currentPosition) )
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
        
    def _handleUrlDrop(self, urls):
        '''This method is called if url MIME data is dropped onto this model, from an external file manager
        or a filesystembrowser widget.'''
        files = sorted(set( (f for f in collectFiles((url.path() for url in urls)) if hasKnownExtension(f)) ))
        progress = QtGui.QProgressDialog()
        progress.setLabelText(self.tr("Importing {0} files...").format(len(files)))
        progress.setRange(0, len(files))
        progress.setMinimumDuration(800)
        progress.setWindowModality(Qt.WindowModal)
        elementList = []
        for i,f in enumerate(files):
            progress.setValue(i+1)
            QtGui.QApplication.processEvents()
            if progress.wasCanceled():
                return False
            readOk = False
            while not readOk:
                try:
                    theFile = self.importFile(f)
                    elementList.append(theFile)
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
        if self.guessAlbums:
            return self.guessTree(elementList)
        else:
            return elementList
        
    def setGuessAlbums(self, state):
        self.guessAlbums = state == Qt.Checked
        
    def guessTree(self, files):
        """Tries to guess a container structure from the given File list."""
        
        albumsFoundByName = {} # name->container map
        albumsFoundByID = {} #id->container map
        
        for file in files:
            id = file.id
            t = file.tags
            if id > 0:
                albumIds = db.parents(id)
                for aid in albumIds:
                    if not aid in albumsFoundByID:
                        exAlb = albumsFoundByID[aid] = Container.fromId(aid)
                    exAlbName = ", ".join(exAlb.tags[tags.TITLE])
                    if not exAlbName in albumsFoundByName:
                        albumsFoundByName[exAlbName] = exAlb
                    
                    file.parent = exAlb
                    exAlb.contents.append(file)
            elif tags.ALBUM in t:
                album = ", ".join(t[tags.ALBUM])
                if not album in albumsFoundByName:
                    albumsFoundByName[album] = Container(id = modify.newEditorId(),
                                                         contents = None,
                                                         tags = tags.Storage(),
                                                         flags = [], position = None, major = True)
                file.parent = albumsFoundByName[album]
                albumsFoundByName[album].contents.append(file)
                if file.position is None:
                    file.position = 0
            elif tags.TITLE in t:
                album = "SingleFile" + ", ".join(t[tags.TITLE])
                albumsFoundByName[album] = file
            else:
                album = file.path
                albumsFoundByName[album] = file
            
        
        for album in albumsFoundByName.values():
            self.finalize(album)
        FIND_DISC_RE=r" ?[([]?(?:cd|disc|part|teil|disk|vol)\.? ?([iI0-9]+)[)\]]?"
        metaContainers = {}
        finalAlbums = []
        for name, album in albumsFoundByName.items():
            discstring = re.findall(FIND_DISC_RE,name,flags=re.IGNORECASE)
            if len(discstring) > 0:
                discnumber = discstring[0]
                if discnumber.lower().startswith("i"): #roman number, support I-III :)
                    discnumber = len(discnumber)
                else:
                    discnumber = int(discnumber)
                discname_reduced = re.sub(FIND_DISC_RE,"",name,flags=re.IGNORECASE)
                if discname_reduced in metaContainers:
                    metaContainer = metaContainers[discname_reduced]
                else:
                    metaContainer = Container(id = modify.newEditorId(), contents = None,
                                              tags = tags.Storage(), flags = [], major = True, position = None)
                    metaContainers[discname_reduced] = metaContainer
                metaContainer.contents.append(album)
                album.position = discnumber
                album.parent = metaContainer
            else:
                finalAlbums.append(album)
        for title, album in metaContainers.items():
            self.finalize(album)
            album.tags[tags.TITLE] = [title]
        finalAlbums.extend(metaContainers.values())
        return finalAlbums
        
    def finalize(self, album):
        """Finalize a heuristically guessed album: Update tags such that the album contains
        all tags that are equal in all children."""
        if album.isFile():
            return
        album.contents.sort(key=lambda x : x.position or -1)
        album.tags = tags.findCommonTags(album.contents, True)
        if tags.ALBUM in album.tags:
            album.tags[tags.TITLE] = album.tags[tags.ALBUM]
    
    def shiftPositions(self, elements, delta):
        '''Shift the positions of the given elements by *delta* (if valid).'''
        elementsByParents = itertools.groupby(elements, key = lambda x: x.parent.id)
        for key, group in elementsByParents:
            elems = sorted(group, key = lambda x: x.position)
            parent = elems[0].parent
            if isinstance(parent, RootNode):
                continue
            if delta < 0 and elems[0].position + delta <= parent.contents.index(elems[0]):
                from ..gui.dialogs import warning
                warning('position below zero', 'not enough space before to decrease position')
                continue
            positionChanges = []
            unit = (-1)**(delta<0) # -1 if delta < 0 else 1
            currentPosition = parent.contents[-1+(delta>0)].position
            for elem in parent.contents[::unit]:
                if elem in elems:
                    positionChanges.append( (elem.position, elem.position+delta) )
                    currentPosition = elem.position + delta + unit
                else:
                    if elem.position*unit < currentPosition*unit:
                        positionChanges.append( (elem.position, currentPosition) )
                    currentPosition += unit
                    
            command = commands.PositionChangeCommand(modify.EDITOR, parent.id, positionChanges, self.tr('position change'))
            modify.push(command)
            