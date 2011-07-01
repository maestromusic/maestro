

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from collections import OrderedDict
import copy

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
    """A specialized modify event for the insertion of elements."""
    def __init__(self, level, insertions):
        self.insertions = insertions
        self.level = level
        self.contentsChanged = True
        
    def ids(self):
        return self.insertions.keys()
    
    def getNewContentsCount(self, element):
        return element.getContentsCount() + len(self.insertions[element.id])
    
    def applyTo(self, element):
        for i, elem in sorted(self.insertions[element.id]):
            elem2 = elem.copy()
            element.contents.insert(i, elem2)
            elem2.setParent(element)

class RemoveElementsEvent(ModifyEvent):
    """A specialized modify event for the removal of elements."""
    def __init__(self, level, removals):
        self.removals = removals
        self.level = level
        self.contentsChanged = True
        
    def ids(self):
        return self.removals.keys()
    
    def getNewContentsCount(self, element):
        return element.getContentsCount() + len(self.removals[element.id])
    
    def applyTo(self, element):
        for index in sorted(self.removals[element.id], reverse = True):
            del element.contents[index]
            
         
class ChangeEventDispatcher(QtCore.QObject):
    
    changes = QtCore.pyqtSignal(ModifyEvent)
    
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

class ModifySingleElementUndoCommand(UndoCommand):
    """A specialized undo command for the modification of a single element (tags, position, ..., but no 
    contents)."""
    
    def __init__(self, level, before, after, text=''):
        QtGui.QUndoCommand.__init__(self)
        self.level = level
        self.before = before
        self.after = after
        self.setText(text)
    
    def redo(self):
        dispatcher.changes.emit(ModifySingleElementEvent(self.level, self.after))
    def undo(self):
        dispatcher.changes.emit(ModifySingleElementEvent(self.level, self.before))
        
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
        self.changes = {}
        self.elementPool = {}
        for elem in elements:
            parent = elem.parent
            if parent.id not in self.changes:
                self.changes[parent.id] = set()
            self.changes[parent.id].add((parent.index(elem), elem.id))
            self.elementPool[elem.id] = elem.copy()
            
    def redo(self):
        dispatcher.changes.emit(RemoveElementsEvent(
             self.level, dict((pid, [tup[0] for tup in elemSet]) for pid,elemSet in self.changes.items())))
    
    def undo(self):
        dispatcher.changes.emit(InsertElementsEvent(
             self.level, dict((pid, [ (tup[0], self.elementPool[tup[1]]) for tup in elemSet ] ) for pid, elemSet in self.changes.items())))
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