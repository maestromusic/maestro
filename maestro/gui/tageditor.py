# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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

import os.path, functools

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from maestro import utils, config, logging, stack, widgets
from maestro.core import tags, levels, urls
from maestro.models import tageditor as tageditormodel, simplelistmodel, flageditor as flageditormodel
from maestro.gui import singletageditor, tagwidgets, flageditor, dialogs
from maestro.gui.misc import widgetlist
        
translate = QtCore.QCoreApplication.translate


class TagEditorWidget(widgets.Widget):
    """A TagEditorWidget contains of a row of buttons, a TagEditorLayout forming the actual tageditor and
    a flageditor. The TagEditorLayout displays pairs of a TagTypeBox and a SingleTagEditor - one for each
    tag present in the tageditor. The displays the tagtype while the SingleTagEditor shows all records for
    this tag.
    
    Arguments:
    
        - includeContents: Whether the "Include contents" button should be pressed down at the beginning.
        - stack: The stack that should be used. If None, the applications's stack is used.
        
    """
    # This hack is necessary to ignore changes in the tagboxes while changing the tag programmatically
    # confer _handleTagChanged and _handleTagChangedByUser.
    _ignoreHandleTagChangedByUser = False
    
    def __init__(self, state=None, stack=None, useGlobalSelection=True, **args):
        super().__init__(**args)
        self.level = None
        self.elements = None
        self.elementsWithContents = None
        self.setAcceptDrops(True)
        
        self.model = tageditormodel.TagEditorModel(stack=stack)
        self.model.tagInserted.connect(self._handleTagInserted)
        self.model.tagRemoved.connect(self._handleTagRemoved)
        self.model.tagChanged.connect(self._handleTagChanged)
        self.model.resetted.connect(self._handleReset)

        self.flagModel = flageditormodel.FlagEditorModel()

        self.selectionManager = widgetlist.SelectionManager()
        # Do not allow the user to select ExpandLines
        self.selectionManager.isSelectable = \
            lambda wList, widget: not isinstance(widget, singletageditor.ExpandLine)
        
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setSpacing(1)
        self.layout().setContentsMargins(0,0,0,0)
        self.toolBar = QtWidgets.QToolBar()
        self.layout().addWidget(self.toolBar)

        self.levelLabel = QtWidgets.QLabel()
        self.toolBar.addWidget(self.levelLabel)
                
        self.addButton = tagwidgets.TagTypeButton()
        self.addButton.tagChosen.connect(self._handleAddRecord)
        self.toolBar.addWidget(self.addButton)
        self.removeButton = QtWidgets.QToolButton()
        self.removeButton.setIcon(utils.images.icon('list-remove'))
        self.removeButton.clicked.connect(self._handleRemoveSelected)
        self.toolBar.addWidget(self.removeButton)
        
        self.includeContentsButton = QtWidgets.QToolButton()
        self.includeContentsButton.setCheckable(True)
        self.includeContentsButton.setChecked(state is not None and state.get('includeContents', False))
        self.includeContentsButton.setToolTip(self.tr("Include all contents"))
        self.includeContentsButton.setIcon(utils.images.icon('recursive'))
        self.includeContentsButton.toggled.connect(self._updateElements)
        self.toolBar.addWidget(self.includeContentsButton)
        
        scrollArea = QtWidgets.QScrollArea()
        scrollArea.setWidgetResizable(True)
        self.layout().addWidget(scrollArea, 1)
            
        self.viewport = QtWidgets.QWidget()
        self.tagEditorLayout = TagEditorLayout(self.viewport)
        scrollArea.setWidget(self.viewport)

        self.flagWidget = QtWidgets.QWidget()
        self.flagWidget.setLayout(QtWidgets.QHBoxLayout())
        self.flagWidget.layout().setContentsMargins(0,0,0,0)
        self.layout().addWidget(self.flagWidget)
        
        self.flagEditor = flageditor.FlagEditor(self.flagModel) 
        self.layout().addWidget(self.flagEditor)
        
        self.singleTagEditors = {}
        self.tagBoxes = {}
        
        if useGlobalSelection:
            from . import selection
            selection.changed.connect(self._handleSelectionChanged)
            self._handleSelectionChanged(selection.getGlobalSelection())
        
    def saveState(self):
        return {'includeContents': self.includeContents}
        
    def _handleSelectionChanged(self, selection):
        """React to changes to the global selection: Load the elements of the selected wrappers
        into the TagEditorWidget."""
        if selection is None or not selection.hasElements():
            self.setElements(None, [])
        else:
            self.useElementsFromSelection(selection)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(config.options.gui.mime) or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        mimeData = event.mimeData()
        
        if mimeData.hasFormat(config.options.gui.mime):
            allElements = (w.element for w in mimeData.wrappers())
            level = mimeData.level
        elif mimeData.hasUrls():
            allElements = levels.real.collect(url for url in event.mimeData().urls()
                           if url.isValid() and url.scheme() == 'file' and os.path.exists(url.toLocalFile()))
            level = levels.real
        else:
            logging.warning(__name__, "Invalid drop event (supports only {})"
                                      .format(", ".join(mimeData.formats())))
            return
        
        elements = []
        ids = set()
        for element in allElements:
            if element.id not in ids:
                ids.add(element.id)
                elements.append(element)
        
        self.setElements(level, elements)
        event.acceptProposedAction()
        
    def setElements(self, level, elements, elementsWithContents=None):
        """Set the elements that are edited in the tageditor. *level* is the level that contains the
        elements. *elements* and *elementsWithContents* are the lists of elements that will be edited when
        the "Include contents" button is not pressed / pressed, respectively.
        """
        if level in (levels.real, None):
            self.levelLabel.setPixmap(utils.images.icon('drive-harddisk').pixmap(20))
            self.levelLabel.setToolTip(self.tr("Normal mode"))
        else:
            self.levelLabel.setPixmap(utils.images.icon('accessories-text-editor').pixmap(20))
            self.levelLabel.setToolTip(self.tr("Editor mode: Changes are only written on editor commit."))
        self.level = level
        self.elements = elements
        if elementsWithContents is not None and elementsWithContents != elements:
            self.elementsWithContents = elementsWithContents
        else: self.elementsWithContents = None
        self.includeContentsButton.setEnabled(self.elementsWithContents is not None)
        self._updateElements()
        
    def useElementsFromSelection(self, selection):
        """Use the elements in the given Selection in the tageditor."""
        self.setElements(selection.level,
                         list(selection.elements(recursive=False)),
                         list(selection.elements(recursive=True)))
        
    def _updateElements(self):
        """Update the element display."""
        if self.elementsWithContents is not None and self.includeContents:
            elements = self.elementsWithContents
        else: elements = self.elements
        if elements is not None:
            self.model.setElements(self.level, elements)
            self.flagModel.setElements(self.level, elements)
        
    def _insertSingleTagEditor(self, row, tag):
        """Insert a TagTypeBox and a SingleTagEditor for *tag* at the given row."""
        # Create the tagbox
        self.tagBoxes[tag] = SmallTagTypeBox(tag, True) #TODO
        self.tagBoxes[tag].tagChanged.connect(self._handleTagChangedByUser)
        
        # Create the Tag-Editor
        self.singleTagEditors[tag] = singletageditor.SingleTagEditor(self, tag, self.model)
        self.singleTagEditors[tag].commonList.setSelectionManager(self.selectionManager)
        self.singleTagEditors[tag].uncommonList.setSelectionManager(self.selectionManager)
        
        self.tagEditorLayout.insertPair(row, self.tagBoxes[tag], self.singleTagEditors[tag])

    def _removeSingleTagEditor(self, tag):
        """Remove the TagTypeBox and SingleTagEditor for the given tag."""
        self.tagEditorLayout.removePair(tag)

        # Tidy up
        # When changing a tag via the tagbox we are about to remove the widget having the current focus.
        # This leads to errors ('Underlying C++ object has been deleted' in focusOutEvent). Fortunately this
        # is fixed using deleteLater.
        self.tagBoxes[tag].deleteLater()
        del self.tagBoxes[tag]
        tagEditor = self.singleTagEditors[tag]
        tagEditor.commonList.setSelectionManager(None)
        tagEditor.uncommonList.setSelectionManager(None)
        tagEditor.setParent(None)
        del self.singleTagEditors[tag]

    def _handleReset(self):
        """Handle the resetted-signal of the model."""
        for tag in list(self.singleTagEditors.keys()): # dict will change
            self._removeSingleTagEditor(tag)
        for tag in self.model.getTags():
            self._insertSingleTagEditor(len(self.singleTagEditors), tag)
        
        # Enable / disable buttons
        count = len(self.model.getElements())
        self.addButton.setEnabled(count > 0)
        self.removeButton.setEnabled(count > 0)
        self.flagEditor.setEnabled(count > 0)
    
    def _handleError(self, error):
        """Handle TagWriteErrors raised in methods of the model."""
        dialogs.warning(self.tr("Tag write error"),
                        self.tr("An error ocurred: {}").format(error),
                        parent=self)
        
    def _handleAddRecord(self, tag=None):
        """Handle the add record button and context menu entry: Open a RecordDialog. If *tag* is given it
        will be selected by default in this dialog."""
        dialog = RecordDialog(self, self.model.getElements(), defaultTag=tag)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            try:
                self.model.addRecord(dialog.getRecord())
            except urls.TagWriteError as e:
                self._handleError(e)

    def _handleRemoveSelected(self):
        """Handle the remove selected button and context menu entry."""
        records = self._getSelectedRecords()
        if len(records) > 0:
            try:
                self.model.removeRecords(records)
            except urls.TagWriteError as e:
                self._handleError(e)
        
    # Note that the following _handle-functions only add new SingleTagEditors or remove SingleTagEditors
    # which have become empty. Unless they are newly created or removed, the editors are updated in their
    # own _handle-functions.
    def _handleTagInserted(self, pos, tag):
        """Handle tagInserted-signal from the model."""
        self._insertSingleTagEditor(pos, tag)
        
    def _handleTagRemoved(self, tag):
        """Handle tagRemoved-signal from the model."""
        self._removeSingleTagEditor(tag)

    def _handleTagChanged(self, oldTag, newTag):
        """Handle tagChanged-signal from the model."""
        for adict in (self.tagBoxes, self.singleTagEditors):
            # Change key from oldTag to newTag
            widget = adict[oldTag]
            del adict[oldTag]
            assert newTag not in adict
            adict[newTag] = widget
            self._ignoreHandleTagChangedByUser = True
            widget.setTag(newTag)
            self._ignoreHandleTagChangedByUser = False
    
    def _handleTagChangedByUser(self, changedTag):
        """Handle changes to the TagTypeBoxes by the user."""
        # This method is also called when the box' tag is changed programmatically (e.g. when we reset the
        # tagBox inside this event handler to the old tag).
        # To avoid changing the model in such cases we use this flag.
        if self._ignoreHandleTagChangedByUser:
            return
        self._ignoreHandleTagChangedByUser = True
        
        # First we have to get the tagBox responsible for this event and its tag
        tagBox = self.sender()
        oldTag = None
        for tag, widget in self.tagBoxes.items():
            if widget == tagBox:
                oldTag = tag
                break
        assert oldTag is not None
        newTag = tagBox.getTag()

        # Do not allow external tags in internal elements
        if not newTag.isInDb() and any(element.isInDb() for record in self.model.getRecords(oldTag)
                                                        for element in record.elementsWithValue):
            text = self.tr("You must add tagtypes to the database before adding such tags to elements "
                           "within the database.")
            newTag = tagwidgets.AddTagTypeDialog.addTagType(newTag, text)
            if newTag is None: # user aborted the dialog
                tagBox.setTag(oldTag)
                return
        
        # First reset the box, because a number of things might go wrong. Also, if oldTag is finally
        # removed (because there is already a SingleTagEditor for newTag) the box is searched via oldTag.     
        tagBox.setTag(oldTag)
        
        try:
            result = self.model.changeTag(oldTag, newTag)
        except urls.TagWriteError as e:
            self._handleError(e)
            
        if result:
            tagBox.setTag(newTag)
        else:
            # This means that changeTag failed because some values could not be converted to the new tag.
            # Reset the box
            QtWidgets.QMessageBox.warning(self, self.tr("Invalid value"),
                                      self.tr("At least one value is invalid for the new type."))
        self._ignoreHandleTagChangedByUser = False
                
    def contextMenuEvent(self, contextMenuEvent, record=None):
        menu = QtWidgets.QMenu(self)

        menu.addAction(self.model.stack.createUndoAction())
        menu.addAction(self.model.stack.createRedoAction())
        menu.addSeparator()
        
        addRecordAction = QtWidgets.QAction(self.tr("Add record..."), self)
        tag = record.tag if record is not None else None
        addRecordAction.triggered.connect(lambda: self._handleAddRecord(tag))
        menu.addAction(addRecordAction)
        
        removeSelectedAction = QtWidgets.QAction(self.tr("Remove selected"), self)
        removeSelectedAction.triggered.connect(self._handleRemoveSelected)
        menu.addAction(removeSelectedAction)

        if record is not None:
            editRecordAction = QtWidgets.QAction(self.tr("Edit record..."), self)
            editRecordAction.triggered.connect(lambda: self._handleEditRecord(record))
            menu.addAction(editRecordAction)
            
        selectedRecords = self._getSelectedRecords()
        action = menu.addAction(self.tr("Extend to all elements"))
        action.setEnabled(not all(record.isCommon() for record in selectedRecords))
        action.triggered.connect(functools.partial(self._extendRecords, selectedRecords))
            
        # Fancy stuff
        fancyMenu = menu.addMenu(self.tr("Fancy stuff"))

        if len(selectedRecords) > 0:
            if len(selectedRecords) > 1 and all(r.tag.type == tags.TYPE_VARCHAR for r in selectedRecords):
                commonPrefix = utils.strings.commonPrefix([record.value for record in selectedRecords],
                                                          separated=True)
                
                if len(commonPrefix) > 0:
                    action = fancyMenu.addAction(self.tr("Edit common start..."))
                    action.triggered.connect(self._editCommonStart)
                    if len(commonPrefix) > 0:
                        rests = [record.value[len(commonPrefix):] for record in selectedRecords]
                        if any(utils.strings.numberFromPrefix(rest)[0] is not None for rest in rests):
                            newValues = []
                            for record, rest in zip(selectedRecords, rests):
                                prefix = utils.strings.numberFromPrefix(rest)[1]
                                newValues.append(record.value[len(commonPrefix)+len(prefix):])
                            if all(record.tag.isValid(value)
                                   for record, value in zip(selectedRecords, newValues)):
                                action = fancyMenu.addAction(
                                                        self.tr("Remove common start (including numbers)"))
                                action.triggered.connect(functools.partial(self._editMany,
                                                                           selectedRecords, newValues))
                        else:
                            newValues = [record.value[len(commonPrefix):] for record in selectedRecords]
                            if all(record.tag.isValid(value)
                                   for record, value in zip(selectedRecords, newValues)):
                                action = fancyMenu.addAction(self.tr("Remove common start"))
                                action.triggered.connect(functools.partial(self._editMany,
                                                                           selectedRecords, newValues))
                else:
                    action = fancyMenu.addAction(self.tr("Add common start..."))
                    action.triggered.connect(self._editCommonStart)
                    if any(utils.strings.numberFromPrefix(r.value)[0] is not None for r in selectedRecords):
                        # Remove the prefix returned in the second tuple part
                        newValues = [r.value[len(utils.strings.numberFromPrefix(r.value)[1]):]
                                     for r in selectedRecords]
                        if all(record.tag.isValid(value)
                               for record, value in zip(selectedRecords, newValues)):
                            action = fancyMenu.addAction(self.tr("Remove numbers from beginning"))
                            action.triggered.connect(functools.partial(self._editMany,
                                                                       selectedRecords, newValues))
            for separator in self.model.getPossibleSeparators(selectedRecords):
                # Note: getPossibleSeparators returns nothing if a date record is selected
                # & are used to specify mnemonics
                action = fancyMenu.addAction(self.tr("Separate at '{}'")
                                             .format(separator.replace('&', '&&')))
                action.triggered.connect(functools.partial(self._splitMany, selectedRecords, separator))

        fancyMenu.setEnabled(len(fancyMenu.actions()) > 0)
        
        menu.popup(contextMenuEvent.globalPos())
        
    def _extendRecords(self, records):
        """Handle 'extend records' action from context menu."""
        try:
            self.model.extendRecords(records)
        except urls.TagWriteError as e:
            self._handleError(e)
            
    def _editMany(self, records, newValues):
        """Handle 'edit many' action from context menu."""
        try:
            self.model.editMany(records, newValues)
        except urls.TagWriteError as e:
            self._handleError(e)
            
    def _splitMany(self, records, separator):
        """Handle 'split' action from context menu."""
        try:
            self.model.splitMany(records, separator)
        except urls.TagWriteError as e:
            self._handleError(e)

    def _editCommonStart(self):
        """Handle 'edit common start' action from context menu."""
        selectedRecords = [editor.getRecord() for editor in self.selectionManager.getSelectedWidgets()]
        commonStart = utils.strings.commonPrefix(str(record.value) for record in selectedRecords)
        text, ok = QtWidgets.QInputDialog.getText(self, self.tr("Edit common start"),
                         self.tr("Insert a new text which will replace the common start "
                                 "of all selected records:"),
                         text=commonStart)
        if ok:
            newValues = [text+record.value[len(commonStart):] for record in selectedRecords]
            if all(record.tag.isValid(value) for record, value in zip(selectedRecords, newValues)):
                self._editMany(selectedRecords, newValues)
            else: dialogs.warning(self.tr("Invalid value"), self.tr("One or more values are invalid."))
    
    def _handleEditRecord(self, record):
        """Handle 'edit record' action from context menu."""
        dialog = RecordDialog(self, self.model.getElements(), record=record)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            try:
                self.model.changeRecord(record, dialog.getRecord())
            except urls.TagWriteError as e:
                self._handleError(e)
        
    def _getSelectedRecords(self):
        """Return all records that are selected and visible (i.e. not hidden by a collapsed ExpandLine."""
        return [editor.getRecord() for editor in self.selectionManager.getSelectedWidgets()
                                # Filter out ExpandLines and hidden records
                                if isinstance(editor, singletageditor.RecordEditor) and editor.isVisible()]

    @property
    def includeContents(self):
        return self.includeContentsButton.isChecked()
    
    @includeContents.setter
    def includeContents(self, value):
        self.includeContentsButton.setChecked(value)


