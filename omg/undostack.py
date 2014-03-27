# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

from . import logging, database as db
logger = logging.getLogger(__name__)


class UndoStackError(RuntimeError):
    """This error is raised when methods of UndoStack are improperly used (e.g. call endMacro when no macro
    is built."""


class UndoStack(QtCore.QObject):
    """An UndoStack stores UndoCommands and provides undo/redo. It provides the same API as QUndoStack but
       improves it in several ways:
      
         - any object may be used as UndoCommand. It must support the methods undo, redo and the attribute
           text,
         - the attempt to modify the stack during undo/redo will lead to a RuntimeError,
         - while a macro is composed and during undo/redo, ChangeEventDispatcher won't emit events directly,
           but add them to an internal queue. When the macro is completed or undo/redo finished, all events
           will be emitted.
         - Events in the queue may be merged (see ChangeEvent.merge)
         - it is possible to abort a macro (similar to rollback in transactional DBs)
         - A substack is a proxy object that acts like the main stack but remembers which commands are pushed
           via the substack. When the substack is closed, all those commands are removed from the stack.
           This is necessary for modal dialogs or plugins like MPD (if the connection gets lost, all
           commands are removed from the stack.
          
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
        self._activeMacros = []    # list of nested macros that are being built (first is outermost)
        self._inUndoRedo = False   # True during undo and redo
        self._eventQueue = []      # list of tuples (dispatcher,event)
        self._undoAction = UndoRedoAction(self,redo=False)
        self._redoAction = UndoRedoAction(self,redo=True)
        self._modalDialogSubstack = None # exclusive special substack for modal dialogs
    
    def index(self):
        """Return the current position of the stack. stack.command(stack.index()) is the command that will
        be redone next."""
        return self._index
    
    def isComposing(self):
        return len(self._activeMacros) > 0
    
    def count(self):
        """Return the number of commands on the stack."""
        return len(self._commands)
    
    def command(self,index):
        """Return the UndoCommand at the given index. stack.command(stack.index()) is the command that will
        be redone next."""
        return self._commands[index]
        
    def beginMacro(self, *args, **kwargs):
        """Begin a new macro and return it.
        
        The arguments are the same as in the *Macro* constructor.""" 
        if self._inUndoRedo:
            raise UndoStackError("Cannot begin a macro during undo/redo.")
        macro = Macro(*args, **kwargs)
        self._activeMacros.append(macro)
        return macro
        # Macros are not added to their parent macro or to the stack unless they are finished.
        # (This makes abortMacro easier)
            
    def push(self, command, *args, **kwargs):
        """Add a command to the stack and call its redo-method. If other arguments are given, a macro around
        the command is constructed and those arguments are passed to the constructor of macro.
        """
        assert not isinstance(command, Macro) # will not work correctly
        if self._inUndoRedo:
            raise UndoStackError("Cannot push a command during undo/redo.")
        if len(self._activeMacros) == 0 or len(args) > 0 or len(kwargs) > 0:
            self.beginMacro(command.text, *args, **kwargs)
            self.push(command)
            self.endMacro()
        else:
            # Check whether argument 'firstRedo' should be used
            code = command.redo.__code__
            if code.co_varnames[:code.co_argcount] == ('self', 'firstRedo'):
                assert command.redo.__defaults__ == (False,)
                command.redo(firstRedo=True)
            else: command.redo()
            self._activeMacros[-1].add(command)
        
    def endMacro(self, abortIfEmpty=False):
        """Ends composition of a macro command. If *abortIfEmpty* is True and no commands have been added
        to the macro, it will simply be dropped (and never reach the stack)."""
        if len(self._activeMacros) == 0:
            raise UndoStackError("Cannot end a macro when no macro is being built.")
        if self._inUndoRedo:
            raise UndoStackError("Cannot end a macro during undo/redo.")

        # Do not use pop here. The macro must remain active until the end (mainly for _emitQueuedEvents)
        macro = self._activeMacros[-1]           
        macro.end()
        # Remember that Macros are not added to their parent macro or to the stack unless they are finished.
        if len(self._activeMacros) > 1:
            self._activeMacros[-2].add(macro)
            del self._activeMacros[-1]
        else:
            # outermost macro has been closed
            if abortIfEmpty and macro.isEmpty():
                self._activeMacros = []
                assert len(self._eventQueue) == 0
                return
            self._commands[self._index:] = [macro] # overwrite rest of the stack
            self._index += 1
            self._emitSignals()
            self._emitQueuedEvents()
            self._activeMacros = []
            
    def abortMacro(self):
        """Abort the current macro: Undo all commands that have been added to it and delete the macro. This
        is better than endMacro+undo because it doesn't leave an unfinished macro on the stack."""
        if len(self._activeMacros) == 0:
            raise UndoStackError("Cannot abort macro, because no macro is being built.")
        if self._inUndoRedo:
            raise UndoStackError("Cannot end a macro during undo/redo.")
        
        for macro in reversed(self._activeMacros):
            macro.abort()
        self._activeMacros = []
        self._eventQueue = []
        # No need to change the stack because active macros have not been added to the stack.
        
    def clear(self):
        """Delete all commands on the stack."""
        if self._inUndoRedo or self.isComposing():
            raise UndoStackError("Cannot clear the stack during undo/redo or while a macro is built.")
        self._clear()
        
    def _clear(self):
        """Unconditionally delete all commands, active macros and everything from the stack.
        Emit queued events."""
        self._commands = []
        self._activeMacros = []
        self._index = 0
        self._emitQueuedEvents()
        self._emitSignals()
        self._inUndoRedo = False         
           
    def canUndo(self):
        """Returns whether there is a command that can be undone."""
        return self._index > 0
    
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
    
    def undoText(self):
        """Return the text of the next action/macro that will be undone."""
        return self._commands[self._index-1].text if self._index > 0 else ''
    
    def redoText(self):
        """Return the text of the next action/macro that will be redone."""
        return self._commands[self._index].text if self._index < len(self._commands) else ''

    def undo(self):
        """Undo the last command/macro."""
        if self._inUndoRedo or self.isComposing():
            raise UndoStackError("Cannot undo a command during undo/redo or while a macro is built.""")
        if self._index == 0:
            raise UndoStackError("There is no command to undo.")
        self._inUndoRedo = True
        commandOrMacro = self._commands[self._index-1]
        try:
            commandOrMacro.undo()
        except Exception as e:
            logger.exception(e)
            self._clear()
            logger.warning("Undostack cleared")
            return
        self._index -= 1
        self._emitQueuedEvents()
        self._inUndoRedo = False
        self._emitSignals()
    
    def redo(self):
        """Redo the next command/macro."""
        if self._inUndoRedo or self.isComposing():
            raise UndoStackError("Cannot redo a command during undo/redo or while a macro is built.""")
        if self._index == len(self._commands):
            raise UndoStackError("There is no command to redo.")
        self._inUndoRedo = True
        commandOrMacro = self._commands[self._index]
        try:
            commandOrMacro.redo()
        except Exception as e:
            logger.exception(e)
            self._clear()
            logger.warning("Undostack cleared")
        self._index += 1
        self._emitQueuedEvents()
        self._inUndoRedo = False
        self._emitSignals()
        
    def setIndex(self,index):
        """Undo/redo commands until there are *index* commands left that can be undone."""
        if self._inUndoRedo or self.isComposing():
            raise UndoStackError("Cannot change index during undo/redo or while a macro is built.""")
        if index != self._index:
            if not 0 <= index <= len(self._commands):
                raise ValueError("Invalid index {} (there are {} commands on the stack)."
                                 .format(index,len(self._commands)))
            self._inUndoRedo = True
            try:
                if index < self._index:
                    for command in reversed(self._commands[index:self._index]):
                        command.undo()
                else:
                    for command in self._commands[self._index:index]:
                        command.redo()
            except Exception as e:
                logger.exception(e)
                self._clear()
                logger.warning("Undostack cleared")
                return
            self._index = index    
            self._emitQueuedEvents()
            self._inUndoRedo = False
            self._emitSignals()
    
    def _emitSignals(self):
        """Emit signals after self._index changed."""
        self.indexChanged.emit(self._index)
        self.canRedoChanged.emit(self.canRedo())
        self.canUndoChanged.emit(self.canUndo())
        self.redoTextChanged.emit(self.redoText())
        self.undoTextChanged.emit(self.undoText())
    
    def shouldDelayEvents(self):
        """Return whether events should be delayed."""
        return self.isComposing() or self._inUndoRedo
    
    def _emitQueuedEvents(self):
        """Emit all events that have been queued."""
        #print("_emitQueuedEvents: {}".format(len(self._eventQueue)))
        for dispatcher,event in self._eventQueue:
            # Use dispatcher._signal.emit instead of dispatcher.emit to really emit signals
            dispatcher._signal.emit(event)
        self._eventQueue = []
            
    def addEvent(self,dispatcher,event):
        """Add *event* to the queue. *dispatcher* is the ChangeEventDispatcher that should eventually emit
        the event. Try to merge the event with existing events (of the same dispatcher, of course).
        """ 
        for d,e in reversed(self._eventQueue):
            if d is dispatcher:
                if e.merge(event):
                    return # event was merged
                break # Only try to merge with the last event of the same dispatcher
        self._eventQueue.append((dispatcher,event))
            
    def createSubstack(self, modalDialog=False):
        """Start a substack and return it. 
        
        If *modalDialog* is True, a special "modal dialog" substack is created. Contrary to usual substacks
        it will hide all commands that have been on the stack until the substack is cleared. This is used
        in modal dialogs and will give the user the feeling that the dialog had its own undostack. The
        difference is that methods like tags.addTagType may still add commands to the global stack.
        This procedure ensures that undo/redo works during modal dialogs even if global commands are pushed
        between commands editing the dialog's sublevel.
        """
        if self._inUndoRedo or self.isComposing():
            raise UndoStackError("Cannot start a substack during undo/redo or while a macro is built.""")
        substack = Substack(self)
        if modalDialog:
            if self._modalDialogSubstack is not None:
                raise UndoStackError("Cannot create a second modal dialog substack.")
            self._modalDialogSubstack = substack
            self._storedCommands = self._commands
            self._storedIndex = self.index()
            self.clear()
        return substack
    
    def resetSubstack(self, substack):
        """Remove all commands that were added via the substack from the stack. Do not close the substack.
        """
        #if self._inUndoRedo:
        #    raise UndoStackError("Cannot reset a substack during undo/redo.""")
    
        self._index = _filterSubstackCommands(substack, self._commands, self._index)
        self._emitSignals()
        
    def closeSubstack(self, substack):
        """Remove all commands that were added via the substack from the stack and close the substack."""
        
        #if self._inUndoRedo:
        #    raise UndoStackError("Cannot close a substack during undo/redo.""")
    
        substack._closed = True
        self._index = _filterSubstackCommands(substack, self._commands, self._index)
        if self._modalDialogSubstack is not None:
            # Also filter commands that are stored away during a modal dialog substack
            self._storedIndex = _filterSubstackCommands(substack, self._storedCommands, self._storedIndex)
            
            if substack is self._modalDialogSubstack:
                # Restore the stack as it was before the modal dialog substack was created
                if len(self._commands) == 0:
                    self._commands = self._storedCommands
                else:
                    # as usual overwrite commands that have been undone by newly added commands
                    self._commands = self._storedCommands[:self._storedIndex] + self._commands
                self._index += self._storedIndex
                self._modalDialogSubstack = None
                self._storedCommands = None
                self._storedIndex = None
        self._emitSignals()
                
    
