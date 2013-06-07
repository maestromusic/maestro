# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

import functools

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from .. import application, utils, database as db
from ..core import tags
from .misc import lineedits

translate = QtCore.QCoreApplication.translate


class TagLabel(QtGui.QLabel):
    """Specialized label which can contain arbitrary text, but displays the corresponding icon next to the
    name when showing a tagname. If *iconOnly* is True the label will display only the icon if there is one
    (if the current tag does not have an icon or the label does not display a tagname, it will still show the
    text).
    """
    iconSize = QtCore.QSize(24,24) # Size of the icon
    
    def __init__(self,tag=None,parent=None,iconOnly=False):
        """Initialize a new TagLabel. You may specify a tag which is displayed at the beginning and a
        parent.
        """
        QtGui.QLabel.__init__(self,parent)
        self.iconOnly = iconOnly
        self.setTag(tag)
        application.dispatcher.connect(self._handleDispatcher)

    def text(self):
        if self.tag is not None:
            return self.tag.title
        else: return ''
        
    def setText(self,text):
        if text == '':
            self.setTag(None)
        else: self.setTag(tags.fromTitle(text))
        
    def getTag(self):
        """Return the tag which is currently shown or None if no tag is shown."""
        return self.tag
        
    def setTag(self,tag):
        """Set the tag which is shown by this label. If *tag* is None, clear the label."""
        self.tag = tag
        if tag is None:
            self.clear()
        else:
            if tag.iconPath is not None:
                if self.iconOnly:
                    super().setText('<img src="{}" widht="{}" height="{}">'
                                      .format(tag.iconPath,self.iconSize.width(),self.iconSize.height()))
                else: super().setText('<img src="{}" widht="{}" height="{}"> {}'
                                      .format(tag.iconPath,self.iconSize.width(),
                                              self.iconSize.height(),tag.title))
            else:
                if self.iconOnly:
                    # Display only the beginning of the tagname, occupying two times the width of an icon
                    # (in most cases this should suffice to guess the tag).
                    fm = QtGui.QFontMetrics(self.font())
                    text = fm.elidedText(tag.title,Qt.ElideRight,2*self.iconSize.width())
                    self.setToolTip(tag.title)
                else:
                    text = tag.title
                    self.setToolTip(None)
                super().setText(text)
        
    def setIconOnly(self,iconOnly):
        """Set whether the label should use iconOnly-mode: When set it will only display the icon and no text,
        if an icon is available."""
        if iconOnly != self.iconOnly:
            self.iconOnly = iconOnly
            if iconOnly:
                font = self.font()
                font.setPointSize(8)
                self.setFont(font)
            else: self.setFont(QtGui.QApplication.font())
            self.setTag(self.tag)
            
    def _handleDispatcher(self,event):
        """Reload the widget on TagTypeChangedEvents applying to our tag."""
        if isinstance(event,tags.TagTypeChangedEvent) and event.tagType == self.tag:
            self.setTag(self.tag)


class ValueTypeBox(QtGui.QComboBox):
    """Combobox to choose a ValueType for tags. Additionally it has a property 'disableMouseWheel'. If this
    property is set to True the Combobox will not react to WheelEvents. Use this if the combobox is inside
    a ScrollArea and you expect the user to change the value of the box rarely but scroll often.
    """
    disableMouseWheel = False
    typeChanged = QtCore.pyqtSignal(tags.ValueType)
    
    def __init__(self,valueType=None,parent=None):
        QtGui.QComboBox.__init__(self,parent)
        for type in tags.TYPES:
            self.addItem(type.name,type)
        if valueType is not None:
            self.setType(valueType)
        self.currentIndexChanged.connect(self._handleCurrentIndexChanged)
    
    def getType(self):
        """Return the currently selected value type."""
        return self.itemData(self.currentIndex())
    
    def setType(self,newType):
        """Set the currently selected value type."""
        for i in range(self.count()):
            type = self.itemData(i)
            if newType == type:
                self.setCurrentIndex(i)
                return
        raise ValueError("'{}' is not a ValueType.".format(newType))
        
    def wheelEvent(self,wheelEvent):
        if self.disableMouseWheel:
            # Let the parent widget handle it. If that parent is a scrollarea, it will scroll
            wheelEvent.ignore() 
        else: QtGui.QComboBox.wheelEvent(self,wheelEvent)
    
    def _handleCurrentIndexChanged(self,index):
        self.typeChanged.emit(self.getType())
        
        
