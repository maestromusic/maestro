# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

"""Improved QUndoStack."""

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import logging
logger = logging.getLogger(__name__)


class UndoStackError(RuntimeError):
    """This error is raised when methods of UndoStack are improperly used (e.g. call endMacro when no macro
    is built."""
    
           
class UndoStack(QtCore.QObject):
    """An UndoStack stores UndoCommands and provides undo/redo. It provides the same API as QUndoStack but
    improves it in several ways:
    
        - the attempt to modify the stack during undo/redo will lead to a RuntimeError,
        - while a macro is composed and during undo/redo, ChangeEventDispatcher won't emit events directly,
          but add them to an internal queue. When the macro is completed or undo/redo finished, all events
          will be emitted.
        - Events in the queue may be merged (see ChangeEvent.merge)
        - it is possible to abort a macro (similar to rollback in transactional DBs)
        - A substack is a proxy object that acts like the main stack but remembers which commands are pushed
          via the substack. When the substack is closed, all those commands are removed from the stack.
          This is necessary for modal dialogs.  
        
    """
    canRedoChanged = QtCore.pyqtSignal(bool)
    canUndoChanged = QtCore.pyqtSignal(bool)
    indexChanged = QtCore.pyqtSignal(int)
    redoTextChanged = QtCore.pyqtSignal(str)
    undoTextChanged = QtCore.pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._commands = []        # QUndoCommands on the stack
        self._index = 0            # Position before the command that will be executed on redo
        self._currentMacro = None  # macro while it is built.
        self._macroDepth = 0       # Number of open macros (# of beginMacro - # of endMacro)
        self._inUndoRedo = False   # True during undo and redo
        self._eventQueue = []      # list of tuples (dispatcher,event)
        self._substack = None      # the current substack
        self._undoAction = UndoRedoAction(self,redo=False)
        self._redoAction = UndoRedoAction(self,redo=True)
        
    def beginMacro(self,text):
        """Begin a macro. The macro will contain all commands that are pushed until endMacro is called.
        *text* will be used as command description in e.g. menu commands for undo/redo. Macros may be nested,
        the outermost macro will be redone/undone at once.
        """ 
        # Note that nested calls to beginMacro will not create more than one instance of Macro
        if self._inUndoRedo:
            raise UndoStackError("Cannot begin a macro during undo/redo.")
        self._macroDepth += 1
        if self._macroDepth == 1:
            assert self._currentMacro is None
            self._currentMacro = Macro(text)
        
    def push(self,command):
        """Add a command to the stack. This calls the command's redo-method."""
        if not isinstance(command,QtGui.QUndoCommand):
            raise TypeError("I push QUndoCommands, not {}: {}".format(type(command),command))
        if self._inUndoRedo:
            raise UndoStackError("Cannot push a command during undo/redo.")
        command.redo()
        if self._currentMacro is None:
            self._push(command)
            self._emitSignals()
        else: self._currentMacro.commands.append(command)
        
    def _push(self,command):
        """Helper for push and endMacro."""
        # Overwrite commands after self._index
        self._commands[self._index:] = [command]
        self._index += 1
        
    def endMacro(self):
        """Ends composition of a macro command."""
        if self._currentMacro is None:
            raise UndoStackError("Cannot end a macro when no macro is being built.")
        if self._inUndoRedo:
            raise UndoStackError("Cannot end a macro during undo/redo.")
        self._macroDepth -= 1
        if self._macroDepth == 0:
            assert self._currentMacro is not None
            self._push(self._currentMacro)
            self._emitSignals()
            self._emitQueuedEvents()
            self._currentMacro = None
    
    def abortMacro(self):
        """Abort the current macro: Undo all commands that have been added to it and delete the macro. This
        is better than endMacro+undo because it doesn't leave an unfinished macro on the stack."""
        if self._currentMacro is None:
            raise UndoStackError("Cannot abort macro, because no macro is being built.")
        if self._inUndoRedo:
            raise UndoStackError("Cannot end a macro during undo/redo.")
        self._currentMacro.undo()
        self._currentMacro = None
        self._macroDepth = 0
        
    def canUndo(self):
        """Returns whether there is a command that can be undone."""
        return self._index > 0 and (self._substack is None or self._index > self._substack.startIndex)
    
    def canRedo(self):
        """Returns whether there is a command that can be redone."""
        return self._index < len(self._commands)

    def createRedoAction(self):
        """Return a QAction that will trigger the redo-method and changes its state (enabled, name...)
        according to the stack's index."""
        return self._redoAction
    
    def createUndoAction(self):
        """Return a QAction that will trigger the undo-method and changes its state (enabled, name...)
        according to the stack's index."""
        return self._undoAction
    
    def clear(self):
        """Delete all commands on the stack."""
        logger.debug("**** MADDIN, TU WAS ****\n" * 10)
    
    def undo(self):
        """Undo the last command/macro."""
        if self._inUndoRedo or self._macroDepth > 0:
            raise UndoStackError("Cannot undo a command during undo/redo or while a macro is built.""")
        if self._index == 0 or (self._substack is not None and self._index == self._substack.startIndex):
            raise UndoStackError("There is no command to undo.")
        self._inUndoRedo = True
        commandOrMacro = self._commands[self._index-1]
        commandOrMacro.undo()
        self._index -= 1
        self._emitQueuedEvents()
        self._inUndoRedo = False
        self._emitSignals()
    
    def redo(self):
        """Redo the next command/macro."""
        if self._inUndoRedo or self._macroDepth > 0:
            raise UndoStackError("Cannot redo a command during undo/redo or while a macro is built.""")
        if self._index == len(self._commands):
            raise UndoStackError("There is no command to redo.")
        self._inUndoRedo = True
        commandOrMacro = self._commands[self._index]
        commandOrMacro.redo()
        self._index += 1
        self._emitQueuedEvents()
        self._inUndoRedo = False
        self._emitSignals()
    
    def setIndex(self,index):
        """Undo/redo commands until there are *index* commands left that can be undone."""
        if index != self._index:
            minIndex = 0 if self._substack is None else self._substack.startIndex
            if not minIndex <= index <= len(self._commands):
                raise ValueError("Invalid index {} (there are {} commands on the stack)."
                                 .format(index,len(self._commands)))
            self._index = index
            self._emitSignals()
    
    def _emitSignals(self):
        """Emit signals after self._index changed."""
        self.indexChanged.emit(self._index)
        self.canRedoChanged.emit(self._index < len(self._commands))
        self.canUndoChanged.emit(self._index > 0)
        self.redoTextChanged.emit(self._commands[self._index].text() if self._index < len(self._commands)
                                                                     else '')
        self.undoTextChanged.emit(self._commands[self._index-1].text() if self._index > 0 else '')
    
    def shouldDelayEvents(self):
        """Return whether events should be delayed."""
        return self._currentMacro is not None or self._inUndoRedo
    
    def _emitQueuedEvents(self):
        """Emit all events that have been queued."""
        for dispatcher,event in self._eventQueue:
            dispatcher._signal.emit(event) # Really emit! _inUndoRedo is usually still True
        self._eventQueue = []
            
    def addEvent(self,dispatcher,event):
        """Add *event* to the queue. *dispatcher* is the ChangeEventDispatcher that should eventually emit
        the event. Try to merge the event with existing events (of the same dispatcher, of course).
        """ 
        for d,e in self._eventQueue:
            if d is dispatcher:
                if e.merge(event):
                    return # event was merged
        else: self._eventQueue.append((dispatcher,event))
    
    def startSubstack(self):
        """Start a substack and return it. There may be only a single substack at any time."""
        if self._substack is not None:
            raise UndoStackError("Cannot start a substack while another one is active.")
        if self._inUndoRedo or self._macroDepth > 0:
            raise UndoStackError("Cannot start a substack during undo/redo or while a macro is built.""")
        self._stackRest = self._commands[self._index:]
        del self._commands[self._index:]
        self._emitSignals()
        self._substack = Substack(self)
        return self._substack
    
    def endSubstack(self):
        """Delete the current substack. Remove all commands that were added via the substack from the stack.
        Also remove such commands that are contained in macros. Delete macros that are empty thereafter.
        """
        if self._substack is None:
            raise UndoStackError("Cannot end a substack when none is active.")
        if self._inUndoRedo or self._macroDepth > 0:
            raise UndoStackError("Cannot end a substack during undo/redo or while a macro is built.""")
        
        self._index = _filterSubstackCommands(self._commands,self._substack.startIndex,self._index)
        if self._index == self._substack.startIndex:
            # recover stack rest 
            self._commands[self._substack.startIndex:] = self._stackRest
        
        self._stackRest = None
        self._substack._main = None # deactivate. Should not be necessary
        self._substack = None
        self._emitSignals()
        
        
