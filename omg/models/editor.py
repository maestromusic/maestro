# -*- coding: utf-8 -*-
# Copyright 2011 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from .. import logging, modify, database as db, tags, realfiles2
from . import mimedata
from ..models import rootedtreemodel, RootNode, File, Container, Element
from ..config import options
from ..utils import hasKnownExtension, collectFiles, longestSubstring
from collections import OrderedDict
from functools import reduce
import re, string

logger = logging.getLogger("models.editor")

class EditorModel(rootedtreemodel.EditableRootedTreeModel):
    
    guessAlbums = True # whether to guess album structure on file drop
    
    def __init__(self, name = 'default'):
        super().__init__(RootNode())
        self.contents = []
        self.name = name
        modify.dispatcher.changes.connect(self.handleChangeEvent)

    
    
    def handleChangeEvent(self, event):
        """React on an incoming ChangeEvent by applying all changes that affect the
        current model."""
        if isinstance(event, modify.events.ElementChangeEvent):
            self.handleElementChangeEvent(event)
        elif isinstance(event, modify.events.ElementsDeletedEvent):
            print('real event incoming -- resetting editor ...')
            self.setRoot(RootNode())
        else:
            print('WARNING UNKNOWN EVENT {}, RESETTING EDITOR'.format(event))
            self.setRoot(RootNode())
            
    def handleElementChangeEvent(self, event):
        for id in event.ids():
            for node in self.root.getAllNodes(skipSelf = False):
                if node.id == id:
                    logger.debug('event match ID={0} at {1}'.format(id, self.name))
                    modelIndex = self.getIndex(node)
                    if isinstance(event, modify.events.SingleElementChangeEvent):
                        event.applyTo(node)
                        self.dataChanged.emit(modelIndex, modelIndex)
                        return # single element event -> no more IDs to check
                    
                    elif isinstance(event, modify.events.PositionChangeEvent) or \
                            isinstance(event, modify.events.NewElementChangeEvent):
                        event.applyTo(node)
                        self.dataChanged.emit(modelIndex.child(0, 0), modelIndex.child(len(node.contents)-1, 0))
                        
                    elif isinstance(event, modify.events.InsertElementsEvent):
                        for pos, newElements in event.insertions[id]:
                            self.beginInsertRows(modelIndex, pos, pos + len(newElements) - 1)
                            node.insertContents(pos, [e.copy() for e in newElements])
                            self.endInsertRows()
                            
                    elif isinstance(event, modify.events.RemoveElementsEvent):
                        for pos, num in event.removals[id]:
                            self.beginRemoveRows(modelIndex, pos, pos + num - 1)
                            del node.contents[pos:pos+num]
                            self.endRemoveRows()
                            
                    elif event.__class__ == modify.events.ElementChangeEvent:
                        if event.contentsChanged and not node.isFile():
                            self.beginRemoveRows(modelIndex, 0, node.getContentsCount())
                            temp = node.contents
                            node.contents = []
                            self.endRemoveRows()
                            node.contents = temp
                            self.beginInsertRows(modelIndex, 0, event.getNewContentsCount(node))
                            event.applyTo(node)
                            self.endInsertRows()
                        else:
                            event.applyTo(node)
                    else:
                        print('unknown element change event: {}'.format(event))
                    self.dataChanged.emit(modelIndex, modelIndex)
           
    def setContents(self,contents):
        """Set the contents of this playlist and set their parent to self.root.
        The contents are only the toplevel-elements in the playlist, not all files.
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
        return [options.gui.mime,"text/uri-list"]
    
    def mimeData(self,indexes):
        return mimedata.MimeData.fromIndexes(self,indexes)
    
    def dropMimeData(self,mimeData,action,row,column,parentIndex):
        """This function does all the magic that happens if elements are dropped onto this editor."""
        logger.debug("dropMimeData on {} row {}".format(self.data(parentIndex, Qt.EditRole), row))
        QtGui.QApplication.changeOverrideCursor(Qt.ArrowCursor) # dont display the DnD cursor during the warning
        if action == Qt.IgnoreAction:
            return True
        assert column <= 0
        parent = self.data(parentIndex, Qt.EditRole)
        # if something is dropped on a file, make it a sibling instead of a child of that file
        if parent is not self.root and parent.isFile():
                parent = parent.parent
                row = parentIndex.row() + 1
        # if something is dropped on now item, append it to the end of the parent
        if row == -1:
            row = parent.getContentsCount()
        if mimeData.hasFormat(options.gui.mime):
            # first case: OMG mime data -> nodes from an editor, browser etc.
            orig_nodes = list(mimeData.getElements())
            
            # check for recursion error
            for o in orig_nodes:
                for n in o.getAllNodes():
                    if n.id == parent.id:
                        
                        QtGui.QMessageBox.critical(None, self.tr('error'),self.tr('You cannot put a container below itself in the hierarchy!'))
                        return False
            modify.beginMacro(modify.EDITOR, 'drag&drop')
            freedPositions = []
            if action == Qt.MoveAction:
                subtractFromRow = 0
                for node in orig_nodes:
                    if node.parent.id == parent.id:
                        if node.parent.index(node) < row:
                            subtractFromRow += 1
                            if isinstance(node.parent, Element):
                                freedPositions.append(node.position)
                removeCommand = modify.RemoveElementsCommand(modify.EDITOR, orig_nodes, 'drop->remove')
                modify.push(removeCommand)
            insert_nodes = [node.copy() for node in orig_nodes]
            if isinstance(parent, RootNode):
                for node in insert_nodes:
                    node.position = None
            else:
                if row > parent.getContentsCount():
                    row = parent.getContentsCount()
                position = 1 if row == 0 else parent.contents[row-1].position + 1
                for node in insert_nodes:
                    node.position = position
                    position += 1
                if len(parent.contents) > row and parent.contents[row].position < position:
                        # need to increase positions of elements behind insertion
                        shift = position - parent.contents[row].position
                        for element in parent.contents[:row-1:-1]:
                            before = element.copy()
                            after = element.copy()
                            after.position += shift
                            command = modify.ModifySingleElementCommand(modify.EDITOR,before,after,'change position')
                            modify.push(modify.EDITOR, command)
                             
            insertions = dict()
            insertions[parent.id] = [(row, insert_nodes)]
            insertCommand = modify.InsertElementsCommand(modify.EDITOR, insertions, 'drop->insert')
            modify.push(insertCommand)
            modify.endMacro(modify.EDITOR)
                
        elif mimeData.hasFormat("text/uri-list"):
            # easy case: files and/or folders are dropped from outside or from a filesystembrowser.
            nodes = self._handleUrlDrop(mimeData.urls())
            if nodes is False:
                return False
            insertions = dict()
            insertions[parent.id] = [(row, nodes)]
            command = modify.InsertElementsCommand(modify.EDITOR, insertions, 'dropCopy->insert')
            modify.push(command)
        else: #unknown mimedata
            logger.warning('unknown mime data dropped')
            return False
        return True
    
    def _handleUrlDrop(self, urls):
        '''This method is called if url MIME data is dropped onto this model, from an external file manager
        or a filesystembrowser widget.'''
        files = sorted(set( (f for f in collectFiles((url.path() for url in urls)) if hasKnownExtension(f)) ))
        progress = QtGui.QProgressDialog()
        progress.setLabelText(self.tr("Importing {0} files...").format(len(files)))
        progress.setRange(0, len(files))
        progress.setMinimumDuration(1500)
        progress.setWindowModality(Qt.WindowModal)
        elementList = []
        for i,f in enumerate(files):
            progress.setValue(i+1)
            QtGui.QApplication.processEvents();
            if progress.wasCanceled():
                return False
            readOk = False
            while not readOk:
                try:
                    theFile = File.fromFilesystem(f)
                    theFile.fileTags = theFile.tags.copy()
                    elementList.append(theFile)
                    readOk = True
                except tags.UnknownTagError as e:
                    from ..gui.tagwidgets import NewTagTypeDialog
                    text = self.tr('File\n"{0}"\ncontains a so far unknown tag "{1}". What should its type be?').format(f, e.tagname)
                    dialog = NewTagTypeDialog(e.tagname, text = text,
                      includeDeleteOption = True)
                    ret = dialog.exec_()
                    if ret == dialog.Accepted:
                        pass
                    elif ret == dialog.Delete or ret == dialog.DeleteAlways:
                        
                        if ret == dialog.DeleteAlways:
                            options.tags.always_delete = options.tags.always_delete + [e.tagname]
                        logger.debug('REMOVE TAG {0} from {1}'.format(e.tagname, f))
                        real = realfiles2.get(f)
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
                    albumsFoundByName[album] = Container(id = modify.newEditorId(), contents = None, tags = tags.Storage(), position = None)
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
                    metaContainer = Container(id = modify.newEditorId(), contents = None, tags = tags.Storage(), position = None)
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
            
    def createMergeHint(self, indices):
        hintRemove = reduce(longestSubstring,
                   ( ", ".join(ind.internalPointer().tags[tags.TITLE]) for ind in indices )
                 )
        return hintRemove.strip(string.punctuation + string.whitespace), hintRemove
    
    def shiftPositions(self, elements, delta):
        '''Shift the positions of the given elements by *delta* (if valid).'''
        #TODO: method only works for continuous selection
        elements.sort(key = lambda el: el.position)
        parent = elements[0].parent
        if isinstance(parent, RootNode):
            return
        if delta > 0:
            if parent.contents[-1] != elements[-1]:
                # there are elements behind
                lastIndex = parent.contents.index(elements[-1])
                spaceBehind = parent.contents[lastIndex+1].position - elements[-1].position - 1
                if spaceBehind < delta:
                    raise NotImplementedError()
            positionChanges = [(element.position, element.position + delta) for element in reversed(elements)]
            command = modify.PositionChangeCommand(modify.EDITOR, parent.id, positionChanges, self.tr('position change'))
            modify.push(command)
        elif delta < 0:
            if parent.contents[0] != elements[0]:
                #there are elements before
                firstIndex = parent.contents.index(elements[0])
                spaceBefore = elements[0].position - parent.contents[firstIndex-1].position - 1
                if spaceBefore < -delta:
                    raise NotImplementedError()
            elif elements[0].position <= -delta:
                return # cannot decrease position 1
            positionChanges = [(element.position, element.position + delta) for element in elements]
            command = modify.PositionChangeCommand(modify.EDITOR, parent.id, positionChanges, self.tr('position change'))
            modify.push(command)
            