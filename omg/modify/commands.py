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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import logging
from ..models import levels
from . import ElementChangeCommand

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

"""This modules contains a list of often needed ElementChangeCommand subclasses for special purposes."""
        
class InsertElementsCommand(ElementChangeCommand):
    """A specialized command to insert elements into an existing container."""
    
    def __init__(self, level, parentId, row, insertedIds, text='insert elements'):
        """Create the command for given *level* inserting elements into *parentId*
        at row index *row*. *insertedIds* is the IDs list of the elements to be inserted.
        Positions are inferred from the context, and positions of subsequent elements
        will be adjusted if necessary."""
        super().__init__(level = level, ids = [parentId], contents = True, text = text)
        self.row = row
        self.oldContents = level.get(parentId).contents.copy()
        newContents = self.oldContents.copy()
        firstPosition = 1 if row == 0 else newContents[row-1][0] 
        newContents.ids[row:row] = insertedIds
        newContents.positions[row:row] = range(firstPosition, firstPosition + len(insertedIds))
        # adjust subsequent positions
        for i in range(row+len(insertedIds), len(newContents.positions)):
            if newContents.positions[i] <= newContents.positions[i-1]:
                newContents.positions[i] = newContents.positions[i-1] + 1
        self.newContents = newContents
        
    def redoChanges(self):
        if self.level is levels.real:
            pass
        
    def undoChanges(self):
        if self.level is levels.real:
            pass



