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

from .. import tags, logging, database as db
from ..constants import REAL, EDITOR, CONTENTS
from . import events
# At the end of the file we will import the submodules real and events.

translate = QtCore.QCoreApplication.translate

logger = logging.getLogger(__name__)



# Type of a change
ADDED,CHANGED,DELETED = range(1,4)
    
            
         
def _debugAll(event):
    logger.debug("EVENT: " + str(event))

    
class ChangeEventDispatcher(QtCore.QObject):
    
    changes = QtCore.pyqtSignal(events.ChangeEvent)
    
    def __init__(self):
        QtCore.QObject.__init__(self)


dispatcher = ChangeEventDispatcher()
dispatcher.changes.connect(_debugAll)

stack = QtGui.QUndoStack()


def commitEditors():
    command = commands.CommitCommand()
    push(command)
             
    
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
    from ..models import Container, Element

    logger.debug("starting merge\n  on parent {}\n  indices {}".format(parent, indices))
    beginMacro(level, translate('modify', 'merge elements'))
    
    insertIndex = indices[0]
    insertPosition = parent.contents[insertIndex].iPosition()
    newContainerPosition = insertPosition if isinstance(parent, Element) else None
    newChildren = []
    toRemove = []    
    positionChanges = []
    
    for i, element in enumerate(parent.contents[insertIndex:], start = insertIndex):
        if i in indices:
            copy = parent.contents[i].copy()
            if tags.TITLE in copy.tags:
                copy.tags[tags.TITLE] = [ t.replace(removeString, '') for t in copy.tags[tags.TITLE] ]
            copy.position = len(newChildren) + 1
            newChildren.append(copy)
            toRemove.append(parent.contents[i])
        elif adjustPositions:
            positionChanges.append( (element.position, element.position - len(newChildren) + 1) )
    push(commands.RemoveElementsCommand(level, toRemove, mode = CONTENTS))
    if len(positionChanges) > 0:
        push(commands.PositionChangeCommand(level, parent.id, positionChanges))
    t = tags.findCommonTags(newChildren, True)
    t[tags.TITLE] = [newTitle]
    if level == EDITOR:
        newContainer = Container(id = newEditorId(),
                                 contents = newChildren,
                                 tags = t,
                                 flags = [],
                                 position = newContainerPosition,
                                 major = False)
    else:
        createCommand = commands.CreateContainerCommand(t, None, False)
        push(createCommand)
        newContainer = Container.fromId(createCommand.id, loadData = True, position = newContainerPosition)

    insertions = { parent.id : [(insertPosition, newContainer)] }
    if level == REAL:
        insertions[newContainer.id] = [ (elem.position, elem) for elem in newChildren ]
    push(commands.InsertElementsCommand(level, insertions))
    endMacro()
    

_currentEditorId = 0
_fileEditorIds = {}
# TODO: Liste wieder leeren?

def editorIdForPath(path):
    global _fileEditorIds
    if path not in _fileEditorIds:
        _fileEditorIds[path] = newEditorId()
    return _fileEditorIds[path]

def newEditorId():
    global _currentEditorId
    _currentEditorId -= 1
    return _currentEditorId


def beginMacro(level,name):
    stack.beginMacro(name)

def endMacro():
    stack.endMacro()

def push(command):
    stack.push(command)

def createUndoAction(level,parent,prefix):
    return stack.createUndoAction(parent,prefix)

def createRedoAction(level,parent,prefix):
    return stack.createRedoAction(parent,prefix)


# This is simply so that other modules can use modify.real.<stuff>
from . import real
