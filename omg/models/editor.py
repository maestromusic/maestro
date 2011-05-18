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
    def __init__(self):
        rootedtreemodel.EditableRootedTreeModel.__init__(self, RootNode())
        self.contents = []
        modify.dispatcher.changes.connect(self.handleChangeEvent)

    
    
    def handleChangeEvent(self, event):
        if event.origin is None or event.origin == self:
            logger.info("CHANGE EVENT INCOMING!!!!!")
            logger.info(str(event))
            for id in event.changes:
                if id is None:
                    self.setRoot(event.changes[id].copy())
                    print("new root with {} children".format(event.changes[id].getContentsCount()))
                else:
                    allNodes = self.root.getAllNodes()
                    next(allNodes) # skip root node
                    for node in allNodes:
                        if node.id == id:
                            node 
    def setContents(self,contents):
        """Set the contents of this playlist and set their parent to self.root. The contents are only the toplevel-elements in the playlist, not all files. All views using this model will be reset."""
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
        if action == Qt.IgnoreAction:
            return True

        if column > 0:
            return False
        parent = self.data(parentIndex, role = Qt.EditRole)
        if parent is not None and parent.isFile(): # if something is dropped on a file, make it a sibling instead of a child of that file
                parent = parent.parent
                row = parentIndex.row() + 1
        if mimeData.hasFormat("text/uri-list"):
            nodes = self._handleUrlDrop(mimeData.urls())
        elif mimeData.hasFormat(options.gui.mime):
            nodes = [node.copy() for node in mimeData.retrieveData(options.gui.mime)]
        else:
            return False
        changes = OrderedDict()
        parent_copy = parent.copy()
        parent_copy.contents[row:row] = nodes
        for n in nodes:
            n.setParent(parent_copy)
        changes[None] = (parent, parent_copy)
        command = modify.UndoCommand(level = modify.EDITOR, changes = changes, contentsChanged = True, origin = self)
        logger.info("pushing undo command")
        modify.stack.activeStack().push(command)
        return True
    
    def _handleUrlDrop(self, urls):
        files = sorted(set( (f for f in collectFiles((url.path() for url in urls)) if hasKnownExtension(f)) ))
        elementList = []
        for f in files:
            elementList.append(File.fromFilesystem(f))
        return elementList
        
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