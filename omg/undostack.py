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


class UndoStack(QtGui.QUndoStack):
    def __init__(self):
        super().__init__()
        self._macroDepth = 0
        self._inUndoRedo = False
        self._eventQueue = []
    
    def delayEvents(self):
        """Return whether events should be delayed."""
        return self._macroDepth > 0 or self._inUndoRedo
    
    def beginMacro(self,text):
        if self._inUndoRedo:
            raise RuntimeError("You cannot begin a macro during undo/redo.")
        super().beginMacro(text)
        self._macroDepth += 1
        
    def push(self,command):
        if self._inUndoRedo:
            raise RuntimeError("You cannot push a command during undo/redo.")
        super().push(command)
        
    def endMacro(self):
        if self._inUndoRedo:
            raise RuntimeError("You cannot end a macro during undo/redo.")
        super().endMacro()
        self._macroDepth -= 1
        if self._macroDepth == 0:
            self._emitQueuedEvents()
        
    def _emitQueuedEvents(self):
        for dispatcher,event in self._eventQueue:
            dispatcher.emit(event)
        self._eventQueue = []
            
    def addEvent(self,dispatcher,event):
        for d,e in self._eventQueue:
            if d is dispatcher:
                if e.merge(event):
                    print("Merge successful")
                    return # event was merged
        else: self._eventQueue.append((dispatcher,event))
    
    @QtCore.pyqtSlot()
    def undo(self):
        if self._inUndoRedo or self._macroDepth > 0:
            raise RuntimeError("You cannot undo a command during undo/redo or while a macro is built.""")
        self._inUndoRedo = True
        super().undo()
        self._emitQueuedEvents()
        self._inUndoRedo = False
    
    @QtCore.pyqtSlot()
    def redo(self):
        if self._inUndoRedo or self._macroDepth > 0:
            raise RuntimeError("You cannot redo a command during undo/redo or while a macro is built.""")
        self._inUndoRedo = True
        super().redo()
        self._emitQueuedEvents()
        self._inUndoRedo = False
        