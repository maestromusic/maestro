# -*- coding: utf-8 -*-
# Copyright 2011 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#


from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from .. import logging, modify, database as db, tags
from . import mimedata
from ..models import rootedtreemodel, RootNode, File, Container
from ..config import options
from ..utils import hasKnownExtension, collectFiles

from collections import OrderedDict
from functools import reduce
import re

logger = logging.getLogger("models.editor")

class EditorModel(rootedtreemodel.EditableRootedTreeModel):
    def __init__(self, name = 'default'):
        super().__init__(RootNode())
        self.contents = []
        self.name = name
        modify.dispatcher.changes.connect(self.handleChangeEvent)

    
    
    def handleChangeEvent(self, event):
        """React on an incoming ChangeEvent by applying all changes that affect the
        current model."""
        logger.info("incoming change event at {}".format(self.name))
        for id,elem in event.changes.items():
            if id == self.root.id:
                self.setRoot(event.changes[id].copy())
            else:
                allNodes = self.root.getAllNodes()
                next(allNodes) # skip root node
                for node in allNodes:
                    if node.id == id:
                        elemcopy = elem.copy()
                        parent = node.parent
                        index = node.parent.index(node)
                        self.remove(node)
                        self.insert(parent, index, elemcopy)
    
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
        return mimedata.createFromIndexes(self,indexes)
    
    def dropMimeData(self,mimeData,action,row,column,parentIndex):
        """This function does all the magic that happens if elements are dropped onto this editor."""
        print("dropMimeData on {} row {}".format(self.data(parentIndex, Qt.EditRole), row))
        QtGui.QApplication.changeOverrideCursor(Qt.ArrowCursor) # dont display the DnD cursor during the warning
        if action == Qt.IgnoreAction:
            return True
        if column > 0:
            return False
        parent = self.data(parentIndex, Qt.EditRole)
        if parent is not self.root and parent.isFile():
                # if something is dropped on a file, make it a sibling instead of a child of that file
                parent = parent.parent
                row = parentIndex.row() + 1
        if row == -1:
            # if something is dropped on now item, append it to the end of the parent
            row = parent.getContentsCount()
        parent_copy = parent.copy() # all changes will be performed on this copy
        changes = OrderedDict()
        if mimeData.hasFormat(options.gui.mime):
            # first case: OMG mime data -> nodes from an editor, browser etc.
            orig_nodes = mimeData.retrieveData(options.gui.mime)
            for o in orig_nodes:
                # check for recursion error
                for n in o.getAllNodes():
                    if n.id == parent.id:
                        
                        QtGui.QMessageBox.critical(None, self.tr('error'),self.tr('You cannot put a container below itself in the hierarchy!'))
                        return False
            if action == Qt.CopyAction:
                # the easy case: just add the copied nodes at the specified row
                nodes = [n.copy() for n in orig_nodes]
                parent_copy.contents[row:row] = nodes
                for n in nodes:
                    n.setParent(parent_copy)
                changes[parent.id] = (parent.copy(), parent_copy)
            else:
                # if nodes are moved, we must handle the case that nodes are moved inside the same parent in a special way.
                # this may happen even if the parents are not the same python objects, because they can be moved between different
                # editors that show the same container.
                sameParentIndexes = [n.parent.index(n) for n in orig_nodes if n.parent.id == parent.id]
                sameParentIndexes.sort(reverse = True)
                sameParentNodes = [parent_copy.contents[i] for i in sameParentIndexes]
                otherParentNodes = [n for n in orig_nodes if n.parent.id != parent.id]
                print("sameParentIds: {}".format(sameParentIndexes))
                otherParentIds = set(n.parent.id for n in otherParentNodes)
                print("otherParentIds: {}".format(otherParentIds))
                offset = 0
                for i in sameParentIndexes:
                    # remove the elements that were moved, and remember how much of them are moved before
                    # the selected insertion row.
                    del parent_copy.contents[i]
                    if i < row:
                        offset += 1
                row -= offset
                otherParentNodes_copy = [n.copy() for n in otherParentNodes]
                # now insert the nodes (and possibly others from other parents
                parent_copy.contents[row:row] = sameParentNodes + otherParentNodes_copy
                for n in sameParentNodes + otherParentNodes_copy:
                    n.setParent(parent_copy)
                changes[parent.id] = (parent.copy(), parent_copy)
                # create remove events for the nodes with different parents
                for id in otherParentIds:
                    children = [n for n in otherParentNodes if n.parent.id == id]
                    children.sort(key = lambda n: n.parent.index(n), reverse = True)
                    otherParent_before = children[0].parent.copy()
                    otherParent_after = children[0].parent.copy()
                    for c in children:
                        del otherParent_after.contents[c.parent.index(c)]
                    changes[id] = (otherParent_before, otherParent_after)
                
        elif mimeData.hasFormat("text/uri-list"):
            # easy case: files and/or folders are dropped from outside or from a filesystembrowser.
            nodes = self._handleUrlDrop(mimeData.urls())
            if nodes is False:
                return False
            parent_copy.contents[row:row] = nodes
            for n in nodes:
                n.setParent(parent_copy)
            changes[parent.id] = (parent.copy(), parent_copy)
        else: #unknown mimedata
            return False

        command = modify.UndoCommand(level = modify.EDITOR, changes = changes, contentsChanged = True)        
        modify.pushEditorCommand(command)
        return True
    
    def _handleUrlDrop(self, urls):
        files = sorted(set( (f for f in collectFiles((url.path() for url in urls)) if hasKnownExtension(f)) ))
        progress = QtGui.QProgressDialog()
        progress.setLabelText(self.tr("Importing {0} files...").format(len(files)))
        progress.setRange(0, len(files))
        progress.setMinimumDuration(1500)
        progress.setWindowModality(Qt.WindowModal)
        print(len(files))
        elementList = []
        for i,f in enumerate(files):
            progress.setValue(i+1)
            QtGui.QApplication.processEvents();
            if progress.wasCanceled():
                return False
            readOk = False
            while not readOk:
                try:
                    elementList.append(File.fromFilesystem(f))
                    readOk = True
                except tags.UnknownTagError as e:
                    descMap = {'{n} ({d})'.format(n = t.name, d = t.description):t for t in tags.TYPES}
                    selection, ok = QtGui.QInputDialog.getItem(None,
                       self.tr('new tag »{0}« found'.format(e.tagname)),
                       self.tr('File <{0}> contains a so far unknown tag »{1}«. What should its type be?'.format(f, e.tagname)),
                       list(descMap.keys()),
                       0,
                       False,
                       QtCore.Qt.Dialog)
                    if ok:
                        tags.addTag(e.tagname, descMap[selection])
                    else:
                        progress.cancel()
                        return False
        return self.guessTree(elementList)
    
    def fireRemoveIndexes(self, elements):
        """Creates and pushes an UndoCommand that removes the selected elements from this model (and all other
        editor models containing them). Elements must be an iterable of either QModelIndexes or Nodes.
        """ 
        if len(elements) == 0:
            return
        if isinstance(elements[0], QtCore.QModelIndex):
            elements = [self.data(i, Qt.EditRole) for i in elements]
        for i in reversed(elements):
            for p in i.getParents():
                if p in elements:
                    elements.remove(i)
        changes = OrderedDict()
        affectedParents = set(i.parent for i in elements)
        for p in affectedParents:
            oldParent = p.copy()
            newParent = p.copy()
            for child in sorted((i for i in elements if i.parent == p), key = lambda i: i.parent.index(i), reverse = True):
                del newParent.contents[child.parent.index(child)]
            changes[p.id] = (oldParent, newParent)
        command = modify.UndoCommand(level = modify.EDITOR, changes = changes, contentsChanged = True)
        modify.pushEditorCommand(command)
    
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
                    albumsFoundByName[album] = Container(tags = tags.Storage(), position = None, id = modify.newEditorId())
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
                    metaContainer = Container(tags.Storage(), None, modify.newEditorId(), None)
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
        commonTags = set(x for x in reduce(lambda x,y: x & y, [set(elem.tags.keys()) for elem in album.getAllNodes(skipSelf = True)]))
        commonTagValues = {}
        differentTags=set()
        
        for element in album.getAllNodes(skipSelf = True):
            t = element.tags
            for tag in commonTags:
                if tag not in commonTagValues:
                    commonTagValues[tag] = t[tag]
                elif commonTagValues[tag] != t[tag]:
                    differentTags.add(tag)
        sameTags = commonTags - differentTags
        album.tags.clear()
        for tag in sameTags:
            album.tags[tag] = commonTagValues[tag]
        if tags.ALBUM in album.tags:
            album.tags[tags.TITLE] = album.tags[tags.ALBUM]