class TagTypeBox(QtGui.QStackedWidget):
    """A combobox to select a tagtype from those in the tagids table. By default the box will be editable.
    Text entered by the user will be interpreted as tag title
    and allowin this case the box will handle tag titles and if the entered tagname is unknown it will add
    a new tag to the table (querying the user for a type). If the entered text is invalid it will reset the
    box. Thus getTag will always return a valid tag. Use the tagChanged-signal to get informed about
    changes.
    
    Parameters:
    
        - defaultTag: The tag selected at the beginning. If it is None, the first tag will be selected.
        - parent: The parent object.
        - editable: Whether the user can enter arbitrary text into the box.
        - useCoverLabel: If True, the box will be hidden behind a TagLabel, unless it has the focus. This
          feature is for example used by the tageditor.
          
    """
    tagChanged = QtCore.pyqtSignal(tags.Tag)
    
    # This variable is used to prevent handling editingFinished twice (if _handleEditingFinished opens
    # a dialog, the box will loose focus and emit the signal again).
    _dialogOpen = False
    
    def __init__(self,defaultTag=None,parent=None,editable=True,useCoverLabel=False):
        QtGui.QStackedWidget.__init__(self,parent)
        self.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Minimum,QtGui.QSizePolicy.Fixed))
        
        if defaultTag is None:
            self._tag = tags.tagList[0]
        else: self._tag = defaultTag
        
        if useCoverLabel:
            self.label = TagLabel(defaultTag)
            self.addWidget(self.label)
            # Do not accept focus by tabbing when hidden behind a label
            self.setFocusPolicy(Qt.ClickFocus)
        else:
            self.setFocusPolicy(Qt.StrongFocus)
            self.label = None
        
        if editable:
            self.box = EnhancedComboBox()
        else: self.box = QtGui.QComboBox()
        self.box.setInsertPolicy(QtGui.QComboBox.NoInsert)

        self._createItems()

        if editable:
            self.box.editingFinished.connect(self._handleEditingFinished)
        else: self.box.currentIndexChanged.connect(self._handleEditingFinished)
        
        self.addWidget(self.box)
        
        application.dispatcher.connect(self._handleDispatcher)
    
    def _createItems(self):
        """Clear the combobox and refill it with items."""
        self.box.clear()
        for tag in tags.tagList:
            self._addTagToBox(tag)
            if tag == self._tag:
                self.box.setCurrentIndex(self.box.count()-1)
        
        if not self._tag.isInDb():
            self.box.setEditText(self._tag.name)
                        
            self.box.insertSeparator(self.box.count())
            self.box.addItem(self.tr("Add tag to DB..."))
                
    def _addTagToBox(self,tag):
        """Add a tag to the box. Display icon and title if available."""
        if tag.icon is not None:
            self.box.addItem(tag.icon,tag.title,tag)
        else: self.box.addItem(tag.title,tag)            
            
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
            self.box.setEditText(tag.title)
        if tag != self._tag:
            if self._tag.isInDb() and not tag.isInDb():
                self.box.insertSeparator(self.box.count())
                self.box.addItem(self.tr("Add tag to DB..."))
            elif not self._tag.isInDb() and tag.isInDb():
                self.box.removeItem(self.box.count()-1) # Remove "Add tag to DB" 
                self.box.removeItem(self.box.count()-1) # and separator
            self._tag = tag
            self.tagChanged.emit(tag)
    
    def _parseTagFromBox(self):
        """Return the tag that is currently selected. This method uses tags.fromTitle to get a tag 
        from the text in the combobox: If the tag is the title of a tag, that tag will be returned.
        Otherwise tags.get will be used. If the user really wants to create a tag with a name that is the 
        translation of another tag into his language (e.g. he wants to create a 'titel'-tag that is not the
        usual 'title'-tag), he has to quote the tagname (using " or '): inserting "titel" into the combobox 
        will do the job.
        Note that the case of the entered text does not matter; all tags have lowercase names. This method 
        returns None if no tag can be returned, because the name is invalid.
        """
        text = self.box.currentText().strip()
        try:
            if text[0] == text[-1] and text[0] in ['"',"'"]: # Don't translate if the text is quoted
                return tags.get(text[1:-1])
            else: return tags.fromTitle(text)
        except tags.TagValueError: # invalid tagname
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
            # invalid tagname
            self.box.setEditText(self._tag.title) # Reset
            self._dialogOpen = True
            QtGui.QMessageBox.warning(self,self.tr("Invalid tagname"),
                                      self.tr("'{}' is not a valid tagname").format(text))
            self._dialogOpen = False
    
    def keyPressEvent(self,keyEvent):
        if keyEvent.key() == Qt.Key_Escape:
            self.box.setEditText(self._tag.title) # Reset
            self.showLabel()
        else: QtGui.QStackedWidget.keyPressEvent(self,keyEvent)
    
    def _handleDispatcher(self,event):
        """React upon TagTypeChangedEvents and TagTypeOrderChangeEvents from the dispatcher."""
        if isinstance(event,(tags.TagTypeChangedEvent,tags.TagTypeOrderChangeEvent)):
            self._createItems()


