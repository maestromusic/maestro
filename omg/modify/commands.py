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

import itertools
from collections import OrderedDict

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import tags as tagsModule, logging, database as db, models, flags as flagsModule
from ..models import algorithms
from . import events, real, dispatcher
from .. import modify
from ..constants import REAL, EDITOR, CONTENTS, DB, DISK, ADDED, DELETED, CHANGED

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

class ElementChangeCommand(QtGui.QUndoCommand):
    """An undo command changing the elements on some level. Has the following attributes:
     - level: an instance of omg.models.levels.Level
     - ids: a list of IDs which are affected by the command
     - contents: a boolean indicating if content relations have changed
    """
    def __init__(self, level, ids = None, contents = None, text = None):
        super().__init__()
        self.level = level
        self.ids = ids
        self.contents = contents
        if text is not None:
            self.setText(text)
    
    def redoChanges(self):
        raise NotImplementedError()
    
    def undoChanges(self):
        raise NotImplementedError()
    
    def redo(self):
        self.redoChanges()
        self.level.changed.emit(self.ids, self.contents)
        
    def undo(self):
        self.undoChanges()
        self.level.changed.emit(self.ids, self.contents)

class UndoCommand(QtGui.QUndoCommand):
    """A generic undo command for arbitrary changes. The constructor gets an OrderedDict mapping
    ids to a tuple, specifying the state of that element before and after the change, respectively.
    
    Whenever possible, use specialized undo commands (or create own subclasses) below which allow for
    a more efficient implementation and widget notification."""
    
    level = REAL
    
    def __init__(self, level, changes, contentsChanged = False, text = ''):
        """Creates an UndoCommand, i.e. an object that stores what has changed in one
        step of database editing.
        
        <changes> is an OrderedDict of ids to tuples of Elements:
        The state before and after the change.
        <level> must be either EDITOR or REAL.
        <contentsChanged> must be True if for at least one of the elements the content
        relations are changed.
        <text> is a user-readable text describing the action; this will appear in the undo/redo menu entries."""
        QtGui.QUndoCommand.__init__(self)
        self.level  = level
        self.changes = changes
        self.contentsChanged = contentsChanged
        self.setText(text)
        
    def redo(self):
        if self.level == REAL:
            real.commit(self.changes)
        else:
            redoChanges = OrderedDict(( (k,v[1]) for k,v in self.changes.items() ))
            redoEvent = events.ElementChangeEvent(self.level, redoChanges, contentsChanged = self.contentsChanged)
            dispatcher.changes.emit(redoEvent)

    def undo(self):
        if self.level == REAL:
            undoChanges = {k:(v[1],v[0]) for k,v in self.changes.items() }
            assert len(undoChanges) > 0
            real.commit(undoChanges)
        else:
            undoChanges = OrderedDict(( (k,v[0]) for k,v in self.changes.items() ))
            undoEvent = events.ElementChangeEvent(self.level, undoChanges, contentsChanged = self.contentsChanged)
            dispatcher.changes.emit(undoEvent)
            
            