class Macro:
    """A macro stores a list of undocommands and acts like a command that executes all of them together."""
    def __init__(self,text):
        self._text = text
        self.commands = []
    
    def redo(self):
        for command in self.commands:
            command.redo()
    
    def undo(self):
        for command in reversed(self.commands):
            command.undo()
            
    def text(self):
        # this is a function so that macros behave like QUndoCommands
        return self._text
        

class Substack:
    """ A substack is a proxy object that delegates all methods to the stack *mainStack* but will mark all
    commands pushed via the substack by wrapping them in SubstackCommands. When endSubstack is called, all
    those commands are removed from the stack.
    
    Warning: Commands that are added via a substack must not affect anything that is changed by commands
    on the usual stack. Because substack-commands are later removed from the stack, doing so will break
    undo/redo.
        
    This class is used in modal dialogs. Usually the dialog edits a sublevel that lives only as long as the
    dialog. All commands which change that level are added via the substack. When the dialog is closed, those
    commands are removed from the stack. If the dialog has been accepted, it will afterwards push a single
    command/macro containing all changes performed by it (usually a CommitCommand).
    This procedure ensures that undo/redo works during modal dialogs even if global commands are pushed
    between commands editing the dialog's sublevel.
    (like e.g. adding a new tagtype).
    """
    def __init__(self,mainStack,startIndex):
        self._mainStack = mainStack
        self.startIndex = startIndex
        
    def __getattr__(self,name):
        return getattr(self._mainStack,name)
        
    def push(self,command):
        self._mainStack.push(SubstackCommand(command))
        
    