class TagTypeButton(QtGui.QPushButton):
    """Button with a menu to choose a tagtype from. When a tagtype has been chosen the signal tagChosen is
    emitted with that tagtype."""
    tagChosen = QtCore.pyqtSignal(tags.Tag)
    
    def __init__(self,text=None):
        if text is None:
            text = translate("TagTypeButton","Add tag")
        super().__init__(text)
        self.setIcon(utils.getIcon("add.png"))
        # Unfortunately there is a large margin on the left
        #https://bugreports.qt-project.org/browse/QTBUG-3624
        self.setMenu(QtGui.QMenu())
        self._fillMenu()
        application.dispatcher.connect(self._handleDispatcher)
        
    def _fillMenu(self):
        """Fill the menu with an action for each tagtype."""
        menu = self.menu()
        menu.clear()
        for tagType in tags.tagList:
            if tagType.icon is not None:
                action = menu.addAction(tagType.icon,tagType.title)
                action.setIconVisibleInMenu(True)
            else: action = menu.addAction(tagType.title)
            action.triggered.connect(functools.partial(self.tagChosen.emit,tagType))
        
        menu.addSeparator()
        action = menu.addAction(self.tr("New tagtype..."))
        action.triggered.connect(self._handleAddTagTypeAction)
        action = menu.addAction(self.tr("Tagmanager..."))
        action.triggered.connect(self._handleManagerButton)
        
    def _handleAddTagTypeAction(self):
        """Handle the last action in the menu: Ask the user to add a tagtype to the database."""
        tagType = AddTagTypeDialog.addTagType()
        if tagType is not None:
            self.tagChosen.emit(tagType)
            
    def _handleManagerButton(self):
        """Open the tagmanager."""
        from . import preferences
        preferences.show('main/tagmanager')
        
    def _handleDispatcher(self,event):
        """React upon TagTypeChangedEvents and TagTypeOrderChangeEvents from the dispatcher."""
        if isinstance(event,(tags.TagTypeChangedEvent,tags.TagTypeOrderChangeEvent)):
            self._fillMenu()
        