class Macro:
    """A macro stores a list of undocommands and acts like a command that executes all of them together.
    
    If *transaction* is True, the macro will always be executed in a database transaction.
    If given *preMethod* is called before the commands of this macro are redone/undone and *postMethod*
    is called afterwards. The order of *preMethod* and *postMethod* is thus independent of whether we are
    undoing or redoing. This could be used to call some prepare/update methods before or after the macro's
    commands. 
    
    The class Macro and its methods should never be used directly. Use methods of UndoStack instead.
    """
    def __init__(self, text, transaction=False, preMethod=None, postMethod=None):
        self.text = text
        self.commands = []
        self.transaction = transaction
        self.preMethod = preMethod
        self.postMethod = postMethod
        self.attachedCommands = []
        self.finished = False
        self.begin()
    
    def add(self, commandOrMacro):
        """Add a command or macro to this macro."""
        (self.commands if not self.finished else self.attachedCommands).append(commandOrMacro)
    
    def begin(self):
        """Perform stuff before the commands of this macro are redone/undone."""
        if self.transaction:
            db.transaction()
        if self.preMethod is not None:
            self.preMethod()
            
    def end(self):
        """Perform stuff after the commands of this macro have been redone/undone."""
        if self.postMethod is not None:
            self.postMethod()
        if self.transaction:
            db.commit()
        self.finished = True # after first redo, the macro is finished
    
    def redo(self):
        """(Re)do this macro and all of the commands inside."""
        self.begin()
        for command in self.commands:
            command.redo()
        self.end()
        for command in self.attachedCommands:
            command.redo()
    
    def undo(self):
        """Undo this macro and all of the commands inside."""
        self.begin()
        for command in reversed(self.commands):
            command.undo()
        self.end()
        for command in reversed(self.attachedCommands):
            command.undo()
            
    def abort(self):
        """Abort this macro during its construction (i.e. between UndoStack.beginMacro and
        UndoStack.endMacro) and undo all of its changes."""
        for command in reversed(self.commands):
            command.undo()
        if self.transaction:
            #This assumes that this macro has not been finished
            db.rollback()
            
    def isEmpty(self):
        """Return whether this macro is empty, i.e. no command has been added to it."""
        return all(isinstance(command, Macro) and command.isEmpty() for command in self.commands)
    
    def printStructure(self, indent = ''):
        """Debug method: print the tree below this node using indentation."""
        print(indent + str(self))
        indent, aIndent = indent+'  ', indent+'A '
        for commands, newIndent in (self.commands, indent), (self.attachedCommands, aIndent): 
            for command in commands:
                if isinstance(command, Macro):
                    command.printStructure(newIndent)
                else: print(newIndent + str(command))
        