class SubstackCommand:
    """Small wrapper that is put around UndoCommands by Substack to mark those commands that have been added
    via the substack."""
    def __init__(self,command):
        self._command = command
        
    def __getattr__(self,name):
        return getattr(self._command,name)
    
    def __str__(self):
        return "<SUBSTACK: {}>".format(self._command)
    
        
def _filterSubstackCommands(commands,startIndex=0,index=0):
    """Remove all SubstackCommands from the list *commands*. Begin at *startIndex*. Return the new index of
    the position given by *index* in the old list."""  
    i = startIndex
    while i < len(commands):
        command = commands[i]
        if isinstance(command,SubstackCommand):
            del commands[i]
            if index > i:
                index -= 1
        elif isinstance(command,Macro):
            _filterSubstackCommands(command.commands)
            if len(command.commands) == 0:
                del commands[i]
                if index > i:
                    index -= 1
        else: i += 1
    return index
            
        
class UndoRedoAction(QtGui.QAction):
    """QAction that is returned by the methods createUndoAction and createRedoAction."""
    def __init__(self,stack,redo):
        super().__init__(stack)
        if redo:
            self._prefix = self.tr("Redo")
            self.setShortcut(self.tr('Ctrl+Y'))
            stack.canRedoChanged.connect(self.setEnabled)
            stack.redoTextChanged.connect(self.setText)
            self.triggered.connect(stack.redo)
        else:
            self._prefix = self.tr("Undo")
            self.setShortcut(self.tr('Ctrl+Z'))
            stack.canUndoChanged.connect(self.setEnabled)
            stack.undoTextChanged.connect(self.setText)
            self.triggered.connect(stack.undo)
            
    def setText(self,text):
        if text is not None and len(text) > 0:
            super().setText(self.tr("{}: {}").format(self._prefix,text))
        else: super().setText(self._prefix)
    