class TagValueEditor(QtGui.QWidget):
    """A flexible editor to edit tag values. Depending on the tag type which may change during runtime a
    TagValueEditor will use different widgets as actual editor (QLineEdit, QTextEdit etc.). A TagValueEditor
    can use a HiddenEditor to hide the actual editor behind a label as long as it doesn't have the focus. Set 
    *hideEditor* to True to enable this behavior.
    """
    
    # Dictionary mapping tags to all the values which have been entered in a TagLineEdit during this
    # application. Will be used in the completer.
    insertedValues = {}

    tagChanged = QtCore.pyqtSignal(tags.Tag)
    valueChanged = QtCore.pyqtSignal()
    
    def __init__(self, tag, parent=None, hideEditor=False):
        QtGui.QWidget.__init__(self,parent)
        assert tag is not None
        self.setLayout(QtGui.QStackedLayout()) # doesn't matter...we just need a layout for one child widget
        self.hideEditor = hideEditor
        self.editor = None
        self.tag = None # Create the variable
        self.valid = tag.canConvert('')
        self._emitValueChanged = True
        self.setTag(tag)
        application.dispatcher.connect(self._handleDispatcher)

    def canSwitchTag(self, newTag):
        """Return whether the current value is valid for the given tag, i.e. whether it is possible to
        change the tag of this editor to *newTag*."""
        return newTag.conConvert(self.getText())
        
    def getTag(self):
        """Return the tag type of this editor."""
        return self.tag

    def setTag(self,tag):
        """Set the tag type of this editor. This will change the editor widget if necessary. This won't
        change the value even if it is invalid for the new tag (but the widget will indicate the invalid
        value).
        """
        if tag != self.tag:
            self._setTag(tag)
        
    def _setTag(self,tag):
        """Set the tag type of this editor. Change the internal editor so that it can edit values of the
        given tag."""
        text = self.getText() if self.editor is not None else ''
        
        # Note: type(self._getActualEditor()) != self._editorClass(self.tag)
        # if the value-type of self.tag has just changed.
        if self.tag is None or self._editorClass(tag) != type(self._getActualEditor()):
            # We have to change the editor
            if self.editor is not None:
                self.layout().removeWidget(self.editor)
            
            editor = self._editorClass(tag)() # Create a new instance of that class
            if self.hideEditor:
                from .misc import hiddeneditor
                shrink = self._editorClass(tag) == EnhancedTextEdit
                self.editor = hiddeneditor.HiddenEditor(editor=editor,shrink=shrink)
                self.editor.valueChanged.connect(self._handleValueChanged)
            else:
                self.editor = editor
                self.editor.editingFinished.connect(self._handleValueChanged)
            self.setFocusProxy(self.editor)
            self.layout().addWidget(self.editor)
    
        self.tag = tag
        
        # It may happen that the current value interpreted as value of the new tag should be displayed
        # differently. Therefore after changing the tag we call setValue with the current text.
        # This must not emit a value-changed signal because conceptually only the way the value is displayed
        # changes and not the value itself.
        if tag.canConvert(text):
            # This is 
            self._emitValueChanged = False
            self.setValue(text)
            self._emitValueChanged = True

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
                
    def _handleDispatcher(self,event):
        """Handle dispatcher: On TagTypeChangedEvents we might have to change the editor type.""" 
        if isinstance(event,tags.TagTypeChangedEvent) and event.tagType == self.tag:
            if self._editorClass(self.tag) != type(self._getActualEditor()):
                # _setTag will change the editor type even though the tag stays the same
                self._setTag(self.tag)

    def _getActualEditor(self):
        """Return the actual editor widget (e.g. a QLineEdit)."""
        if self.hideEditor:
            return self.editor.getEditor()
        else: return self.editor

    def _editorClass(self,tag=None):
        """Return a class of widgets suitable to edit values of the given tag (e.g. QLineEdit)."""
        if tag is None:
            tag = self.tag
        if not tag.isInDb() or tag.type == tags.TYPE_VARCHAR:
            return QtGui.QLineEdit
        elif tag.type == tags.TYPE_TEXT:
            return EnhancedTextEdit
        else: return DateLineEdit
                
    def getText(self):
        """Return the current text of this editor. This might be invalid for the current tag type."""
        if self.hideEditor:
            return self.editor.getValue()
        elif isinstance(self.editor,QtGui.QLineEdit):
            return self.editor.text()
        else: return self.editor.toPlainText()

    def getValue(self):
        """Return the current value. Contrary to getText, convert the text according to the current tag type
        (e.g. creating a FlexiDate) and return None if the current text is not valid."""
        try:
            return self.tag.convertValue(self.getText())
        except tags.TagValueError:
            return None
        
    def setValue(self,value):
        """Set the current value. *value* must be either a string or FlexiDate if the current tag type is
        date."""
        if self.tag.type == tags.TYPE_DATE and isinstance(value,utils.FlexiDate):
            text = utils.FlexiDate.strftime(value)
        else: text = str(value)
        
        if text != self.getText():
            if self.hideEditor:
                self.editor.setValue(text)
            elif isinstance(self.editor,QtGui.QLineEdit):
                self.editor.setText(text)
            else: self.editor.setPlainText(text)

    def clear(self):
        """Clear the current value."""
        self.setValue('')

    def _handleValueChanged(self):
        """Handle valueChanged or editingFinished-signals from the actual editor."""
        if self.tag.canConvert(self.getText()):
            if not self.valid: # The last value was invalid
                self._getActualEditor().setPalette(QtGui.QPalette()) # use inherited palette
                self.valid = True
                if self.hideEditor:
                    self.editor.setFixed(False)
                
            if isinstance(self._getActualEditor(),QtGui.QLineEdit):
                # Add value to insertedValues (which will be shown in the completer)
                if self.tag not in self.insertedValues:
                    self.insertedValues[self.tag] = []
                if self.getText() not in self.insertedValues[self.tag]:
                    # insert at the beginning, so that the most recent values will be at the top of the
                    # completer's list.
                    self.insertedValues[self.tag].insert(0,self.getText())
            
            if self._emitValueChanged:
                self.valueChanged.emit()
        else:
            self.valid = False
            palette = self._getActualEditor().palette()
            palette.setColor(QtGui.QPalette.Base,QtGui.QColor(255,112,148))
            self._getActualEditor().setPalette(palette)
            if self.hideEditor:
                self.editor.showEditor()
                self.editor.setFixed(True)