class CommitCommand(UndoCommand):
    
    def __init__(self):
        QtGui.QUndoCommand.__init__(self)
        self.setText('commit')
        # store (copies of) contents of all open editors in self.editorRoots
        from ..gui import editor
        editorModels = editor.activeEditorModels()
        self.editorRoots = [model.root.copy() for model in editorModels]
        
        # save current state in the editors in dicts mapping id->element
        self.newElements, self.dbElements = dict(), dict()
        for element in itertools.chain.from_iterable(
                                            root.getAllNodes(skipSelf = True) for root in self.editorRoots):
            if element.isInDB():
                if not element.id in self.dbElements:
                    self.dbElements[element.id] = element
            else:
                if not element.id in self.newElements:
                    self.newElements[element.id] = element
        
        #load original states of in-db elements (needed for undo)
        self.originalElements = dict()
        for element in self.dbElements.values():
            origEl = models.Element.fromId(element.id, loadData = True)
            if origEl.isContainer():
                origEl.loadContents(recursive = False, loadData = False)
            self.originalElements[element.id] = origEl
        
    def redo(self):
        """Perform the commit. This is done by the following steps:
          - copy roots of all editors, clear them afterwards
          - generate real IDs for new elements
          - call real.commit() for all elements contained in the editors; this will also
            invoke a ElementsChangeEvent for all the changes (new elements will have a negative
            id as key in the dictionary)
          - restore the (committed) content in the editors by an appropriate event"""
        
        progress = QtGui.QProgressDialog(translate(__name__, "Commiting files..."),
                                         None, 0, 7)
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModal)
        progress.setValue(1)
        # assign new IDs to all elements which have editor IDs so far
        if hasattr(self, 'idMap'): # this is not the first redo
            elementsToCreate = []
            for elem in self.newElements.values():
                elemCopy = elem.copy()
                elemCopy.id = self.idMap[elem.id]
                elementsToCreate.append(elemCopy)
            real.createNewElements(elementsToCreate)
        else:
            self.idMap = real.createNewElements(self.newElements.values())
            
        
        progress.setValue(2)
        # store new IDs in the editors (old ones are still available via self.idMap
        for elem in itertools.chain( *(root.getAllNodes(skipSelf = True) for root in self.editorRoots) ):
            if not elem.isInDB():
                elem.id = self.idMap[elem.id]
                
        # commit all the changes
        changes = {}
        for id, elem in self.newElements.items():
            if elem.isFile():
                oldElem = models.File(id = self.idMap[id], tags = tagsModule.Storage(),
                                      flags = list(), path = elem.path, length = None,
                                      position = None)
                if hasattr(elem, 'fileTags'):
                    oldElem.fileTags = elem.fileTags
            else:
                oldElem = models.Container(id = self.idMap[id], contents = list(),
                                           tags = tagsModule.Storage(),
                                         flags = list(), position = None, major = elem.major)
            changes[self.idMap[id]] = ( oldElem, elem )
        progress.setValue(3)
        for id, elem in self.dbElements.items():
            changes[id] = ( self.originalElements[id], self.dbElements[id] )
        progress.setValue(4)
        real.commit(changes, newIds = tuple(self.idMap.values()))
        progress.setValue(5)
        # notify the editors to display the new commited content
        dispatcher.changes.emit(events.ElementChangeEvent(
                            EDITOR, {root.id:root for root in self.editorRoots}, True))
        progress.setValue(6)
        
        
    def undo(self):
        """Undo the commit. This is relatively easy:
          - empty all editors
          - revert the changes for elements which previously existed in the DB
          - delete elements which didn't; if they are files, restore the original tags
        """
        # clear the editors
        emptyRoots = [root.copy(contents = []) for root in self.editorRoots]
        dispatcher.changes.emit(events.ElementChangeEvent(
                            REAL, {root.id:root for root in emptyRoots}, True))
        
        # undo changes to elements that were in the db before
        changes = {}
        for id, elem in self.dbElements.items():
            changes[id] = ( self.dbElements[id], self.originalElements[id] )
        real.commit(changes)
        # write original tags to files which were newly added
        tagChanges = {}
        for elem in self.newElements.values():
            if elem.isFile():
                tagChanges[elem.id] = (elem.tags, elem.fileTags)
        real.changeTags(tagChanges,self.newElements.values(),emitEvent = False) 
        
        # delete all elements which had editorIDs before
        real.deleteElements([el.id for el in self.newElements.values() ])
        
        # restore original element IDs (for next redo)
        revIdMap = {b:a for (a,b) in self.idMap.items()}
        for elem in itertools.chain.from_iterable(
                                            root.getAllNodes(skipSelf = True) for root in self.editorRoots):
            if elem.id in revIdMap:
                elem.id = revIdMap[elem.id]
        dispatcher.changes.emit(events.ElementChangeEvent(
                            EDITOR, {root.id:root for root in self.editorRoots}, True))
                

class ChangeSingleElementCommand(UndoCommand):
    """A specialized undo command for the modification of a single element (tags, position, ..., but no 
    contents)."""
    
    def __init__(self, level, before, after, text=''):
        QtGui.QUndoCommand.__init__(self, text)
        if level != EDITOR:
            raise NotImplementedError()
        self.level = level
        self.before = before.copy()
        self.after = after.copy()
    
    def redo(self):
        dispatcher.changes.emit(events.SingleElementChangeEvent(self.level, self.after))
        
    def undo(self):
        dispatcher.changes.emit(events.SingleElementChangeEvent(self.level, self.before))


