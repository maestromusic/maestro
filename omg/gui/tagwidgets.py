#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#
from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from omg import tags, FlexiDate, db
from omg.gui.misc import editorwidget

class TagLabel(QtGui.QLabel):
    """Specialized label which can contain arbitrary text, but displays the corresponding icons next to the name when showing tagnames."""
    iconSize = QtCore.QSize(24,24) # Size of the icon
    
    def __init__(self,tag=None,parent=None):
        """Initialize a new TagLabel. You may specify a tag which is displayed at the beginning and a parent."""
        QtGui.QLabel.__init__(self,parent)
        self.setTag(tag)

    def text(self):
        if self.tag is not None:
            return self.tag.translated()
        else: return ''
        
    def setText(self,text):
        if text == '':
            self.setTag(None)
        else: self.setTag(tags.fromTranslation(text))
        
    def getTag(self,tag):
        """Return the tag which is currently shown or None if no tag is shown."""
        return self.tag
        
    def setTag(self,tag):
        """Set the tag which is shown by this label. If <tag> is None, clear the label."""
        self.tag = tag
        if tag is None:
            self.clear()
        else:
            if tag.iconPath() is not None:
                QtGui.QLabel.setText(self,'<img src="{}" widht="{}" height="{}"> {}'
                                    .format(tag.iconPath(),self.iconSize.width(),self.iconSize.height(),tag.translated()))
            else: QtGui.QLabel.setText(self,tag.translated())


class TagTypeBox(QtGui.QComboBox):
    """Combobox to choose an indexed tag (from those in the database). If the box is editable the user may insert an arbitrary text and getTag may return OtherTags, too (confer getTag)."""
    def __init__(self,defaultTag = None,parent=None):
        """Initialize a TagTypeBox. You may specify a tag that is selected at the beginning and a parent."""
        QtGui.QComboBox.__init__(self,parent)
        self.setEditable(True)
        self.setInsertPolicy(QtGui.QComboBox.NoInsert)
        if defaultTag is None:
            self.setEditText('')
        
        for tag in tags.tagList:
            if tag.iconPath() is not None:
                self.addItem(QtGui.QIcon(tag.iconPath()),tag.translated())
            else: self.addItem(tag.translated())
            if tag == defaultTag:
                self.setCurrentIndex(self.count()-1)
                
    def getTag(self):
        """Return the tag that is currently selected. This method uses tags.fromTranslation to get a tag from the text in the combobox: If the tag is the translation of a tagname, that tag will be returned. Otherwise tags.get will be used. If the user really wants to create a tag with a name that is the translation of another tag into his language (e.g. he wants to create a 'titel'-tag that is not the usual 'title'-tag), he has to quote the tagname (using " or '): inserting "titel" into the combobox will do the job.
        Note that the case of the entered text does not matter; all tags have lowercase names. This method returns None if no tag can be generated, because e.g. the text is not a valid tagname."""
        text = self.currentText().strip()
        try:
            if text[0] == text[-1] and text[0] in ['"',"'"]: # Don't translate if the text is quoted
                return tags.get(text[1:-1])
            else: return tags.fromTranslation(text)
        except ValueError:
            return None


class TagValidator(QtGui.QValidator): #TODO remove if useless
    def __init__(self,tag):
        QtGui.QValidator.__init__(self)
        self.tag = tag

    def validate(self,value,pos): # Pos allows to change the caret position (and is a reference parameter in C++)
        if self.tag.isValid(value):
            return (QtGui.QValidator.Acceptable,value,pos)
        else: return (QtGui.QValidator.Intermediate,value,pos)


class EnhancedTextEdit(QtGui.QTextEdit):
    """Enhanced version of QtGui.QTextEdit which has an editingFinished-signal like QLineEdit."""
    editingFinished = QtCore.pyqtSignal()
    def __init__(self,parent=None):
        QtGui.QTextEdit.__init__(self,parent)
        self.changed = False
        self.textChanged.connect(self._handleTextChanged)

    def _handleTextChanged(self):
        self.changed = True
        
    def focusOutEvent(self,event):
        if self.changed:
            self.changed = False
            self.editingFinished.emit()
        QtGui.QTextEdit.focusOutEvent(self,event)