widgetClass = widgets.addClass(
    id = "tageditor",
    name = translate("Tageditor", "Tageditor"),
    icon = utils.images.icon('tageditor'),
    theClass = TagEditorWidget,
    unique = True,
    areas = 'dock',
    preferredDockArea = 'right'
)


class RecordDialog(QtWidgets.QDialog):
    """Dialog to edit a single record. Parameters are:
    
        - *parent*: The parent widget
        - *elements*: The list of elements that can be selected in the dialog
        - *record*: If set the dialog will be initialized with the tag, value and selected elements from
          the record.
        - *tag*: If set and *record* is None, this tag will be displayed at the beginning.
    
    \ """
    def __init__(self, parent, elements, record=None, defaultTag=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.setWindowTitle(self.tr("Add tag value"))
        assert len(elements) > 0
        
        if record is not None:
            defaultTag = record.tag
        self.typeEditor = tagwidgets.TagTypeBox(defaultTag=defaultTag)
        self.typeEditor.tagChanged.connect(self._handleTagChanged)
        
        self.valueEditor = tagwidgets.TagValueEditor(self.typeEditor.getTag())
        if record is not None:
            self.valueEditor.setValue(record.value)
            
        self.elementsBox = QtWidgets.QListView(self)
        self.elementsBox.setModel(simplelistmodel.SimpleListModel(elements, lambda el: el.getTitle()))
        self.elementsBox.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        for i, element in enumerate(elements):
            if record is None or element in record.elementsWithValue:
                self.elementsBox.selectionModel().select(self.elementsBox.model().index(i, 0),
                                                         QtCore.QItemSelectionModel.Select)
                
        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Ok)
        buttonBox.rejected.connect(self.reject)
        buttonBox.accepted.connect(self._handleOkButton)
        
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)
        firstLineLayout = QtWidgets.QHBoxLayout()
        secondLineLayout = QtWidgets.QHBoxLayout()
        layout.addLayout(firstLineLayout)
        layout.addLayout(secondLineLayout)
        firstLineLayout.addWidget(QtWidgets.QLabel(self.tr("Type: "), self))
        firstLineLayout.addWidget(self.typeEditor)
        firstLineLayout.addStretch(1)
        secondLineLayout.addWidget(QtWidgets.QLabel(self.tr("Value: "), self))
        secondLineLayout.addWidget(self.valueEditor)
        layout.addWidget(QtWidgets.QLabel(self.tr("Elements: "), self))
        layout.addWidget(self.elementsBox)

        layout.addWidget(buttonBox)
        
        if defaultTag is None:
            self.typeEditor.setFocus(Qt.PopupFocusReason)
        else: self.valueEditor.setFocus(Qt.PopupFocusReason)
    
    def _handleOkButton(self):
        """Check whether at least one element is selected and the current value is valid and if so, exit."""
        if not self.elementsBox.selectionModel().hasSelection():
            QtWidgets.QMessageBox.warning(self, self.tr("No element selected"),
                                      self.tr("You must select at lest one element."))
            return
        
        # Do not allow external tags in internal elements
        tagType = self.typeEditor.getTag()
        if not tagType.isInDb() and any(element.isInDb() for element in self._getSelectedElements()):
            text = self.tr("You must add tagtypes to the database before adding such tags to elements "
                           "within the database.")
            newTag = tagwidgets.AddTagTypeDialog.addTagType(tagType, text)
            if newTag is None: # user aborted the dialog
                return
            if newTag != tagType: # user changed the tagtype
                self.valueEditor.setTag(newTag)
                self.typeEditor.setTag(newTag)
                tagType = newTag
            
        if self.valueEditor.getValue() is None: # valueEditor.getValue returns None if the value is invalid
            QtWidgets.QMessageBox.warning(self, self.tr("Invalid value"), self.tr("The given value is invalid."))
            return
        
        self.accept()
        
    def getRecord(self):
        """Return a record with the data from the dialog."""
        allElements = self.elementsBox.model().getItems()
        return tageditormodel.Record(self.typeEditor.getTag(), self.valueEditor.getValue(),
                                     allElements, self._getSelectedElements())

    def _getSelectedElements(self):
        """Return the elements selected for the record."""
        allElements = self.elementsBox.model().getItems()
        return tuple(allElements[i] for i in range(len(allElements))
                                 if self.elementsBox.selectionModel().isRowSelected(i, QtCore.QModelIndex()))
        
    def _handleTagChanged(self, tag):
        """Change the tag of the ValueEditor."""
        self.valueEditor.setTag(tag)
        
    