class ChangeMajorFlagCommand(ChangeSingleElementCommand):
    """A command to toggle the 'major' flag of a single element."""
    def __init__(self, level, element, text = translate(__name__, 'toggle major flag')):
        QtGui.QUndoCommand.__init__(self, text)
        self.level = level
        self.newMajor = not element.major
        self.id = element.id
        
    def redo(self):
        if self.level == REAL:
            real.setMajor(self.id, self.newMajor, emitEvent = False)
        dispatcher.changes.emit(events.MajorFlagChangeEvent(self.level, self.id, self.newMajor))
        self.newMajor = not self.newMajor
    
    undo = redo
    
class PositionChangeCommand(UndoCommand):
    """An undo command for changing positions of elements below one single parent."""
    
    def __init__(self, level, parentId, positionChanges, text = ''):
        """Initialize the PositionChangeCommand. *positionChanges* is a list of tuples
        mapping old to new positions."""
        QtGui.QUndoCommand.__init__(self, text)
        self.level = level
        self.parentId = parentId
        self.positionChanges = positionChanges
        
    def redo(self):
        if self.level == REAL:
            real.changePositions(self.parentId, self.positionChanges)
        else:
            dispatcher.changes.emit(events.PositionChangeEvent(self.level, self.parentId, 
                                                           dict(self.positionChanges)))
    
    def undo(self):
        if self.level == REAL:
            real.changePositions(self.parentId, [ (b,a) for a,b in self.positionChanges ])
        else:
            dispatcher.changes.emit(events.PositionChangeEvent(self.level, self.parentId,
                                                           dict(map(reversed,self.positionChanges))))
        
        
class InsertElementsCommand(UndoCommand):
    """A specialized command to insert elements into an existing container."""
    
    def __init__(self, level, insertions, text=''):
        """Create the command. *insertions* is a dict mapping parent ID to pairs
        (position, insertedElement). If the node given by parent ID is a container,
        position == insertedElement.position should hold. If the parent is a RootNode,
        then position is interpreted as the index at which the container is to be inserted."""
        QtGui.QUndoCommand.__init__(self, text)
        for v in insertions.values():
            assert len(v) > 0
        self.level = level
        self.insertions = insertions
    
    def redo(self):
        if self.level == REAL:
            real.addContents(self.insertions)
        else:
            dispatcher.changes.emit(events.InsertContentsEvent(self.level, self.insertions))
        
    def undo(self):
        if self.level == REAL:
            real.removeContents({parent:list(zip(*pairs))[0] for (parent,pairs) in self.insertions.items() })
        else:
            dispatcher.changes.emit(events.RemoveContentsEvent(EDITOR,
                                      {parent:list(zip(*pairs))[0] for parent,pairs in self.insertions.items() }))


class RemoveElementsCommand(UndoCommand):
    """A specialized undo command for the removal of elements. There are three types of removals:
    - DISK: delete the file corresponding to an element on disk,
    - DB: remove an element from the database,
    - CONTENTS: remove the "is-child-of" relation between an element and its parent.
    In EDITOR mode, the latter is the only valid remove operation. The operations above are ordered
    in such a way that any of them implies all of those below (e.g., if a file is deleted on the disk,
    it is automatically removed from the database and all parents)."""
    
    
    
    def __init__(self, level, elements, mode = CONTENTS, text=''):
        """Creates the remove command. Elements must be an iterable of Element objects, mode
        one of DISK, DB, CONTENTS (see the class doc for details).
        
        NOTE: It is probably a good idea to clear undo stacks after removing files from disk. An undo will
        restore the database to the state it had before the deletion, but the files are lost forever."""
        QtGui.QUndoCommand.__init__(self, text)
        
        if level == EDITOR and mode != CONTENTS:
            logger.error('cannot remove in mode other than CONTENTS in EDITOR mode -- please fix.')
            mode = CONTENTS
        self.mode = mode
        self.level = level
        assert len(elements) > 0
        
        self.changes = {}
        self.elementPool = {}
        # need to get, for each element, _all_ containers containing that element, in order to
        # be able to restore the content relations on undo.
        for element in elements:
            if not element.id in self.elementPool:
                self.elementPool[element.id] = element.copy()
            if mode == CONTENTS:
                parentIDs = (element.parent.id,)
            else:
                parentIDs = db.parents(element.id)
            
            for parentID in parentIDs:
                if parentID not in self.changes:
                    self.changes[parentID] = set()
                if mode == CONTENTS:
                    positions = (element.iPosition(),)
                else:
                    positions = db.positions(parentID, element.id)
                for position in positions:
                    self.changes[parentID].add( (position, element.id) )
        self.positionOnlyChanges = {parent:tuple(zip(*tup))[0] for parent,tup in self.changes.items()}
    
    def redo(self):
        if self.level == REAL:
            if self.mode == CONTENTS:
                real.removeContents(self.positionOnlyChanges)
            else:
                paths = [f.path for f in self.elementPool.values() if f.isFile() ]
                real.deleteElements(list(self.elementPool.keys()))
                if self.mode == DISK:
                    real.deleteFilesFromDisk(paths)
                if len(paths) > 0:
                    dispatcher.changes.emit(events.FilesRemovedEvent(paths, self.mode == DISK))
        else:
            dispatcher.changes.emit(events.RemoveContentsEvent(self.level, self.positionOnlyChanges))
    
    def undo(self):
        elementChanges = {}
        for parent, values in self.changes.items():
            changeList = elementChanges[parent] = []
            for position, elementID in values:
                changeList.append((position, self.elementPool[elementID]))
        if self.level == REAL:
            #Reinsert the elements. First we create them, then handle content relations.
            if self.mode == DB:
                real.createNewElements(list(self.elementPool.values()))
            real.addContents(elementChanges)
        else:
            dispatcher.changes.emit(events.InsertContentsEvent(EDITOR, elementChanges))

        