#class TagFlagUndoCommand(UndoCommand):
#    """An UndoCommand that changes only tags and/or flags. The dicts *tagChanges* and *flagChanges* map
#    ids to tuples: the tags (tags.Storage) or flags (list) before and after the change. On level REAL
#    the parameter *elements* must be a list of affected elements."""
#    def __init__(self,level,tagChanges,flagChanges,elements=None,text = ''):
#        QtGui.QUndoCommand.__init__(self)
#        self.level  = level
#        self.tagChanges = tagChanges
#        self.flagChanges = flagChanges
#        self.contentsChanged = False
#        self.setText("Tags/Flags changed")
#        if level == REAL:
#            self.elements = [el.export(attributes=['path']) for el in elements]
#        
#    def redo(self):
#        if self.level == REAL:
#            real.changeTags(self.tagChanges,self.elements,emitEvent=False)
#            real.changeFlags(self.flagChanges,emitEvent=False)
#        # Emit an event
#        new = {id: (tags[1],None) for id,tags in self.tagChanges.items()}
#        for id,flags in self.flagChanges.items():
#            if id in new:
#                new[id] = (new[id][0],flags[1]) # Set the None part of the tuple above to the new flags
#            else: new[id] = (None,flags)
#        dispatcher.changes.emit(events.TagFlagChangeEvent(self.level,new))
#
#    def undo(self):
#        if self.level == REAL:
#            real.changeTags({k: (v[1],v[0]) for k,v in self.tagChanges.items()},self.elements,emitEvent=False)
#            real.changeFlags({k: (v[1],v[0]) for k,v in self.flagChanges.items()},emitEvent=False)
#        # Emit an event
#        new = {id: (tags[0],None) for id,tags in self.tagChanges.items()}
#        for id,flags in self.flagChanges.items():
#            if id in new:
#                new[id] = (new[id][0],flags[0]) # Set the None part of the tuple above to the old flags
#            else: new[id] = (None,flags)
#        dispatcher.changes.emit(events.TagFlagChangeEvent(self.level,new))
#         
#            
#class SortValueUndoCommand(UndoCommand):
#    """An UndoCommand that changes the sort value of a tag value."""
#    def __init__(self, tag, valueId, oldSort = -1, newSort = None, text = translate('modify.commands','change sort value')):
#        QtGui.QUndoCommand.__init__(self,text)
#        self.tag = tag
#        self.valueId = valueId
#        self.oldSort = oldSort
#        self.newSort = newSort
#        
#    def redo(self):
#        real.setSortValue(self.tag,self.valueId,self.newSort,self.oldSort)
#        
#    def undo(self):
#        real.setSortValue(self.tag,self.valueId,self.oldSort,self.newSort)
#
#
#class ValueHiddenUndoCommand(UndoCommand):
#    """An UndoCommand to change the "hidden" attribute of a tag value."""
#    def __init__(self, tag, valueId, newState = None, text = translate('modify.commands', 'change hidden flag')):
#        """Create the command. If newState is None, then the old one will be fetched from the database
#        and the new one set to its negative.
#        Otherwise, this class assumes that the current state is (not newState), so don't call this
#        whith newState = oldState."""
#        QtGui.QUndoCommand.__init__(self, text)
#        self.tag = tag
#        self.valueId = valueId
#        self.newState = db.hidden(tag, valueId) if newState is None else newState
#        
#    def redo(self):
#        real.setHidden(self.tag, self.valueId, self.newState)
#    
#    def undo(self):
#        real.setHidden(self.tag, self.valueId, not self.newState)      
#
#
#class RenameTagValueCommand(UndoCommand):
#    """A command to rename *all* occurences of a specific tag value, e.g. all "Frederic Chopin" to
#    "Frédéric Chopin"."""
#    def __init__(self, tag, oldValue, newValue, text = None):
#        QtGui.QUndoCommand.__init__(self)
#        if text is None:
#            text = translate('modify.commands', 'change {}-tag value from {} to {}'.format(tag, oldValue, newValue))
#        self.setText(text)
#        self.valueId = db.idFromValue(tag, oldValue)
#        self.oldValue = oldValue
#        self.newValue = newValue
#        self.tag = tag
#        # store elements that will be changed
#        changedIDs = set(db.elementsWithTagValue(tag, self.valueId))
#        
#        # store elements that already have the new value
#        try:
#            existingIDs = set(db.elementsWithTagValue(tag, newValue))
#        except db.sql.EmptyResultException:
#            existingIDs = set()
#        
#        self.both = changedIDs & existingIDs
#        self.changeSimple = changedIDs - self.both
#    
#    def redo(self):
#        real.changeTagValue(self.tag, self.oldValue, self.newValue, self.changeSimple | self.both)
#        
#    def undo(self):
#        real.changeTagValue(self.tag, self.newValue, self.oldValue, self.changeSimple)
#        if len(self.both) > 0:
#            real.addTagValue(self.tag, self.oldValue, self.both)
#            
#
#
#
#class CoverUndoCommand(UndoCommand):
#    """Change a cover of a single element."""
#    def __init__(self,id,pixmap, text = translate(__name__, 'change cover')):
#        super().__init__(REAL,{}, text = text)
#        self.id = id
#        self.newPixmap = pixmap
#        from .. import covers
#        if covers.hasCover(id):
#            self.oldPixmap = covers.getCover(id)
#        else: self.oldPixmap = None
#        
#    def redo(self):
#        from .. import covers
#        if not covers.saveCover(self.id,self.newPixmap):
#            QtGui.QMessageBox(QtGui.QMessageBox.Warning,self.tr("Saving cover failed"),
#                              self.tr("The cover could not be saved."),
#                              QtGui.QMessageBox.Ok).exec_()
#        
#    def undo(self):
#        from .. import covers
#        if not covers.saveCover(self.id,self.oldPixmap):
#            QtGui.QMessageBox(QtGui.QMessageBox.Warning,self.tr("Saving cover failed"),
#                              self.tr("The cover could not be saved."),
#                              QtGui.QMessageBox.Ok).exec_()
#            
#        
#def merge(level, parent, indices, newTitle, removeString, adjustPositions):
#    """Merge creates a new container between *parent* and the children at the given *indices*.
#    Those child elements will be removed from *parent* and instead inserted as children of
#    the new container at indices[0]. The new container will contain all tags that are equal in
#    all of its new children; its TITLE tag will be set to *newTitle*.
#    
#    removeString defines what to remove from the titles of the elements that are moved below the
#    new container; this will usually be similar to *newTitle* plus possibly some punctutaion.
#    If *adjustPositions* is True, the positions of items that are *not* removed are decreased
#    to fill the gaps arising from moved elements.
#    Example: Consider the following setting of an album containing a Sonata: 
#    
#    * parent
#    |- pos1: child0 (title = Sonata Nr. 5: Allegro)
#    |- pos2: child1 (tilte = Sonata Nr. 5: Adagio)
#    |- pos3: child2 (title = Sonata Nr. 5: Finale. Presto)
#    |- pos4: child3 (title = Nocturne Op. 13/37)
#    |- pos5: child4 (title = Prelude BWV 42)
#    
#    After a call to merge with *indices=(0,1,2)*, *newTitle='Sonata Nr. 5'*, *removeString='Sonata Nr. 5: '*,
#    *adjustPositions = True* the layout would be:
#    
#    * parent
#    |- * pos1: new container (title = Sonata Nr. 5)
#       |- pos1: child0 (title = Allegro)
#       |- pos2: child1 (title = Adagio)
#       |- pos3: child2 (title = Finale. Presto)
#    |- pos2: child3 (title = Nocturne Op. 13/37)
#    |- pos3: child4 (title = Prelude BWV 42)
#    """ 
#    from ..models import Container, Element, RootNode
#
#    logger.debug("starting merge\n  on parent {}\n  indices {}".format(parent, indices))
#    modify.beginMacro(level, translate(__name__, 'merge elements'))
#    
#    insertIndex = indices[0]
#    insertPosition = parent.contents[insertIndex].iPosition()
#    newContainerPosition = insertPosition if isinstance(parent, Element) else None
#    newChildren = []
#    toRemove = []    
#    positionChanges = []
#    
#    for i, element in enumerate(parent.contents[insertIndex:], start = insertIndex):
#        if i in indices:
#            copy = parent.contents[i].copy()
#            if tagsModule.TITLE in copy.tags:
#                copy.tags[tagsModule.TITLE] = [ t.replace(removeString, '') for t in copy.tags[tagsModule.TITLE] ]
#            copy.position = len(newChildren) + 1
#            newChildren.append(copy)
#            toRemove.append(parent.contents[i])
#        elif adjustPositions:# or isinstance(parent, RootNode):
#            positionChanges.append( (element.iPosition(), element.iPosition() - len(newChildren) + 1) )
#    modify.push(RemoveElementsCommand(level, toRemove, mode = CONTENTS))
#    if len(positionChanges) > 0:
#        modify.push(PositionChangeCommand(level, parent.id, positionChanges))
#    t = tagsModule.findCommonTags(newChildren, True)
#    t[tagsModule.TITLE] = [newTitle]
#    if level == EDITOR:
#        newContainer = Container(id = modify.newEditorId(),
#                                 contents = newChildren,
#                                 tags = t,
#                                 flags = [],
#                                 position = newContainerPosition,
#                                 major = False)
#    else:
#        createCommand = CreateContainerCommand(t, None, False)
#        modify.push(createCommand)
#        newContainer = Container.fromId(createCommand.id, loadData = True, position = newContainerPosition)
#
#    insertions = { parent.id : [(insertPosition, newContainer)] }
#    if level == REAL:
#        insertions[newContainer.id] = [ (elem.position, elem) for elem in newChildren ]
#    modify.push(InsertElementsCommand(level, insertions))
#    modify.endMacro()
#
#def flatten(level, elements, recursive):
#    """Flatten out the given elements, i.e. remove them and put their children at their previous
#    place. If *recursive* is *True*, the same will be done for all children, so that we end
#    up with a flat list of files."""
#    if len(elements) > 1:
#        modify.beginMacro(level, translate(__name__, 'Flatten several containers'))
#    for element in elements:
#        if element.isContainer():
#            flattenSingle(level, element, recursive)
#    if len(elements) > 1:
#        modify.endMacro()
#        
#def flattenSingle(level, element, recursive):
#    """helper function to flatten a single container."""
#    parent = element.parent
#    position = element.iPosition()
#    index = parent.index(element)
#
#    if recursive:
#        children = element.getAllFiles()
#    else:
#        children = element.contents
#    modify.beginMacro(level, 'flatten container')
#    if index < len(parent.contents) - 1:
#        # need to ajust positions of elements behind
#        nextPosition = parent.contents[index+1].iPosition()
#        if nextPosition < position + len(children):
#            shift = position + len(children) - nextPosition
#            changes = []
#            for elem in parent.contents[index+1:]:
#                changes.append( (elem.iPosition(), elem.iPosition()+shift))
#            modify.push(PositionChangeCommand(level, parent.id, changes))
#    insertions = []
#    for child in children:
#        childCopy = child.copy()
#        if isinstance(parent, models.Element): 
#            childCopy.position = position
#        insertions.append( (position, childCopy))
#        position += 1
#        
#    modify.push(RemoveElementsCommand(level, [element], DB if level == REAL else CONTENTS))
#    modify.push(InsertElementsCommand(level, {parent.id: insertions}))
#    modify.endMacro()