class TagValueEditor(QtGui.QWidget):
    # Dictionary mapping tags to all the values which have been entered in a TagLineEdit during this application. Will be used in the completer.
    insertedValues = {}

    tagChanged = QtCore.pyqtSignal(tags.Tag)
    valueChanged = QtCore.pyqtSignal()
    
    def __init__(self,tag,parent=None,useEditorWidget=False):
        QtGui.QWidget.__init__(self,parent)
        assert tag is not None
        self.setLayout(QtGui.QStackedLayout()) # doesn't matter...we just need a layout for one child widget
        self.useEditorWidget = useEditorWidget
        self.editor = None
        self.tag = None # Create the variable
        self.valid = tag.isValid('')
        self.setTag(tag)

    def canSwitchTag(self,newTag):
        return newTag.isValid(self.getText())
        
    def getTag(self):
        return self.tag

    def setTag(self,tag,setValue=True):
        if tag == self.tag:
            return
        
        if self.tag is None or self._editorClass(tag) != self._editorClass(self.tag):
            # We have to change the editor
            if self.editor is not None:
                text = self.getText()
                self.layout().removeWidget(self.editor)
                self._createEditor(tag)
                self.layout().addWidget(self.editor)
                self.tag = tag
                if setValue:
                    self.setValue(text)
            else: 
                self._createEditor(tag)
                self.layout().addWidget(self.editor)
                self.tag = tag
        else: # It may happen that the current value interpreted as value of the new tag should be displayed differently. Therefore after changing the tag we invoke setValue with the current value.
            text = self.getText()
            self.tag = tag
            if setValue:
                self.setValue(text)

        if self._editorClass() == QtGui.QLineEdit:
            # Update the completer
            if tag in self.insertedValues:
                completionStrings = self.insertedValues[tag][:] # copy the list
            else: completionStrings = []

            if tag != tags.TITLE and tag.isIndexed():
                ext = [str(value) for value in db.allTagValues(tag) if str(value) not in completionStrings]
                completionStrings.extend(ext)

            if len(completionStrings) > 0:
                self._getActualEditor().setCompleter(QtGui.QCompleter(completionStrings))
            else: self._getActualEditor().setCompleter(None)
        
        self.tagChanged.emit(tag)

    def _getActualEditor(self):
        if self.useEditorWidget:
            return self.editor.getEditor()
        else: return self.editor

    def _createEditor(self,tag):
        editor = self._editorClass(tag)() # Create a new instance of that class
        if self.useEditorWidget:
            self.editor = editorwidget.EditorWidget(editor=editor)
            self.editor.valueChanged.connect(self._handleValueChanged)
        else:
            self.editor = editor
            self.editor.editingFinished.connect(self._handleValueChanged)

    def _editorClass(self,tag=None):
        if tag is None:
            tag = self.tag
        if tag.type == tags.TYPE_TEXT:
            return EnhancedTextEdit
        else: return QtGui.QLineEdit
                
    def getText(self):
        if self.useEditorWidget:
            return self.editor.getValue()
        elif isinstance(self.editor,QtGui.QLineEdit):
            return self.editor.text()
        else: return self.editor.toPlainText()

    def getValue(self):
        if not self.tag.isValid(self.getText()):
            return None
        else: return self.tag.type.valueFromString(self.getText())
        
    def setValue(self,value):
        if self.tag.type == tags.TYPE_DATE and isinstance(value,FlexiDate):
            text = FlexiDate.strftime(value)
        else: text = str(value)
        
        if text != self.getText():
            if self.useEditorWidget:
                self.editor.setValue(text)
            elif isinstance(self.editor,QtGui.QLineEdit):
                self.editor.setText(text)
            else: self.editor.setPlainText(text)
            
            if self.tag.isValid(self.getText()):
                self.valueChanged.emit()

    def clear(self):
        self.setValue('')

    def _handleValueChanged(self):
        if self.tag.isValid(self.getText()):
            if not self.valid: # The last value was invalid
                self._getActualEditor().setPalette(QtGui.QPalette()) # use inherited palette
                self.valid = True
                if self.useEditorWidget:
                    self.editor.setFixed(False)
                
            if isinstance(self._getActualEditor(),QtGui.QLineEdit):
                # Add value to insertedValues (which will be shown in the completer)
                if self.tag not in self.insertedValues:
                    self.insertedValues[self.tag] = []
                if self.getText() not in self.insertedValues[self.tag]:
                    # insert at the beginning, so that the most recent values will be at the top of the completer's list.
                    self.insertedValues[self.tag].insert(0,self.getText())
            self.valueChanged.emit()
        else:
            self.valid = False
            palette = self._getActualEditor().palette()
            palette.setColor(QtGui.QPalette.Base,QtGui.QColor(255,112,148))
            self._getActualEditor().setPalette(palette)
            if self.useEditorWidget:
                self.editor.showEditor()
                self.editor.setFixed(True)