class CreateContainerCommand(UndoCommand):
    """A specialized command to create a single container in the database with the given
    attributes, but without any content relations."""
    
    def __init__(self, tags = None, flags = None, major = True, text = translate(__name__, 'create container')):
        QtGui.QUndoCommand.__init__(self, text)
        self.tags = tags if tags else tagsModule.Storage()
        self.flags = flags if flags else []
        self.major = major
        self.id = None
        
    def redo(self):
        self.id = real.newContainer(self.tags, self.flags, self.major, self.id)
        
    def undo(self):
        real.deleteElements([self.id])


class TagFlagUndoCommand(UndoCommand):
    """An UndoCommand that changes only tags and/or flags. The dicts *tagChanges* and *flagChanges* map
    ids to tuples: the tags (tags.Storage) or flags (list) before and after the change. On level REAL
    the parameter *elements* must be a list of affected elements."""
    def __init__(self,level,tagChanges,flagChanges,elements=None,text = ''):
        QtGui.QUndoCommand.__init__(self)
        self.level  = level
        self.tagChanges = tagChanges
        self.flagChanges = flagChanges
        self.contentsChanged = False
        self.setText("Tags/Flags changed")
        if level == REAL:
            self.elements = [el.export(attributes=['path']) for el in elements]
        
    def redo(self):
        if self.level == REAL:
            real.changeTags(self.tagChanges,self.elements,emitEvent=False)
            real.changeFlags(self.flagChanges,emitEvent=False)
        # Emit an event
        new = {id: (tags[1],None) for id,tags in self.tagChanges.items()}
        for id,flags in self.flagChanges.items():
            if id in new:
                new[id] = (new[id][0],flags[1]) # Set the None part of the tuple above to the new flags
            else: new[id] = (None,flags)
        dispatcher.changes.emit(events.TagFlagChangeEvent(self.level,new))

    def undo(self):
        if self.level == REAL:
            real.changeTags({k: (v[1],v[0]) for k,v in self.tagChanges.items()},self.elements,emitEvent=False)
            real.changeFlags({k: (v[1],v[0]) for k,v in self.flagChanges.items()},emitEvent=False)
        # Emit an event
        new = {id: (tags[0],None) for id,tags in self.tagChanges.items()}
        for id,flags in self.flagChanges.items():
            if id in new:
                new[id] = (new[id][0],flags[0]) # Set the None part of the tuple above to the old flags
            else: new[id] = (None,flags)
        dispatcher.changes.emit(events.TagFlagChangeEvent(self.level,new))
         
            
class SortValueUndoCommand(UndoCommand):
    """An UndoCommand that changes the sort value of a tag value."""
    def __init__(self, tag, valueId, oldSort = -1, newSort = None, text = translate('modify.commands','change sort value')):
        QtGui.QUndoCommand.__init__(self,text)
        self.tag = tag
        self.valueId = valueId
        self.oldSort = oldSort
        self.newSort = newSort
        
    def redo(self):
        real.setSortValue(self.tag,self.valueId,self.newSort,self.oldSort)
        
    def undo(self):
        real.setSortValue(self.tag,self.valueId,self.oldSort,self.newSort)