class TagEditorDialog(QtWidgets.QDialog):
    """The tageditor as dialog. It uses its own level and commits the level when the dialog is accepted."""
    def __init__(self, includeContents=None, parent=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.setWindowTitle(self.tr("Edit tags"))
        self.resize(600, 450) #TODO: make this cleverer
        self.stack = stack.createSubstack(modalDialog=True)
        self.level = None
        if includeContents is None:
            includeContents = config.storage.gui.tag_editor_include_contents
            
        self.setLayout(QtWidgets.QVBoxLayout())
        self.tagedit = TagEditorWidget(state={'includeContents': includeContents},
                                       stack=self.stack,
                                       useGlobalSelection=False,
                                       widgetClass=widgetClass)
        self.layout().addWidget(self.tagedit)
        
        style = QtWidgets.QApplication.style()
        
        buttonLayout = QtWidgets.QHBoxLayout()
        self.layout().addLayout(buttonLayout)
        
        undoButton = QtWidgets.QPushButton(self.tr("Undo"))
        undoButton.clicked.connect(self.stack.undo)
        self.stack.canUndoChanged.connect(undoButton.setEnabled)
        undoButton.setEnabled(False)
        buttonLayout.addWidget(undoButton)
        redoButton = QtWidgets.QPushButton(self.tr("Redo"))
        redoButton.clicked.connect(self.stack.redo)
        self.stack.canRedoChanged.connect(redoButton.setEnabled)
        redoButton.setEnabled(False)
        buttonLayout.addWidget(redoButton)
        
        resetButton = QtWidgets.QPushButton(style.standardIcon(QtWidgets.QStyle.SP_DialogResetButton),
                                             self.tr("Reset"))
        resetButton.clicked.connect(self._handleReset)
        cancelButton = QtWidgets.QPushButton(style.standardIcon(QtWidgets.QStyle.SP_DialogCancelButton),
                                             self.tr("Cancel"))
        cancelButton.clicked.connect(self.reject)
        commitButton = QtWidgets.QPushButton(style.standardIcon(QtWidgets.QStyle.SP_DialogSaveButton),
                                         self.tr("OK"))
        commitButton.clicked.connect(self.accept)
        buttonLayout.addWidget(resetButton)
        buttonLayout.addStretch()
        buttonLayout.addWidget(cancelButton)
        buttonLayout.addWidget(commitButton)
        
    def setElements(self, level, elements, elementsWithContents=None):
        """Set the elements in the tageditor. See TagEditorWidget.setElements."""
        if elementsWithContents is not None and elementsWithContents != elements:
            self.level = levels.Level("TagEditor", level, elements=elementsWithContents, stack=self.stack)
            # Get the copies on the new level
            elements = [self.level[element.id] for element in elements]
            elementsWithContents = self.level.elements.values()
        else:
            self.level = levels.Level("TagEditor", level, elements=elements, stack=self.stack)
            # Get the copies on the new level
            elements = self.level.elements.values()
            elementsWithContents = None
        self.tagedit.setElements(self.level, elements, elementsWithContents)
       
    def useElementsFromSelection(self, selection):
        """Use the elements in the given Selection in the tageditor."""
        self.setElements(selection.level,
                         selection.elements(recursive=False),
                         selection.elements(recursive=True))
        
    def reject(self):
        self.stack.closeSubstack(self.stack)
        super().reject()
        
    def accept(self):
        try:
            self.stack.closeSubstack(self.stack)
            # make sure that the commit is added via the application stack
            self.level.stack = stack.stack
            self.level.commit()
            super().accept()
            config.storage.gui.tag_editor_include_contents = self.tagedit.includeContentsButton.isChecked()
        except urls.TagWriteError as e:
            e.displayMessage()
            self.level.stack = self.stack
    
    def _handleReset(self):
        """Handle clicks on the reset button: Reload all elements and clear the stack."""
        ids = list(self.level.elements.keys())
        self.level.elements = {}
        elements = self.level.collect(ids)
        self.stack.resetSubstack(self.stack)
        self.tagedit.setElements(self.level, elements)


class SmallTagTypeBox(tagwidgets.TagTypeBox):
    """Special TagTypeBox for the tageditor. Contrary to regular StackedWidgets it will consume only the
    space necessary to display the current widget. Usually this is a TagLabel and thus much smaller than a
    combobox.
    """
    def __init__(self, tag, iconOnly, parent=None):
        super().__init__(tag, parent, useCoverLabel=True)
        self.currentChanged.connect(self.updateGeometry)
        self.label.setIconOnly(iconOnly)
    
    def sizeHint(self):
        return self.currentWidget().sizeHint()
    
    def minimumSizeHint(self):
        return self.currentWidget().minimumSizeHint()
    
    def setIconOnly(self, iconOnly):
        """Set whether the label should use its iconOnly-mode. Confer TagLabel.setIconOnly."""
        self.label.setIconOnly(iconOnly)
              

class TagEditorLayout(QtWidgets.QLayout):
    """Layout for the TagEditor. It may contain several columns each of which contain several pairs
    consisting of a TagTypeBox (left) and a SingleTagEditor (right).
    
    Currently TagEditorLayout always uses only one column.
    """
    innerHSpace = 5
    columnSpacing = 10
    rowSpacing = 1
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContentsMargins(2,2,2,2)
        self._columnCount = 1
        self._minColumnWidth = 200
        self._pairs = []
        
        # itemAt must return QLayoutItems and when we return an item without keeping a reference to it,
        # we'll get a segfault. Thus we additionally store the items.
        self._items = []
        
    def count(self):
        return 2*len(self._pairs)
    
    def itemAt(self, index):
        if index >= self.count():
            return None
        else: return self._items[index // 2][index % 2]
    
    def insertPair(self, row, tagBox, singleTagEditor):
        """Insert pair of *tagBox* and *singleTagEditor* into the layout at the given row."""
        self.addChildWidget(tagBox)
        self.addChildWidget(singleTagEditor)
        self._pairs.insert(row, (tagBox, singleTagEditor))
        self._items.insert(row, (QtWidgets.QWidgetItem(tagBox), QtWidgets.QWidgetItem(singleTagEditor)))
        self.invalidate() # this is also called by for example QBoxLayout::addItem
        
    def removePair(self, tag):
        """Remove the pair the (currently) belongs to tag *tag* from the layout."""
        for i, pair in enumerate(self._pairs):
            tagBox, singleTagEditor = pair
            if tagBox.getTag() == tag:
                del self._pairs[i]
                del self._items[i]
                self.invalidate() # this is also called by for example QLayout::removeItem
                return
        raise ValueError("Tag '{}' is not present in the tageditor".format(tag.name))
    
    def minimumSize(self):
        return self.sizeHint()
    
    def sizeHint(self):
        return QtCore.QSize(*self.doLayout(really=False))
        
    def setGeometry(self, rect):
        self.doLayout(really=True, outerRect=rect)
        
    def doLayout(self, really, outerRect=None):
        """Helper function for sizeHint and setGeometry: Layout all contents to *outerRect* and return the
        width and height that is used in the end. If *really* is False the layout is only computed but
        not performed (for sizeHint)."""
        contentsMargins = self.getContentsMargins()
        if len(self._pairs) == 0:
            return contentsMargins[0] + contentsMargins[2], contentsMargins[1] + contentsMargins[3]
        if really:
            availableWidth = outerRect.width() - contentsMargins[0] - contentsMargins[2]
        
        tbSizeHints = []
        steSizeHints = []
        heights = []
        widths = []
        for tagBox, singleTagEditor in self._pairs:
            hint1 = tagBox.sizeHint()
            hint2 = singleTagEditor.sizeHint()
            tbSizeHints.append(hint1)
            steSizeHints.append(hint2)
            widths.append(hint1.width() + self.innerHSpace + hint2.width())
            heights.append(max(hint1.height(), hint2.height()))
        
        rowsInColumns = self._computeColumns(self._columnCount, heights)
        columnCount = len(rowsInColumns)
        
        columnWidths = []
        columnHeights = []
        
        # Compute width of columns
        i = 0
        for rowCount in rowsInColumns:
            columnWidths.append(max(self._minColumnWidth, max(widths[i:i+rowCount])))
            i += rowCount
        
        # If some horizontal space is left, distribute it evenly
        if really and sum(columnWidths) + (columnCount-1) * self.columnSpacing < availableWidth:
            remainingSpace = availableWidth - sum(columnWidths) - (columnCount-1) * self.columnSpacing
            for i in range(columnCount):
                columnWidths[i] += remainingSpace // columnCount
                if i < remainingSpace % columnCount:
                    columnWidths[i] += 1  
            
        x = contentsMargins[0]
        i = 0
        for colIndex, rowCount in enumerate(rowsInColumns):
            y = contentsMargins[1]
            tbWidth = max(tbSizeHints[j].width() for j in range(i, i+rowCount))
            steWidth = columnWidths[colIndex] - tbWidth - self.innerHSpace
            for _ in range(rowCount):
                tagBox, singleTagEditor = self._pairs[i]
                
                if really:
                    rect = QtCore.QRect(x, y, tbWidth, tbSizeHints[i].height())
                    tagBox.setGeometry(rect)
                
                    rect = QtCore.QRect(x+tbWidth+self.innerHSpace, y,
                                        steWidth, max(tbSizeHints[i].height(), steSizeHints[i].height()))
                    singleTagEditor.setGeometry(rect)
                
                y += heights[i] + self.rowSpacing
                i += 1
            
            columnHeights.append(y)
            x += columnWidths[colIndex] + self.columnSpacing
            
        x += contentsMargins[2]
        return x, max(columnHeights) + contentsMargins[3]
            
    def _computeColumns(self, columnCount, heights):
        """Given the number of columns and a list of heights of the pairs that should be distributed to the
        columns, return a list storing how many pairs should be put in each column."""
        if len(heights) == 0:
            return []
        
        columns = [0]
        
        perColumn = sum(heights) / columnCount
        
        currentHeight = 0
        for height in heights:
            if columns[-1] == 0 or len(columns) == columnCount \
                    or currentHeight + self.rowSpacing + 0.5 * height <= perColumn:
                columns[-1] += 1
                currentHeight += self.rowSpacing + height
            else:
                columns.append(1)
                currentHeight =  height
            
        return columns
