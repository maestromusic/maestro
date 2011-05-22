

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from collections import OrderedDict


REAL = 1
EDITOR = 2


class ChangeEvent:
    def __init__(self, level, changes, contentsChanged = False):
        """Creates a new ChangeEvent, which consists of a level (either REAL or EDITOR),
        an OrderedDict of ids->Elements, and a flag whether the contents of the elements
        have changed or not."""
        self.changes = changes
        self.level = level
        self.contentsChanged = contentsChanged
        
    def __str__(self):
        return "ChangeEvent:{}".format(self.changes)

class ChangeEventDispatcher(QtCore.QObject):
    
    changes = QtCore.pyqtSignal(ChangeEvent)
    
    def __init__(self):
        QtCore.QObject.__init__(self)
dispatcher = ChangeEventDispatcher()
class UndoCommand(QtGui.QUndoCommand):

    def __init__(self, level, changes, contentsChanged = False, text = ''):
        """Creates an UndoCommand, i.e. an object that stores what has changed in one
        step of database editing. 'changes' is an OrderedDict of ids to tuples of Elements:
        The state before and after the change."""
        QtGui.QUndoCommand.__init__(self)
        self.level  = level
        self.changes = changes
        self.contentsChanged = contentsChanged
        self.setText(text)
        
    def redo(self):
        newChanges = OrderedDict(( (k,v[1]) for k,v in self.changes.items() ))
        redoEvent = ChangeEvent(self.level, newChanges, contentsChanged = self.contentsChanged)
        dispatcher.changes.emit(redoEvent)

    def undo(self):
        newChanges = OrderedDict(( (k,v[0]) for k,v in self.changes.items() ))
        redoEvent = ChangeEvent(self.level, newChanges, contentsChanged = self.contentsChanged)
        dispatcher.changes.emit(redoEvent)

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
        self.editorStack.indexChanged.connect(self._editorIndexChanged)
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