class ValueHiddenUndoCommand(UndoCommand):
    """An UndoCommand to change the "hidden" attribute of a tag value."""
    def __init__(self, tag, valueId, newState = None, text = translate('modify.commands', 'change hidden flag')):
        """Create the command. If newState is None, then the old one will be fetched from the database
        and the new one set to its negative.
        Otherwise, this class assumes that the current state is (not newState), so don't call this
        whith newState = oldState."""
        QtGui.QUndoCommand.__init__(self, text)
        self.tag = tag
        self.valueId = valueId
        self.newState = db.hidden(tag, valueId) if newState is None else newState
        
    def redo(self):
        real.setHidden(self.tag, self.valueId, self.newState)
    
    def undo(self):
        real.setHidden(self.tag, self.valueId, not self.newState)      


class RenameTagValueCommand(UndoCommand):
    """A command to rename *all* occurences of a specific tag value, e.g. all "Frederic Chopin" to
    "Frédéric Chopin"."""
    def __init__(self, tag, oldValue, newValue, text = None):
        QtGui.QUndoCommand.__init__(self)
        if text is None:
            text = translate('modify.commands', 'change {}-tag value from {} to {}'.format(tag, oldValue, newValue))
        self.setText(text)
        self.valueId = db.idFromValue(tag, oldValue)
        self.oldValue = oldValue
        self.newValue = newValue
        self.tag = tag
        # store elements that will be changed
        changedIDs = set(db.elementsWithTagValue(tag, self.valueId))
        
        # store elements that already have the new value
        try:
            existingIDs = set(db.elementsWithTagValue(tag, newValue))
        except db.sql.EmptyResultException:
            existingIDs = set()
        
        self.both = changedIDs & existingIDs
        self.changeSimple = changedIDs - self.both
    
    def redo(self):
        real.changeTagValue(self.tag, self.oldValue, self.newValue, self.changeSimple | self.both)
        
    def undo(self):
        real.changeTagValue(self.tag, self.newValue, self.oldValue, self.changeSimple)
        if len(self.both) > 0:
            real.addTagValue(self.tag, self.oldValue, self.both)
            



class CoverUndoCommand(UndoCommand):
    """Change a cover of a single element."""
    def __init__(self,id,pixmap, text = translate(__name__, 'change cover')):
        super().__init__(REAL,{}, text = text)
        self.id = id
        self.newPixmap = pixmap
        from .. import covers
        if covers.hasCover(id):
            self.oldPixmap = covers.getCover(id)
        else: self.oldPixmap = None
        
    def redo(self):
        from .. import covers
        if not covers.saveCover(self.id,self.newPixmap):
            QtGui.QMessageBox(QtGui.QMessageBox.Warning,self.tr("Saving cover failed"),
                              self.tr("The cover could not be saved."),
                              QtGui.QMessageBox.Ok).exec_()
        
    def undo(self):
        from .. import covers
        if not covers.saveCover(self.id,self.oldPixmap):
            QtGui.QMessageBox(QtGui.QMessageBox.Warning,self.tr("Saving cover failed"),
                              self.tr("The cover could not be saved."),
                              QtGui.QMessageBox.Ok).exec_()
            
        
