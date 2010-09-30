#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

class EditorWidget(QtGui.QStackedWidget):
    editorOpened = QtCore.pyqtSignal()
    editorClosed = QtCore.pyqtSignal()
    
    def __init__(self,parent=None):
        QtGui.QStackedWidget.__init__(self,parent)
        self.label = None
        self.editor = None
        self.setFocusPolicy(Qt.StrongFocus)
    
    def getLabel(self):
        return self.label
    
    def setLabel(self,label):
        if self.label is not None:
            self.removeWidget(self.label)
        self.label = label
        self.insertWidget(0,label)
            
    def getEditor(self):
        return self.editor
    
    def setEditor(self,editor):
        if self.editor is not None:
            self.removeWidget(self.editor)
            self.editor.removeEventFilter(self)
        self.editor = editor
        editor.installEventFilter(self)
        self.insertWidget(0 if self.label is None else 1,editor)
        
    def showLabel(self):
        if self.label is not None:
            self.setCurrentWidget(self.label)
        self.setFocusProxy(None) # or we won't receive focusInEvents
    
    def showEditor(self):
        if self.editor is not None:
            self.setCurrentWidget(self.editor)
            self.setFocusProxy(self.editor)
            self.editor.selectAll()

    def focusInEvent(self,focusEvent):
        if self.currentWidget() == self.label:
            self.showEditor()
            self.editor.setFocus(Qt.MouseFocusReason)
            self.editorOpened.emit()
        QtGui.QStackedWidget.focusInEvent(self,focusEvent)
    
    def eventFilter(self,object,event):
        if object == self.editor and event.type() == QtCore.QEvent.FocusOut:
            self.showLabel()
            self.editorClosed.emit()
        return False # don't stop the event