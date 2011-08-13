#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#
from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from .. import tags, utils, database as db, modify
from ..gui.misc import editorwidget
from ..gui import dialogs


class TagLabel(QtGui.QLabel):
    """Specialized label which can contain arbitrary text, but displays the corresponding icons next to the
    name when showing tagnames.
    """
    iconSize = QtCore.QSize(24,24) # Size of the icon
    
    def __init__(self,tag=None,parent=None):
        """Initialize a new TagLabel. You may specify a tag which is displayed at the beginning and a
        parent.
        """
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
        
    def getTag(self):
        """Return the tag which is currently shown or None if no tag is shown."""
        return self.tag
        
    def setTag(self,tag):
        """Set the tag which is shown by this label. If *tag* is None, clear the label."""
        self.tag = tag
        if tag is None:
            self.clear()
        else:
            if tag.iconPath() is not None:
                QtGui.QLabel.setText(self,'<img src="{}" widht="{}" height="{}"> {}'
                                    .format(tag.iconPath(),self.iconSize.width(),
                                            self.iconSize.height(),tag.translated()))
            else: QtGui.QLabel.setText(self,tag.translated())
        
        
class TagTypeBox(QtGui.QStackedWidget):
    """A combobox to select a tagtype from those in the tagids table. By default the box will be editable
    and in this case the box will handle tag translations and if the entered tagname is unknown it will add
    a new tag to the table (querying the user for a type). If the entered text is invalid it will reset the
    box. Thus getTag will always return a valid tag. Use the tagChanged-signal to get informed about
    changes.
    
    Parameters:
    
        - defaultTag: The tag selected at the beginning. If it is None, the first tag will be selected.
        - parent: The parent object.
        - editable: Whether the box is editable.
        - useCoverLabel: If True, the box will be hidden behind a TagLabel, unless it has the focus. This
          feature is for example used by the tageditor.
    
    \ """
    tagChanged = QtCore.pyqtSignal(tags.Tag)
    
    # This variable is used to prevent handling editingFinished twice (if _handleEditingFinished opens
    # a dialog, the box will loose focus and emit the signal again).
    _dialogOpen = False
    
    def __init__(self,defaultTag = None,parent = None,editable=True,useCoverLabel=False):
        QtGui.QStackedWidget.__init__(self,parent)
        self.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Minimum,QtGui.QSizePolicy.Fixed))
        self.setFocusPolicy(Qt.StrongFocus)
        self._tag = defaultTag
        
        if useCoverLabel:
            self.label = TagLabel(defaultTag)
            self.addWidget(self.label)
        else: self.label = None
        
        if editable:
            self.box = EnhancedComboBox()
        else: self.box = QtGui.QComboBox()
        self.box.setInsertPolicy(QtGui.QComboBox.NoInsert)

        for tag in tags.tagList:
            # If defaultTag is None, select the first tag
            if self._tag is None:
                self._tag = tag
                self.box.setCurrentIndex(0)
            self._addTagToBox(tag)
            if tag == defaultTag:
                self.box.setCurrentIndex(self.box.count()-1)

        if editable:
            self.box.editingFinished.connect(self._handleEditingFinished)
        else: self.box.currentIndexChanged.connect(self._handleEditingFinished)
        
        self.addWidget(self.box)
        
        modify.dispatcher.newTagAdded.connect(self._handleNewTagAdded)
    
    def _addTagToBox(self,tag):
        """Add a tag to the box. Display icon and translation if available."""
        if tag.iconPath() is not None:
            self.box.addItem(QtGui.QIcon(tag.iconPath()),tag.translated())
        else: self.box.addItem(tag.translated())
        
    def showLabel(self):
        """Display the label and hide the editor."""
        if self.label is not None:
            self.setCurrentWidget(self.label)
            self.setFocusProxy(None) # or we won't receive focusInEvents
    
    def showBox(self):
        """Display the editor and hide the label."""
        self.setCurrentWidget(self.box)
        self.setFocusProxy(self.box)

    def getTag(self):
        """Return the currently selected tag. TagTypeBox will ensure that this is always a valid tag."""
        return self._tag
    
    def setTag(self,tag):
        """Set the currently selected tag."""
        assert(isinstance(tag,tags.Tag))
        if self.label is not None and tag != self.label.getTag():
            self.label.setTag(tag)
        if tag != self._parseTagFromBox():
            self.box.setEditText(tag.translated())
        if tag != self._tag:
            self._tag = tag
            self.tagChanged.emit(tag)
    
    def _parseTagFromBox(self):
        """Return the tag that is currently selected. This method uses tags.fromTranslation to get a tag 
        from the text in the combobox: If the tag is the translation of a tagname, that tag will be returned.
        Otherwise tags.get will be used. If the user really wants to create a tag with a name that is the 
        translation of another tag into his language (e.g. he wants to create a 'titel'-tag that is not the
        usual 'title'-tag), he has to quote the tagname (using " or '): inserting "titel" into the combobox 
        will do the job.
        Note that the case of the entered text does not matter; all tags have lowercase names. This method 
        returns None if no tag can be generated, because e.g. the text is not a valid tagname.
        """
        text = self.box.currentText().strip()
        try:
            if text[0] == text[-1] and text[0] in ['"',"'"]: # Don't translate if the text is quoted
                return tags.get(text[1:-1])
            else: return tags.fromTranslation(text)
        except tags.UnknownTagError:
            return None
        
    def focusInEvent(self,focusEvent):
        # focusInEvents are used to switch to the box.
        if self.currentWidget() == self.label:
            self.showBox()
            self.box.setFocus(focusEvent.reason())
        QtGui.QStackedWidget.focusInEvent(self,focusEvent)
    
    def _handleEditingFinished(self):
        """Handle editingFinished signal from EnhancedComboBox if editable is True or the currentIndexChanged
        signal from QComboBox otherwise."""
        if self._dialogOpen:
            return
        
        tag = self._parseTagFromBox()
        if tag is not None:
            self.setTag(tag)
            self.showLabel()
        else:
            text = self.box.currentText().strip()
            if text[0] == text[-1] and text[0] in ['"',"'"]:
                text = text[1:-1]
            if not tags.isValidTagname(text):
                self.box.setEditText(self._tag.translated()) # Reset
                self._dialogOpen = True
                QtGui.QMessageBox.warning(self,self.tr("Invalid tagname"),
                                          self.tr("'{}' is not a valid tagname").format(text))
                self._dialogOpen = False
            else:
                self._dialogOpen = True
                type = dialogs.NewTagDialog.queryTagType(text)
                self._dialogOpen = False
                if type is not None:
                    newTag = tags.addTag(text,type)
                    self._addTagToBox(newTag)
                    self.setTag(newTag)
                    self.showLabel()
                else:
                    self.box.setEditText(self._tag.translated()) # Reset
    
    def keyPressEvent(self,keyEvent):
        if keyEvent.key() == Qt.Key_Escape:
            self.box.setEditText(self._tag.translated()) # Reset
            self.showLabel()
        else: QtGui.QStackedWidget.keyPressEvent(self,keyEvent)
    
    def _handleNewTagAdded(self,tag):
        """React upon newTagAdded-signals from the dispatcher. Those are emitted when a new tag is added to
        the database."""
        if self.box.findText(tag.translated(),Qt.MatchFixedString) < 0:
            self._addTagToBox(tag)