def merge(level, parent, indices, newTitle, removeString, adjustPositions):
    """Merge creates a new container between *parent* and the children at the given *indices*.
    Those child elements will be removed from *parent* and instead inserted as children of
    the new container at indices[0]. The new container will contain all tags that are equal in
    all of its new children; its TITLE tag will be set to *newTitle*.
    
    removeString defines what to remove from the titles of the elements that are moved below the
    new container; this will usually be similar to *newTitle* plus possibly some punctutaion.
    If *adjustPositions* is True, the positions of items that are *not* removed are decreased
    to fill the gaps arising from moved elements.
    Example: Consider the following setting of an album containing a Sonata: 
    
    * parent
    |- pos1: child0 (title = Sonata Nr. 5: Allegro)
    |- pos2: child1 (tilte = Sonata Nr. 5: Adagio)
    |- pos3: child2 (title = Sonata Nr. 5: Finale. Presto)
    |- pos4: child3 (title = Nocturne Op. 13/37)
    |- pos5: child4 (title = Prelude BWV 42)
    
    After a call to merge with *indices=(0,1,2)*, *newTitle='Sonata Nr. 5'*, *removeString='Sonata Nr. 5: '*,
    *adjustPositions = True* the layout would be:
    
    * parent
    |- * pos1: new container (title = Sonata Nr. 5)
       |- pos1: child0 (title = Allegro)
       |- pos2: child1 (title = Adagio)
       |- pos3: child2 (title = Finale. Presto)
    |- pos2: child3 (title = Nocturne Op. 13/37)
    |- pos3: child4 (title = Prelude BWV 42)
    """ 
    from ..models import Container, Element, RootNode

    logger.debug("starting merge\n  on parent {}\n  indices {}".format(parent, indices))
    modify.beginMacro(level, translate(__name__, 'merge elements'))
    
    insertIndex = indices[0]
    insertPosition = parent.contents[insertIndex].iPosition()
    newContainerPosition = insertPosition if isinstance(parent, Element) else None
    newChildren = []
    toRemove = []    
    positionChanges = []
    
    for i, element in enumerate(parent.contents[insertIndex:], start = insertIndex):
        if i in indices:
            copy = parent.contents[i].copy()
            if tagsModule.TITLE in copy.tags:
                copy.tags[tagsModule.TITLE] = [ t.replace(removeString, '') for t in copy.tags[tagsModule.TITLE] ]
            copy.position = len(newChildren) + 1
            newChildren.append(copy)
            toRemove.append(parent.contents[i])
        elif adjustPositions:# or isinstance(parent, RootNode):
            positionChanges.append( (element.iPosition(), element.iPosition() - len(newChildren) + 1) )
    modify.push(RemoveElementsCommand(level, toRemove, mode = CONTENTS))
    if len(positionChanges) > 0:
        modify.push(PositionChangeCommand(level, parent.id, positionChanges))
    t = tagsModule.findCommonTags(newChildren, True)
    t[tagsModule.TITLE] = [newTitle]
    if level == EDITOR:
        newContainer = Container(id = modify.newEditorId(),
                                 contents = newChildren,
                                 tags = t,
                                 flags = [],
                                 position = newContainerPosition,
                                 major = False)
    else:
        createCommand = CreateContainerCommand(t, None, False)
        modify.push(createCommand)
        newContainer = Container.fromId(createCommand.id, loadData = True, position = newContainerPosition)

    insertions = { parent.id : [(insertPosition, newContainer)] }
    if level == REAL:
        insertions[newContainer.id] = [ (elem.position, elem) for elem in newChildren ]
    modify.push(InsertElementsCommand(level, insertions))
    modify.endMacro()

def flatten(level, elements, recursive):
    """Flatten out the given elements, i.e. remove them and put their children at their previous
    place. If *recursive* is *True*, the same will be done for all children, so that we end
    up with a flat list of files."""
    if len(elements) > 1:
        modify.beginMacro(level, translate(__name__, 'Flatten several containers'))
    for element in elements:
        if element.isContainer():
            flattenSingle(level, element, recursive)
    if len(elements) > 1:
        modify.endMacro()
        
def flattenSingle(level, element, recursive):
    """helper function to flatten a single container."""
    parent = element.parent
    position = element.iPosition()
    index = parent.index(element)

    if recursive:
        children = element.getAllFiles()
    else:
        children = element.contents
    modify.beginMacro(level, 'flatten container')
    if index < len(parent.contents) - 1:
        # need to ajust positions of elements behind
        nextPosition = parent.contents[index+1].iPosition()
        if nextPosition < position + len(children):
            shift = position + len(children) - nextPosition
            changes = []
            for elem in parent.contents[index+1:]:
                changes.append( (elem.iPosition(), elem.iPosition()+shift))
            modify.push(PositionChangeCommand(level, parent.id, changes))
    insertions = []
    for child in children:
        childCopy = child.copy()
        if isinstance(parent, models.Element): 
            childCopy.position = position
        insertions.append( (position, childCopy))
        position += 1
        
    modify.push(RemoveElementsCommand(level, [element], DB if level == REAL else CONTENTS))
    modify.push(InsertElementsCommand(level, {parent.id: insertions}))
    modify.endMacro()
