

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import tags

from collections import OrderedDict
import copy
translate = QtCore.QCoreApplication.translate

REAL = 1
EDITOR = 2

class ModifyEvent:
    """A generic modify event for all sorts of modifications."""
    def __init__(self, level, changes, contentsChanged = False):
        self.changes = changes
        self.level = level
        self.contentsChanged = contentsChanged
    
    def ids(self):
        return self.changes.keys()
    
    def getNewContentsCount(self, element):
        return self.changes[element.id].getContentsCount()
    
    def applyTo(self, element):
        element.copyFrom(self.changes[element.id], copyContents = self.contentsChanged)

class ModifySingleElementEvent(ModifyEvent):
    """A specialized modify event if only one element (tags, position, ...) is modified."""
    def __init__(self, level, element):
        self.element = element
        self.level = level
        self.contentsChanged = False
        
    def ids(self):
        return self.element.id,
    
    def getNewContentsCount(self, element):
        return 0
    
    def applyTo(self, element):
        element.copyFrom(self.element, copyContents = False)

class InsertElementsEvent(ModifyEvent):
    """A specialized modify event for the insertion of elements. <insertions> is a dict mapping parentId -> iterable of
    (position, elementList) tuples."""
    def __init__(self, level, insertions):
        self.insertions = insertions
        self.level = level
        self.contentsChanged = True
        
    def ids(self):
        return self.insertions.keys()
    
    def getNewContentsCount(self, element):
        return element.getContentsCount() + sum(map(len, tup[1]) for tup in self.insertions[element.id])
    
    def applyTo(self, element):
        for i, elems in self.insertions[element.id]:
            element.insertContents(i, [e.copy() for e in elems])
            

class RemoveElementsEvent(ModifyEvent):
    """A specialized modify event for the removal of elements. Removals is a dict mapping parent ids to an iterable of
    (position, number) tuples, meaning that parent.contents[position,position+number] will be removed. The caller must
    make sure that it is feasable to remove elements in the order they appear in the iterable – i.e. they should be sorted
    decreasing."""
    def __init__(self, level, removals):
        self.removals = removals
        self.level = level
        self.contentsChanged = True
        
    def ids(self):
        return self.removals.keys()
    
    def getNewContentsCount(self, element):
        return element.getContentsCount() - sum(tup[1] for tup in self.removals[element.id])
    
    def applyTo(self, element):
        for index, count in self.removals[element.id]:
            del element.contents[index:index+count]
            
         
class ChangeEventDispatcher(QtCore.QObject):
    
    changes = QtCore.pyqtSignal(ModifyEvent)
    newTagAdded = QtCore.pyqtSignal(tags.Tag)
    
    def __init__(self):
        QtCore.QObject.__init__(self)

dispatcher = ChangeEventDispatcher()

class UndoCommand(QtGui.QUndoCommand):
    """A generic undo command for arbitrary changes. The constructor gets an OrderedDict mapping
    ids to a tuple, specifying the state of that element before and after the change, respectively.
    
    Whenever possible, use specialized undo commands (or create own subclasses) below which allow for
    a more efficient implementation and widget notification."""
    
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
        newChanges = OrderedDict(( (k,v[1]) for k,v in self.changes.items() ))
        redoEvent = ModifyEvent(self.level, newChanges, contentsChanged = self.contentsChanged)
        dispatcher.changes.emit(redoEvent)

    def undo(self):
        newChanges = OrderedDict(( (k,v[0]) for k,v in self.changes.items() ))
        redoEvent = ModifyEvent(self.level, newChanges, contentsChanged = self.contentsChanged)
        dispatcher.changes.emit(redoEvent)

class ModifySingleElementCommand(UndoCommand):
    """A specialized undo command for the modification of a single element (tags, position, ..., but no 
    contents)."""
    
    def __init__(self, level, before, after, text=''):
        QtGui.QUndoCommand.__init__(self)
        self.level = level
        self.before = before.copy()
        self.after = after.copy()
        self.setText(text)
    
    def redo(self):
        dispatcher.changes.emit(ModifySingleElementEvent(self.level, self.after))
    def undo(self):
        dispatcher.changes.emit(ModifySingleElementEvent(self.level, self.before))

def createRanges(tuples):
        previous = None
        start = None
        elements = []
        for i, elem in sorted(tuples):
            if previous is None:
                previous = start = i
            if i > previous + 1:
                # emit previous range
                yield start, elements
                start = i
                elements = []
            previous = i
            elements.append(elem)
        yield start, elements
