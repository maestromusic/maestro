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

           
class UndoStack(QtCore.QObject):
    """An UndoStack stores QUndoCommands and provides undo/redo. It provides the same API as QUndoStack but
    improves it in several ways:
    
        - the attempt to modify the stack during undo/redo will lead to a RuntimeError,
        - while a macro is composed and during undo/redo, ChangeEventDispatcher won't emit events directly,
          but add them to an internal queue. When the macro is completed or undo/redo finished, all events
          will be emitted.
        - Events on the queue may be merged (see ChangeEvent.merge)
        - it is possible to abort a macro (similar to rollback in transactional DBs)
        
    """
    canRedoChanged = QtCore.pyqtSignal(bool)
    canUndoChanged = QtCore.pyqtSignal(bool)
    indexChanged = QtCore.pyqtSignal(int)
    redoTextChanged = QtCore.pyqtSignal(str)
    undoTextChanged = QtCore.pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._commands = []       # List of commands/macros
        self._index = 0           # Position before the command that will be executed on redo
        self._macroDepth = 0      # Number of open macros (# of beginMacro - # of endMacro)
        self._inUndoRedo = False  # True during undo and redo
        self._eventQueue = []     # list of tuples (dispatcher,event)
        self._currentMacro = None # macro while it is built.
        self._undoAction = UndoRedoAction(self,redo=False)
        self._redoAction = UndoRedoAction(self,redo=True)
        
    def beginMacro(self,text):
        # Note that nested calls to beginMacro will not create more than one macro
        if self._inUndoRedo:
            raise RuntimeError("You cannot begin a macro during undo/redo.")
        self._macroDepth += 1
        if self._macroDepth == 1:
            assert self._currentMacro is None
            self._currentMacro = Macro(text)
        
    def push(self,command):
        if not isinstance(command,QtGui.QUndoCommand):
            raise TypeError("I push QUndoCommands, not {}: {}".format(type(command),command))
        if self._inUndoRedo:
            raise RuntimeError("You cannot push a command during undo/redo.")
        command.redo()
        if self._currentMacro is None:
            self._push(command)
        else: self._currentMacro.commands.append(command)
        
    def _push(self,command):
        """Helper for push and endMacro."""
        # Overwrite commands after self._index
        self._commands[self._index:] = [command]
        self._index += 1
        self._emitSignals()
        
    def endMacro(self):
        if self._inUndoRedo:
            raise RuntimeError("You cannot end a macro during undo/redo.")
        self._macroDepth -= 1
        if self._macroDepth == 0:
            assert self._currentMacro is not None
            self._push(self._currentMacro)
            self._emitQueuedEvents()
            self._currentMacro = None
    
    def abortMacro(self):
        """Abort the current macro: Undo all commands that have been added to it and delete the macro. This
        is better than endMacro+undo because it doesn't leave an unfinished macro on the stack."""
        if self._currentMacro is None:
            raise RuntimeError("Cannot abort macro, because no macro is being built.")
        self._currentMacro.undo()
        self._currentMacro = None
        self._macroDepth = 0
        
    def canUndo(self):
        return self._index > 0
    
    def canRedo(self):
        return self._index < len(self._commands)

    def createRedoAction(self):
        return self._redoAction
    
    def createUndoAction(self):
        return self._undoAction
    
    @QtCore.pyqtSlot()
    def undo(self):
        if self._inUndoRedo or self._macroDepth > 0:
            raise RuntimeError("You cannot undo a command during undo/redo or while a macro is built.""")
        self._inUndoRedo = True
        commandOrMacro = self._commands[self._index-1]
        commandOrMacro.undo()
        self._index -= 1
        self._emitQueuedEvents()
        self._inUndoRedo = False
        self._emitSignals()
    
    @QtCore.pyqtSlot()
    def redo(self):
        if self._inUndoRedo or self._macroDepth > 0:
            raise RuntimeError("You cannot redo a command during undo/redo or while a macro is built.""")
        self._inUndoRedo = True
        commandOrMacro = self._commands[self._index]
        commandOrMacro.redo()
        self._index += 1
        self._emitQueuedEvents()
        self._inUndoRedo = False
        self._emitSignals()
    
    def setIndex(self,index):
        if index != self._index:
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
    