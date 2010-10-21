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
    valueChanged = QtCore.pyqtSignal(str)

    label = None
    editor = None
    
    def __init__(self,label=None,editor=None,parent=None):
        QtGui.QStackedWidget.__init__(self,parent)
        self.setLabel(label)
        self.setEditor(editor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.popup = None
    
    def getLabel(self):
        return self.label
    
    def setLabel(self,label):
        if self.label is not None:
            self.removeWidget(self.label)
            self.label.removeEventFilter(self)
        self.label = label if label is not None else QtGui.QLabel()
        self.label.installEventFilter(self)
        self.insertWidget(0,self.label)
            
    def getEditor(self):
        return self.editor
    
    def setEditor(self,editor):
        if self.editor is not None:
            self.removeWidget(self.editor)
            self.editor.removeEventFilter(self)
        self.editor = editor if editor is not None else QtGui.QLineEdit()
        self.editor.installEventFilter(self)
        self.insertWidget(1,self.editor)
        
    def showLabel(self):
        if self.label is not None:
            self.setCurrentWidget(self.label)
        self.setFocusProxy(None) # or we won't receive focusInEvents
    
    def showEditor(self):
        if self.editor is not None:
            self.setCurrentWidget(self.editor)
            self.setFocusProxy(self.editor)
            if hasattr(self.editor,'selectAll'):
                self.editor.selectAll()

    def getValue(self):
        return self.label.text()

    def setValue(self,value):
        if value != self.editor.text():
            self.editor.setText(value)
        if value != self.label.text():
            self.label.setText(value)
            self.valueChanged.emit(value)
        
    def focusInEvent(self,focusEvent):
        if self.currentWidget() == self.label:
            self.showEditor()
            self.editor.setFocus(focusEvent.reason())
        QtGui.QStackedWidget.focusInEvent(self,focusEvent)
    
    def eventFilter(self,object,event):
        #~ if object == self.label:
            #~ if event.type() == QtCore.QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                #~ self.showEditor()
                #~ return True # consume event
        if object == self.editor:
            if event.type() == QtCore.QEvent.FocusOut:
                if self.popup is None:
                    self.showLabel()
                    self.setValue(self.editor.text())
                    return False
                return False
            elif event.type() == QtCore.QEvent.ContextMenu:
                self.popup = self.editor.createStandardContextMenu()
                action = self.popup.exec_(self.editor.mapToGlobal(event.pos()))
                self.popup = None
                return True
            elif event.type() == QtCore.QEvent.KeyPress:
                if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                    self.setValue(self.editor.text())
                    self.showLabel()
                    return True
                elif event.key() == Qt.Key_Escape:
                    self.setValue(self.label.text())
                    self.showLabel()
                    return True
        return False # don't stop the event