class Substack:
    """ A substack is a proxy object that delegates all methods to the stack *mainStack* but will mark all
    commands pushed via the substack by wrapping them in SubstackCommands. With UndoStack.clearSubstack
    all these commands can be deleted from the stack.
    
    Warning: Commands that are added via a substack must not affect anything that is changed by commands
    on the usual stack. Because substack-commands are later removed from the stack, doing so will break
    undo/redo.
    
    To create substacks use UndoStack.createSubstack.
    """
    def __init__(self, mainStack):
        self._mainStack = mainStack
        self._closed = False
        
    def __getattr__(self,name):
        return getattr(self._mainStack,name)
        
    def push(self,command):
        if self._closed:
            raise UndoStackError("Cannot push commands via a closed substack.")
        self._mainStack.push(SubstackCommand(self, command))
        
    def reset(self):
        """Remove all commands of the substack from the main stack. Do not close the substack."""
        self._mainStack.resetSubstack(self)
        
    def close(self):
        """Close the substack, removing all of its commands from the main stack."""
        self._mainStack.closeSubstack(self)
        
    
class SubstackCommand:
    """Small wrapper that is put around UndoCommands by a substack to mark those commands that have been
    added via the substack."""
    def __init__(self, substack, command):
        self._command = command
        self._substack = substack
        
    def __getattr__(self,name):
        return getattr(self._command,name)
    
    def __str__(self):
        return "<SUBSTACK: {}>".format(self._command)
    
        
def _filterSubstackCommands(substack, commands, index=0):
    """Remove all SubstackCommands belonging to *substack* from the list *commands*. Return the new index of
    the position given by *index* in the old list."""  
    i = 0
    while i < len(commands):
        command = commands[i]
        if isinstance(command, SubstackCommand) and command._substack is substack:
            del commands[i]
            if index > i:
                index -= 1
            continue
        elif isinstance(command,Macro):
            _filterSubstackCommands(substack, command.commands)
            _filterSubstackCommands(substack, command.attachedCommands)
            #TODO: Should macros be removed which have no commands but attached commands?
            if len(command.commands) == 0 and len(command.attachedCommands) == 0:
                # if the macro is empty, remove it
                del commands[i]
                if index > i:
                    index -= 1
                continue
        i += 1
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
        self.setText('')
            
    def setText(self,text):
        if text is not None and len(text) > 0:
            super().setText(self.tr("{}: {}").format(self._prefix,text))
        else: super().setText(self._prefix)
    