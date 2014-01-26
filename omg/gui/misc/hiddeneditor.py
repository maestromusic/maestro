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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt


class HiddenEditor(QtGui.QStackedWidget):
    """An HiddenEditor contains two child-widgets stacked upon each other: An editor (either a QLineEdit or
    a QComboBox or a QTextEdit) and a QLabel showing the editor's value. Usually the label is displayed,
    but when the user clicks on it, the editor appears and the value can be edited. When the editor looses
    focus, the label reappears.
    """
    valueChanged = QtCore.pyqtSignal()
    label = None
    editor = None
    
     # Contains the context-menu, while the editor displays one. This is necessary to prevent hiding the
     # editor, when it looses focus to its context-menu.
    popup = None
    
    # If True, the currently active widget (editor and label) will remain active until fixed is set to false
    # again. You may still use showEditor or showLabel to switch programmatically, though.
    fixed = False 
    
    def __init__(self, label=None, editor=None, parent=None, shrink=False):
        """Create a new HiddenEditor. You may specify a label, an editor and a parent. By default a QLabel
        and an empty QLineEdit are created. If *shrink* is True the HiddenEditor will only occupy the space
        of the currently visible widget. This is useful if a big editor (e.g. QTextEdit) contains only a
        short text, so that the label is small.
        """
        QtGui.QStackedWidget.__init__(self, parent)
        self.shrink = shrink
        self.setLabel(label)
        self.setEditor(editor)
        self.setFocusPolicy(Qt.StrongFocus)
    
    def getLabel(self):
        """Return the label used in this HiddenEditor."""
        return self.label
    
    def setLabel(self, label=None):
        """Set the label used in this HiddenEditor. The label will be updated to hold the editor's value. If
        label is None, a default QLabel is created and used."""
        if self.label is not None:
            self.removeWidget(self.label)
        if label is None:
            label = QtGui.QLabel()
            label.setTextFormat(Qt.PlainText)
            label.setIndent(2)
        self.label = label
        # Keep at least the height of an QLineEdit. TODO: Improve this hack. 
        if self.shrink:
            self.label.setMinimumHeight(26)
        if self.editor is not None:
            self.label.setText(self._editorText())
        self.insertWidget(0, self.label)

    def isFixed(self):
        """Return whether this HiddenEditor is fixed, i.e. it does not switch between label and editor."""
        return self.fixed

    def setFixed(self, fixed):
        """Set whether this HiddenEditor is fixed, i.e. it does not switch between label and editor."""
        self.fixed = fixed
        
    def getEditor(self):
        """Return the editor used in this HiddenEditor."""
        return self.editor
    
    def setEditor(self, editor):
        """Set the editor used in this HiddenEditor. The editor must either be a QLineEdit or a QComboBox or
        a QTextEdit or None in which case an empty QLineEdit is created. The label will be updated to hold
        the editor's value.
        """
        assert (editor is None
                    or isinstance(editor, QtGui.QLineEdit)
                    or isinstance(editor, QtGui.QComboBox)
                    or isinstance(editor, QtGui.QTextEdit))
        if self.editor is not None:
            self.removeWidget(self.editor)
            self.editor.removeEventFilter(self)
            if isinstance(self.editor, QtGui.QTextEdit):
                self.editor.viewport().removeEventFilter(self)
        self.editor = editor if editor is not None else QtGui.QLineEdit()
        self.editor.installEventFilter(self)
        if isinstance(self.editor, QtGui.QTextEdit):
            self.editor.viewport().installEventFilter(self)
        self.insertWidget(1, self.editor)
        self.setValue(self._editorText())

    def _editorText(self):
        """Return the text contained in the editor."""
        if isinstance(self.editor, QtGui.QLineEdit):
            return self.editor.text()
        elif isinstance(self.editor, QtGui.QTextEdit):
            return self.editor.toPlainText()
        else: return self.editor.currentText()
        
    def showLabel(self):
        """Display the label and hide the editor."""
        if self.label is not None:
            self.setCurrentWidget(self.label)
        self.setFocusProxy(None) # or we won't receive focusInEvents
    
    def showEditor(self):
        """Display the editor and hide the label."""
        if self.editor is not None:
            self.setCurrentWidget(self.editor)
            self.setFocusProxy(self.editor)
            if hasattr(self.editor, 'selectAll'):
                self.editor.selectAll()

    def getValue(self):
        """Return the value contained in this HiddenEditor."""
        return self._editorText()

    def setValue(self, value):
        """Set the value contained in this HiddenEditor."""
        if value != self._editorText():
            if isinstance(self.editor, QtGui.QLineEdit):
                self.editor.setText(value)
            elif isinstance(self.editor, QtGui.QTextEdit):
                self.editor.setPlainText(value)
            else: self.editor.setEditText(value)
        if value != self.label.text():
            self.label.setText(value)
            self.valueChanged.emit()
        
    def focusInEvent(self, focusEvent):
        # focusInEvents are used to switch to the editor.
        if not self.fixed and self.currentWidget() == self.label:
            self.showEditor()
            self.editor.setFocus(focusEvent.reason())
        QtGui.QStackedWidget.focusInEvent(self, focusEvent)
    
    def eventFilter(self, object, event):
        # We have to filter several events from the editor:
        # - FocusOut: Hide the editor and show the label...except the focus switched to the editor's
        #   context-menu or item-view (if the editor is a combobox).
        # - ContextMenu: Display the context-menu as usual but additionally store it in self.popup, so that
        #   when the editor looses its focus to the context-menu, we won't hide the editor in the
        #   FocusOut-event.
        # - KeyPress: React to RETURN and ENTER (accept the value and display the label) and ESC (reset the
        #   editor to the label's value and display the label).
        if object == self.editor:
            if event.type() == QtCore.QEvent.FocusOut:
                if (self.popup is None # No context-menu...so check for the view of a combobox
                        and not (isinstance(self.editor, QtGui.QComboBox)
                        and self.editor.view().isVisible())):
                    self.setValue(self._editorText())
                    if not self.fixed:
                        self.showLabel()
                    return False
                return False
            elif event.type() == QtCore.QEvent.ContextMenu:
                # See below for QTextEdit
                if not isinstance(self.editor, QtGui.QComboBox):
                    self.popup = self.editor.createStandardContextMenu()
                else: self.popup = self.editor.lineEdit().createStandardContextMenu()
                action = self.popup.exec_(event.globalPos())
                self.popup = None
                return True
            elif event.type() == QtCore.QEvent.KeyPress:
                if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                    # Allow Shift+Enter in a QTextEdit
                    if isinstance(self.editor, QtGui.QTextEdit) and Qt.ShiftModifier & event.modifiers():
                        return False
                    self.setValue(self._editorText())
                    if not self.fixed:
                        self.showLabel()
                    return True
                elif event.key() == Qt.Key_Escape:
                    self.setValue(self.label.text())
                    if not self.fixed:
                        self.showLabel()
                    return True
        elif (isinstance(self.editor, QtGui.QTextEdit)
                    and object == self.editor.viewport()
                    and event.type() == QtCore.QEvent.ContextMenu):
            # QTextEdit does not send ContextMenuEvents itself, but its viewport does. Therefore we
            # installed an event filter on the viewport and filter events here.
            self.popup = self.editor.createStandardContextMenu()
            action = self.popup.exec_(event.globalPos())
            self.popup = None
            return True
            
        return False # don't stop the event
    
    def sizeHint(self):
        if self.shrink: 
            return self.currentWidget().sizeHint()
        else: return super().sizeHint()
    
    def minimumSizeHint(self):
        if self.shrink:
            return self.currentWidget().minimumSizeHint()
        else: return super().minimumSizeHint()