class AddTagTypeDialog(QtGui.QDialog):
    """This dialog allows the user to add a tagtype to the database. To do this, the user has to specify
    name and type and may specify a title and set the private flag. The dialog can be initialized with an
    external tag *tagType*, otherwise the name field will be empty at first. If given, *text* will be
    displayed at the top of the dialog.
    
    After the tag has been added to the database, it is available as attribute 'tagType'. If the user aborted
    the dialog, this attribute is None.

    WARNING: The user is allowed to change the tagname in the dialog and thus the final tagType that was
    added to the database and is stored in the attribute 'tagType' may differ from the argument *tagType*.
    """
    def __init__(self,tagType=None,text=None):
        QtGui.QDialog.__init__(self)
        self.setWindowTitle(self.tr("Add tag type"))
        
        if tagType is not None and tagType.isInDb():
            raise ValueError("Cannot open AddTagTypeDialog for an internal tagtype.")
        self.tagType = None # only set this, if the type has been added to the database
                
        self.setLayout(QtGui.QVBoxLayout())
        
        if text is not None:
            label = QtGui.QLabel(text)
            label.setWordWrap(True)
            self.layout().addWidget(label)
        
        formLayout = QtGui.QFormLayout()
        self.layout().addLayout(formLayout)
            
        self.lineEdit = QtGui.QLineEdit(tagType.name if tagType is not None else '')
        formLayout.addRow(self.tr("Name:"),self.lineEdit)
            
        self.combo = ValueTypeBox()
        formLayout.addRow(self.tr("Type:"),self.combo)
        
        self.titleLineEdit = QtGui.QLineEdit(tagType.name.capitalize() if tagType is not None else '')
        formLayout.addRow(self.tr("Title:"),self.titleLineEdit)
        
        self.privateBox = QtGui.QCheckBox()
        formLayout.addRow(self.tr("Private:"),self.privateBox)
                
        buttonLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(buttonLayout)
        buttonLayout.addStretch()
        
        self.cancelButton = QtGui.QPushButton(self.tr("Cancel"))
        self.cancelButton.clicked.connect(self.reject)
        buttonLayout.addWidget(self.cancelButton)
        
        self.okButton = QtGui.QPushButton(self.tr("OK"))
        self.okButton.clicked.connect(self._handleOk)
        self.okButton.setDefault(True)
        buttonLayout.addWidget(self.okButton)

    def _handleOk(self):
        """Handle OK button: Check if everything is fine and add the type to the database."""
        tagName = self.lineEdit.text()
        if tags.isInDb(tagName):
            QtGui.QMessageBox.warning(self,self.tr("Tag exists already"),
                                      self.tr("There is already a tag named '{}'.").format(tagName))
            return
        if not tags.isValidTagName(tagName):
            QtGui.QMessageBox.warning(self,self.tr("Invalid tagname"),
                                      self.tr("'{}' is not a valid tagname.").format(tagName))
            return
        title = self.titleLineEdit.text()
        if tags.isTitle(title):
            QtGui.QMessageBox.warning(self,self.tr("Title exists already"),
                                      self.tr("There is already a tag with title '{}'.").format(title))
            return
        if len(title) == 0 or title == tagName:
            title = None
        
        try:
            self.tagType = tags.addTagType(tagName,self.combo.getType(),
                                           title=title,private=self.privateBox.isChecked())
        except tags.TagValueError:
            from . import dialogs
            dialogs.warning(self.tr("Cannot add tagtype"),
                            self.tr("The tag already appears in some elements with values that cannot be"
                                    " converted to the chosen type. Change the type or edit those elements."))
        else:
            self.accept()
        
    @classmethod
    def addTagType(cls,tagType=None,text=None):
        """Show an AddTagTypeDialog to allow the user to add a tagtype to the database.  The dialog can be
        initialized with an external tag *tagType*, otherwise the name field will be empty at first. If
        given, *text* will be displayed at the top of the dialog.
        
        Return the tag that was added to the database or None, if the user aborted the dialog.
        
        WARNING: The user is allowed to change the tagtype in the dialog. Thus this method may return a
        different tagType than the argument *tagType*.
        """
        dialog = cls(tagType,text)
        dialog.exec_()
        return dialog.tagType
        
        
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
            self._popup.exec_(event.globalPos())
            self._popup = None
            return True
        return False # don't stop the event
    
    
