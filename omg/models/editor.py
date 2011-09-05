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
from ..modify import events, commands
from ..utils import hasKnownExtension, collectFiles, longestSubstring, relPath
from collections import OrderedDict
from functools import reduce
import re, string
import os
os.walk(None, None, None)

logger = logging.getLogger("models.editor")

class DynamicElementTreeIterator:
    
    def __init__(self, root):
        self.root = root
        self.current = root
        self.stopNext = False
    
    def __iter__(self):
        return self
    
    def proceed(self):
        cand = self.current.parent
        while cand.getContentsCount() == cand.contents.index(self.current) + 1:
            self.current = cand
            if self.current == self.root:
                return False
            cand = cand.parent
        self.current = cand.contents[cand.contents.index(self.current) + 1]
        return True
    
    def skip(self):
        if self.current.parent == self.previous:
            self.current = self.previous
            self.proceed()
        
    def __next__(self):
        if self.stopNext:
            raise StopIteration()
        self.previous = self.current
        if self.current.hasContents():
            self.current = self.current.contents[0]
        else:
            if self.current == self.root or not self.proceed():
                self.stopNext = True
        return self.previous
            
                
class EditorModel(rootedtreemodel.EditableRootedTreeModel):
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
        else:
            logger.warning('WARNING UNKNOWN EVENT {}, RESETTING EDITOR'.format(event))
            self.clear()
            
    def handleElementChangeEvent(self, event):
        iter = DynamicElementTreeIterator(self.root)
        for node in iter:
            print('at {}'.format(node))
            if node.id in event.ids():
                id = node.id
                logger.debug('event match ID={0} at {1}'.format(id, self.name))
                modelIndex = self.getIndex(node)
                
                if not event.contentsChanged:
                    # this handles SingleElementChangeEvent, all TagChangeEvents, FlagChangeEvents, ...
                    event.applyTo(node)
                elif isinstance(event, events.PositionChangeEvent):
                    event.applyTo(node)
                    self.dataChanged.emit(modelIndex.child(0, 0), modelIndex.child(node.getContentsCount()-1, 0))
                    
                elif isinstance(event, events.InsertElementsEvent):
                    for pos, newElements in event.insertions[id]:
                        self.beginInsertRows(modelIndex, pos, pos + len(newElements) - 1)
                        node.insertContents(pos, [e.copy() for e in newElements])
                        self.endInsertRows()
                        
                elif isinstance(event, events.RemoveElementsEvent):
                    for pos, num in event.removals[id]:
                        self.beginRemoveRows(modelIndex, pos, pos + num - 1)
                        del node.contents[pos:pos+num]
                        self.endRemoveRows()
                        
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
                        iter.skip()
                else:
                    logger.warning('unknown element change event: {}'.format(event))
                self.dataChanged.emit(modelIndex, modelIndex)
                if len(event.ids()) == 1:
                    return
           
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
            insertions = dict()
            insertions[parent.id] = [(row, nodes)]
            command = commands.InsertElementsCommand(modify.EDITOR, insertions, 'dropCopy->insert')
            modify.push(command)
            return True
    
    def _dropOMGMime(self, mimeData, action, parent, row):
        orig_nodes = list(mimeData.getElements())
            
        # check for recursion error
        for o in orig_nodes:
            for n in o.getAllNodes():
                if n.id == parent.id:
                    QtGui.QMessageBox.critical(None, self.tr('error'),self.tr('You cannot put a container below itself!'))
                    return False
                
        modify.beginMacro(modify.EDITOR, self.tr('drop elements'))
        
        subtractFromRow = 0
        if action == Qt.MoveAction:
            for node in orig_nodes:
                if node.parent.id == parent.id and node.parent.index(node) < row:
                    subtractFromRow += 1
            removeCommand = commands.RemoveElementsCommand(modify.EDITOR, orig_nodes, 'drop->remove')
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
                positionChanges = [(elem.position,elem.position+shift) for elem in reversed(parent.contents[row:]) ]
                command = commands.PositionChangeCommand(modify.EDITOR, parent.id, positionChanges, self.tr('adjust positions'))
                modify.push(command)
                         
        insertions = dict()
        insertions[parent.id] = [(row-subtractFromRow, insert_nodes)]
        insertCommand = commands.InsertElementsCommand(modify.EDITOR, insertions, 'drop->insert')
        modify.push(insertCommand)
        modify.endMacro()
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
                                              tags = tags.Storage(), flags = [], position = None)
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
            