class RemoveElementsCommand(UndoCommand):
    """A specialized undo command for the removal of elements."""
    
    def __init__(self, level, elements, text=''):
        """Creates the remove command. Elements must be an iterable of Element objects.
        
        The constructor checks for redundancies in the list (e.g., if an item and its parent
        are both in the list, then the item itself is redundant)."""
        QtGui.QUndoCommand.__init__(self)
        self.level = level
        if len(elements) == 0:
            return
        for i in reversed(elements):
            for p in i.getParents():
                if p in elements:
                    elements.remove(i)
        changes = {} # map of parent id -> set of (index, elementId) tuples
        self.elementPool = {}
        for elem in elements:
            parent = elem.parent
            if parent.id not in changes:
                changes[parent.id] = set()
            changes[parent.id].add((parent.index(elem), elem.id))
            self.elementPool[elem.id] = elem.copy()
        # now create index ranges from the unordered sets
        self.removals = {}
        for parentId, changeSet in changes.items():
            self.removals[parentId] = []
            for tuple in createRanges(changeSet):
                self.removals[parentId].append( tuple )
                 
    def redo(self):
        dispatcher.changes.emit(RemoveElementsEvent(
             self.level, dict((pid, [ ( tup[0], len(tup[1]) ) for tup in reversed(elemSet)]) for pid,elemSet in self.removals.items())))
    
    def undo(self):
        dispatcher.changes.emit(InsertElementsEvent(
             self.level, dict((pid, [ (tup[0], [self.elementPool[i] for i in tup[1]]) for tup in elemSet ] ) for pid, elemSet in self.removals.items())))

class InsertElementsCommand(UndoCommand):
    def __init__(self, level, insertions, text=''):
        super().__init__(level, insertions, text)
        self.level = level
        self.insertions = insertions
    
    def redo(self):
        dispatcher.changes.emit(InsertElementsEvent(
              self.level, self.insertions))
    def undo(self):
        dispatcher.changes.emit(RemoveElementsEvent(
              self.level, dict((pid, [ (tup[0], len(tup[1]) ) for tup in reversed(elemSet)]) for pid,elemSet in self.insertions.items())))
    
def changePosition(level, element, position):
    elemOld = element.copy()
    elemNew = element.copy()
    elemNew.position = position
    
    stack.activeStack().push(ModifySingleElementCommand(level, elemOld, elemNew, translate('modify', 'change position'))) # TODO: richtigen Stack auswählen        
    
def merge(level, parent, positions, newTitle, removeString, adjustPositions):
    from ..models import Container
    if level == REAL:
        raise NotImplementedError('Maddin, tu was!')
    if stack.state() == REAL:
        stack.setActiveStack(stack.editorStack)

    stack.editorStack.beginMacro(translate('modify', 'merge elements'))
    copies = []
    insertPosition = positions[0]
    insertElementPosition = parent.contents[insertPosition].position
    print(parent)
    removeCommand = RemoveElementsCommand(EDITOR, [parent.contents[i] for i in positions])
    
    for i,element in enumerate(parent.contents[insertPosition:], start=insertPosition):
        if i in positions:
            elemC = parent.contents[i].copy()
            copies.append(elemC)
            elemC.position = len(copies)
            if tags.TITLE in elemC.tags:
                elemC.tags[tags.TITLE] = [ t.replace(removeString, '') for t in elemC.tags[tags.TITLE] ]
            pushEditorCommand(ModifySingleElementCommand(EDITOR, element, elemC))
        elif adjustPositions:
            changePosition(EDITOR, element, element.position - len(copies) + 1)
    pushEditorCommand(removeCommand)        
    t = tags.findCommonTags(copies, True)
    t[tags.TITLE] = [newTitle]
    newContainer = Container(id = newEditorId(), contents = copies, tags = t, position = insertElementPosition)
    insertions = { parent.id : [(insertPosition, [newContainer])] }
    pushEditorCommand(InsertElementsCommand(EDITOR, insertions))
    stack.editorStack.endMacro()
    

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


class UndoGroup(QtGui.QUndoGroup):
    def __init__(self, parent = None):
        QtGui.QUndoGroup.__init__(self, parent)
        
        self.mainStack = QtGui.QUndoStack()
        
        self.addStack(self.mainStack)
        self.editorStack = None
        
        self._createEditorStack()
        self.setActiveStack(self.mainStack)
        
    def state(self):
        if self.activeStack() is self.editorStack:
            return EDITOR
        else:
            return REAL

    def _createEditorStack(self):
        if self.editorStack is not None:
            self.removeStack(self.editorStack)
        self.editorStack = QtGui.QUndoStack()
        #self.editorStack.indexChanged.connect(self._editorIndexChanged)
        self.addStack(self.editorStack)

    def _editorIndexChanged(self, index):
        if index == 0:
            self.setActiveStack(self.mainStack)
        else:
            self.setActiveStack(self.editorStack)
    
    def clearEditorStack(self):
        self._createEditorStack()
        self.setActiveStack(self.mainStack)
        
stack = UndoGroup()
def pushEditorCommand(command):
    if stack.state() == REAL:
        stack.setActiveStack(stack.editorStack)
    stack.activeStack().push(command)
    
def beginEditorMacro(name):
    if stack.state() == REAL:
        stack.setActiveStack(stack.editorStack)
    stack.activeStack().beginMacro(name)
    
def endEditorMacro():
    assert stack.state() == EDITOR
    stack.editorStack.endMacro()

def createUndoAction(level,parent,prefix):
    if level == REAL:
        return stack.editorStack.createUndoAction(parent,prefix)
    else: return stack.mainStack.createUndoAction(parent,prefix)

def createRedoAction(level,parent,prefix):
    if level == REAL:
        return stack.editorStack.createRedoAction(parent,prefix)
    else: return stack.mainStack.createRedoAction(parent,prefix)
    