class DateLineEdit(lineedits.LineEditWithHint):
    """A lineedit with the additional feature that it draws a human readable format string in its right
    corner (if there is enough space. The format string is drawn in gray."""
    def __init__(self,text='',parent=None):
        super().__init__(text,parent)
        self.setRightText(utils.FlexiDate.getHumanReadableFormat())
        

class TagValuePropertiesWidget(QtGui.QWidget):
    """A widget that displays properties of tag values and allows to change them.
    
    The user can choose to:
      - rename all occurences of that value,
      - set or remove a distinguished sort value,
      - select whether the value should be hidden.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtGui.QGridLayout()
        self.label = QtGui.QLabel("")
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label, 0, 0, 1, 2)
        self.changeValueCheckbox = QtGui.QCheckBox(self.tr('rename all occurences:'))
        self.valueEdit = TagValueEditor(tags.TITLE)
        self.changeValueCheckbox.toggled.connect(self.valueEdit.setEnabled)
        layout.addWidget(self.changeValueCheckbox, 1, 0)
        layout.addWidget(self.valueEdit, 1, 1)
        
        self.sortValueCheckbox = QtGui.QCheckBox(self.tr('distinguished sort value:'))

        layout.addWidget(self.sortValueCheckbox, 2, 0)
        self.sortEdit = QtGui.QLineEdit()
        self.sortValueCheckbox.toggled.connect(self.sortEdit.setEnabled)
        self.sortValueCheckbox.toggled.connect(self._handleSortCheckboxToggled)
        layout.addWidget(self.sortEdit, 2, 1)
        self.hiddenCheckbox = QtGui.QCheckBox(self.tr('value is hidden'))
        layout.addWidget(self.hiddenCheckbox, 3, 0)
        
        self.setLayout(layout)
    
    def _handleSortCheckboxToggled(self, checked):
        """If the user enables the checkbox to set a custom sort value, this method
        tries to guess the sort value by splitting the tag value at the last space
        and exchanging the two parts."""
        if checked:
            if self.origSortValue is None and self.sortEdit.text() == "":
                names = self.valueEdit.getText().rsplit(' ')
                if len(names) >= 2:
                    if names[0].lower() == "the":
                        guess = " ".join(names[1:]) + ", " + names[0]
                    else:
                        guess = names[-1] + ", " + " ".join(names[:-1])
                    self.sortEdit.setText(guess)
                
    def setValue(self, tag, valueId):
        self.tag = tag
        self.valueId = valueId
        self.orig_hidden = db.hidden(tag, valueId)
        self.origSortValue = db.sortValue(tag, valueId)
        self.origValue = db.valueFromId(tag, valueId)
        self.valueEdit.setTag(tag)
        self.valueEdit.setEnabled(False)
        self.changeValueCheckbox.setChecked(False)
        self.valueEdit.setValue(self.origValue)
        
        self.label.setText(self.tr('editing {0} value: {1}').format(tag, self.origValue))
        if self.origSortValue is None:
            self.sortEdit.setText("")
            self.sortValueCheckbox.setChecked(False)
            self.sortEdit.setEnabled(False)
        else:
            self.sortEdit.setText(self.origSortValue)
            self.sortEdit.setEnabled(True)
            self.sortValueCheckbox.setChecked(True)
        self.hiddenCheckbox.setChecked(self.orig_hidden)
    
    def inputAcceptable(self):
        if self.changeValueCheckbox.isChecked() and self.valueEdit.getValue() is None:
            from .dialogs import warning
            warning(self.tr("Invalid Tag Value"),
                    self.tr("Please enter a valid tag value."))
            return False
        return True

    def commit(self):
        from ..core import tagcommands
        if self.changeValueCheckbox.isChecked() and self.valueEdit.getValue() != self.origValue:
            tagcommands.renameTagValue(self.tag, self.origValue, self.valueEdit.getValue())
            self.origValue = self.valueEdit.getValue()
            self.valueId = db.idFromValue(self.tag, self.origValue)
        if self.sortValueCheckbox.isChecked():
            if self.sortEdit.text() != self.origSortValue:
                command = tagcommands.ChangeSortValueCommand(self.tag, self.valueId, self.origSortValue,
                                                        self.sortEdit.text())
                application.stack.push(command)
        elif self.origSortValue is not None:
            command = tagcommands.ChangeSortValueCommand(self.tag, self.valueId, self.origSortValue, None)
            application.stack.push(command)
        if self.hiddenCheckbox.isChecked() != self.orig_hidden:
            command = tagcommands.HiddenAttributeCommand(self. tag, self.valueId,
                                                      self.hiddenCheckbox.isChecked())
            application.stack.push(command)
    
    @staticmethod
    def showDialog(tag, valueId):
        dialog = QtGui.QDialog()
        dialog.setLayout(QtGui.QVBoxLayout())
        
        tvp = TagValuePropertiesWidget()
        dialog.layout().addWidget(tvp)
        
        buttonLine = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel | QtGui.QDialogButtonBox.Ok)        
        dialog.layout().addWidget(buttonLine)
        tvp.setValue(tag, valueId)
        
        buttonLine.accepted.connect(lambda : dialog.accept() if tvp.inputAcceptable() else None)
        buttonLine.rejected.connect(dialog.reject)
        dialog.exec_()
        if dialog.result() == QtGui.QDialog.Accepted:
            tvp.commit()
            
