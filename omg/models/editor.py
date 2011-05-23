# -*- coding: utf-8 -*-
# Copyright 2011 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#


from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from .. import logging, modify
from . import mimedata
from ..models import rootedtreemodel, RootNode, File
from ..config import options
from ..utils import hasKnownExtension, collectFiles

from collections import OrderedDict
logger = logging.getLogger("models.editor")

class EditorModel(rootedtreemodel.EditableRootedTreeModel):
    def __init__(self, name = 'default'):
        rootedtreemodel.EditableRootedTreeModel.__init__(self, RootNode())
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
        defaultFlags = rootedtreemodel.EditableRootedTreeModel.flags(self,index)
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
        elementList = []
        for f in files:
            elementList.append(File.fromFilesystem(f))
        return elementList
    
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
                        
#===============================================================================
# class OldEditorModel(BasicPlaylist):
#    
#    def __init__(self):
#        BasicPlaylist.__init__(self)
#        
#    def _prepareMimeData(self, mimeData):
#        """Overwrites the function of BasicPlaylist to add album-recognition intelligence."""
#        if mimeData.hasFormat(options.gui.mime): # already elements -> no preprocessing needed
#            return [node.copy() for node in mimeData.retrieveData(options.gui.mime)]
#        elif mimeData.hasFormat('text/uri-list'):
#            filePaths = [relPath(path) for path in self._collectFiles(absPath(p.path()) for p in mimeData.urls())]
#            guess = omg.gopulate.GopulateGuesser(filePaths)
#            return guess.guessTree(True)
#        else:
#            return None
#        
#    def merge(self, indices, name):
#        self.undoStack.beginMacro("Merge {} items, title »{}«".format(len(indices),name))
#        amount = len(indices)
#        if amount > 0:
#            indices.sort(key = lambda ind: ind.row())
#            
#            rows = [ ind.row() for ind in indices ]
#            elements = [ ind.internalPointer() for ind in indices ]
#            parentIdx = indices[0].parent()
#            parent = elements[0].parent
#            if not parent:
#                parent = self.root()
#            lastrow = self.rowCount(parentIdx)
#            for row in reversed(rows): # remove element from current child list
#                if row != rows[0]:
#                    for r in range(row+1,lastrow): # adjust position of elements behind
#                        child = parentIdx.child(r,0).internalPointer()
#                        self.undoStack.push(PositionChangeCommand(child, child.position - 1))
#                self.undoStack.push(
#                      RemoveContentsCommand(self, parentIdx, row, 1))
#                lastrow -= 1
#            
#            newContainer = Container(id = None)
#            newContainer.parent = parent
#            newContainer.position = elements[0].position
#            newContainer.loadTags()
#            newContainer.setContents(elements)
#            for element,j in zip(elements, itertools.count(1)):
#                self.undoStack.push(PositionChangeCommand(element, j))
#                for tag, i in zip(element.tags[tags.TITLE], itertools.count()):
#                    if tag.find(name) != -1:
#                        newtag = tag.replace(name, "").\
#                            strip(constants.FILL_CHARACTERS).\
#                            lstrip("0123456789").\
#                            strip(constants.FILL_CHARACTERS)
#                        if newtag == "":
#                            newtag = "Part {}".format(i+1)
#                        self.undoStack.push(TagChangeCommand(element, tags.TITLE, i, newtag))
#            newContainer.updateSameTags()  
#            newContainer.tags[tags.TITLE] = [ name ]
#            self.undoStack.push(InsertContentsCommand(self, parent, row, [newContainer], copy = False))
#            
#            self.dataChanged.emit(
#                self.index(row, 0, parentIdx), self.index(self.rowCount(parentIdx)-1, 0, parentIdx))
#            self.dataChanged.emit(parentIdx, parentIdx)
#        self.undoStack.endMacro()
#        
#    def commit(self):
#        """Commits all the containers and files in the current model into the database."""
#        
#        logger.debug("commit called")
#        for item in self.root.contents:
#            item.commit(toplevel = True)
# 
# 
# # ALTER KRAM
# def computeHash(self):
#        """Computes the hash of the audio stream and stores it in the object's hash attribute."""
#    
#        import hashlib,tempfile,subprocess
#        handle, tmpfile = tempfile.mkstemp()
#        subprocess.check_call(
#            ["mplayer", "-dumpfile", tmpfile, "-dumpaudio", absPath(self.path)], #TODO: konfigurierbar machen
#            stdout=subprocess.PIPE,
#            stderr=subprocess.PIPE)
#        with open(handle,"br") as hdl:
#            self.hash = hashlib.sha1(hdl.read()).hexdigest()
#        os.remove(tmpfile)
#    
# def computeAndStoreHash(self):
#    self.computeHash()
#    db.query("UPDATE files SET hash = ? WHERE element_id = ?;", self.hash, self.id)
#    logger.debug("hash of file {} has been computed and set".format(self.path))
#    
# def commit(self, toplevel = False):
#    """Save this file into the database. After that, the object has an id attribute"""
#    if self.isInDB(): #TODO: tags commiten
#        return
#    
#    import omg.gopulate
#    logger.debug("commiting file {}".format(self.path))
#    self.id = queries.addContainer(
#                                    os.path.basename(self.path),
#                                    tags = self.tags,
#                                    file = True,
#                                    elements = 0,
#                                    toplevel = toplevel)
#    querytext = "INSERT INTO files (element_id,path,hash,length) VALUES(?,?,?,?);"
#    if self.length is None:
#        self.length = 0
#    if hasattr(self, "hash"):
#        hash = self.hash
#    else:
#        hash = 'pending'            
#    db.query(querytext, self.id, relPath(self.path), hash, int(self.length))
#    if hash == 'pending':
#        hashQueue.put((self.computeAndStoreHash, [], {}))
#    self._syncState = {}
# class PositionChangeCommand(QtGui.QUndoCommand):
#    
#    def __init__(self, element, pos):
#        QtGui.QUndoCommand.__init__(self, "change element position")
#        self.elem = element
#        self.pos = pos
#    
#    def redo(self):
#        self.oldpos = self.elem.position
#        self.elem.position = self.pos
#    
#    def undo(self):
#        self.elem.position = self.oldpos
# 
# class TagChangeCommand(QtGui.QUndoCommand):
#    
#    def __init__(self, element, tag, index, value):
#        QtGui.QUndoCommand.__init__(self, "change »{}« tag".format(tag.name))
#        self.elem = element
#        self.tag = tag
#        self.index = index
#        self.value = value
#    
#    def redo(self):
#        self.oldValue = self.elem.tags[self.tag][self.index]
#        self.elem.tags[self.tag][self.index] = self.value
#    def undo(self):
#        self.elem.tags[self.tag][self.index] = self.oldValue
#===============================================================================