class TagValueEditor(QtGui.QWidget):
    #TODO: Comments
    
    # Dictionary mapping tags to all the values which have been entered in a TagLineEdit during this
    # application. Will be used in the completer.
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
        else:
            # It may happen that the current value interpreted as value of the new tag should be displayed
            # differently. Therefore after changing the tag we invoke setValue with the current value.
            text = self.getText()
            self.tag = tag
            if setValue:
                self.setValue(text)

        if self._editorClass() == QtGui.QLineEdit:
            # Update the completer
            if tag in self.insertedValues:
                completionStrings = self.insertedValues[tag][:] # copy the list
            else: completionStrings = []

            if tag.type == tags.TYPE_VARCHAR and tag != tags.TITLE:
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
        if self.tag.type == tags.TYPE_DATE and isinstance(value,utils.FlexiDate):
            text = utils.FlexiDate.strftime(value)
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
                    # insert at the beginning, so that the most recent values will be at the top of the
                    # completer's list.
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


class EnhancedComboBox(QtGui.QComboBox):
    """Enhanced version of QtGui.QComboBox which has an editingFinished-signal like QLineEdit."""
    editingFinished = QtCore.pyqtSignal()
    _popup = None # The lineedit's contextmenu while it is shown
    
    def __init__(self,parent=None):
        QtGui.QComboBox.__init__(self,parent)
        self.setEditable(True)
        self.lineEdit().installEventFilter(self)
        
    def _emit(self):
        if not self.view().isVisible() and self._popup is None:
            self.editingFinished.emit()
        
    def focusOutEvent(self,focusEvent):
        self._emit()
        QtGui.QComboBox.focusOutEvent(self,focusEvent)
    
    def keyPressEvent(self,keyEvent):
        if keyEvent.key() == Qt.Key_Return or keyEvent.key() == Qt.Key_Enter:
            self._emit()
        QtGui.QComboBox.keyPressEvent(self,keyEvent)
        
    def eventFilter(self,object,event):
        if event.type() == QtCore.QEvent.ContextMenu and object == self.lineEdit():
            self._popup = self.lineEdit().createStandardContextMenu()
            action = self._popup.exec_(event.globalPos())
            self._popup = None
            return True
        return False # don't stop the event
    