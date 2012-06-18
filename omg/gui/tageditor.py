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

import os.path

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from .. import strutils, utils, config, logging, modify
from ..core import tags, levels
from ..core.elements import File
from ..models import tageditor as tageditormodel, simplelistmodel, flageditor as flageditormodel
from ..gui import singletageditor, tagwidgets, mainwindow, editor, flageditor, dialogs
from ..gui.misc import widgetlist, dynamicgridlayout


translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)


class TagEditorDock(QtGui.QDockWidget):
    """DockWidget containing the TagEditor."""
    def __init__(self,parent=None,state=None,location=None):
        QtGui.QDockWidget.__init__(self,parent)
        self.setWindowTitle(self.tr("Tageditor"))
        if location is not None:
            vertical = location.floating or location.area in [Qt.LeftDockWidgetArea,Qt.RightDockWidgetArea]
        else: vertical = False # Should not happen
        self.dockLocationChanged.connect(self._handleLocationChanged)
        self.topLevelChanged.connect(self._handleLocationChanged)
            
        self.setAcceptDrops(True)
        
        self.editorWidget = TagEditorWidget(vertical=vertical,dock=self)
        self.setWidget(self.editorWidget)
        
        self.loadRecursively = True
        if state is not None:
            if 'loadRecursively' in state:
                self.loadRecursively = bool(state['loadRecursively'])
        
        from . import selection
        selection.changed.connect(self._handleSelectionChanged)
        
    def saveState(self):
        return {'loadRecursively': self.loadRecursively}
        
    def _handleLocationChanged(self,area):
        """Handle changes in the dock's position."""
        vertical = self.isFloating() or area in [Qt.LeftDockWidgetArea,Qt.RightDockWidgetArea]
        self.editorWidget.setVertical(vertical)
    
    def _handleSelectionChanged(self,nodeSelection):
        """React to changes to the global selection: Load the elements of the selected wrappers
        into the TagEditorWidget."""
        if not nodeSelection.hasWrappers():
            return
        elements = list(nodeSelection.elements(recursive=self.loadRecursively))
        self.editorWidget.setElements(nodeSelection.level,elements)
        
    def dragEnterEvent(self,event):
        if event.mimeData().hasFormat(config.options.gui.mime) or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self,event):
        mimeData = event.mimeData()
        
        if mimeData.hasFormat(config.options.gui.mime):
            allElements = (w.element for w in mimeData.getWrappers())
            level = mimeData.level
        elif mimeData.hasUrls():
            allElements = levels.real.getFromPaths(url for url in event.mimeData().urls()
                           if url.isValid() and url.scheme() == 'file' and os.path.exists(url.toLocalFile()))
            level = levels.real
        else:
            logger.warning("Invalid drop event (supports only {})".format(", ".join(mimeData.formats())))
            return
        
        elements = []
        ids = set()
        for element in allElements:
            if element.id not in ids:
                ids.add(element.id)
                elements.append(element)
        
        self.editorWidget.setElements(level,elements)
        event.acceptProposedAction()
        
        
mainwindow.addWidgetData(mainwindow.WidgetData(
        id="tageditor",
        name=translate("Tageditor","Tageditor"),
        theClass = TagEditorDock,
        central=False,
        dock=True,
        default=True,
        unique=True,
        preferredDockArea=Qt.BottomDockWidgetArea))
    
    
class TagEditorDialog(QtGui.QDialog):
    #TODO rewrite so that it uses its own level
    def __init__(self,level,elements,parent=None):
        QtGui.QDialog.__init__(self,parent)
        return #disable
        self.setLayout(QtGui.QVBoxLayout())
        self.tagedit = TagEditorWidget(level,elements)
        self.layout().addWidget(self.tagedit)
        self.setWindowTitle(self.tr("Edit tags"))
        self.resize(600,450) #TODO: make this cleverer
        
        style = QtGui.QApplication.style()
        
        buttonLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(buttonLayout)
        
        self.undoButton = QtGui.QPushButton(self.tr("Undo"))
        self.redoButton = QtGui.QPushButton(self.tr("Redo"))
        self.resetButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogResetButton),
                                             self.tr("Reset"))
        self.cancelButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogCancelButton),
                                             self.tr("Cancel"))
        self.cancelButton.clicked.connect(self.reject)
        self.commitButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogSaveButton),
                                              self.tr("OK"))
        buttonLayout.addWidget(self.undoButton)
        buttonLayout.addWidget(self.redoButton)
        buttonLayout.addWidget(self.resetButton)
        buttonLayout.addStretch()
        buttonLayout.addWidget(self.cancelButton)
        buttonLayout.addWidget(self.commitButton)
        
        
class TagEditorWidget(QtGui.QWidget):
    # This hack is necessary to ignore changes in the tagboxes while changing the tag programmatically
    # confer _handleTagChanged and _handleTagChangedByUser.
    _ignoreHandleTagChangedByUser = False
    
    def __init__(self,level=None,elements=None,vertical=False,stack=None,dock=None):
        QtGui.QWidget.__init__(self)
        self.vertical = None # will be set in setVertical below
        self.dock = dock
        
        self.model = tageditormodel.TagEditorModel(stack=stack)
        self.model.tagInserted.connect(self._handleTagInserted)
        self.model.tagRemoved.connect(self._handleTagRemoved)
        self.model.tagChanged.connect(self._handleTagChanged)
        self.model.resetted.connect(self._handleReset)

        self.flagModel = flageditormodel.FlagEditorModel(stack=stack)
        #self.flagModel.resetted.connect(self._checkFlagEditorVisibility)
        #self.flagModel.recordInserted.connect(self._checkFlagEditorVisibility)
        #self.flagModel.recordRemoved.connect(self._checkFlagEditorVisibility)

        self.selectionManager = widgetlist.SelectionManager()
        # Do not allow the user to select ExpandLines
        self.selectionManager.isSelectable = \
            lambda wList,widget: not isinstance(widget,singletageditor.ExpandLine)
        
        self.setLayout(QtGui.QVBoxLayout())
        self.layout().setSpacing(0)
        self.layout().setContentsMargins(0,0,0,0)
        self.topLayout = QtGui.QHBoxLayout()
        # Spacings and margins are inherited. Reset the horizontal values for topLayout
        style = QtGui.QApplication.style()
        self.topLayout.setSpacing(style.pixelMetric(style.PM_LayoutHorizontalSpacing))
        self.topLayout.setContentsMargins(style.pixelMetric(style.PM_LayoutLeftMargin),0,
                                          style.pixelMetric(style.PM_LayoutRightMargin),0)
        self.layout().addLayout(self.topLayout)

        self.levelLabel = QtGui.QLabel()
        self.topLayout.addWidget(self.levelLabel)
        
        # Texts will be set in _changeLayout because they are only displayed in horizontal mode
        self.addButton = tagwidgets.TagTypeButton()
        self.addButton.tagChosen.connect(self._handleAddRecord)
        self.topLayout.addWidget(self.addButton)
        self.removeButton = QtGui.QPushButton()
        self.removeButton.setIcon(utils.getIcon("remove.png"))
        self.removeButton.clicked.connect(self._handleRemoveSelected)
        self.topLayout.addWidget(self.removeButton)
        
        self.horizontalFlagEditor = flageditor.FlagEditor(self.flagModel,vertical=False)
        self.topLayout.addWidget(self.horizontalFlagEditor,1)
        # This stretch will be activated in vertical mode to fill the place of the horizontal flageditor
        self.topLayout.addStretch(0)
        
        self.optionButton = QtGui.QPushButton()
        self.optionButton.setIcon(utils.getIcon('options.png'))
        self.optionButton.clicked.connect(self._handleOptionButton)
        self.topLayout.addWidget(self.optionButton)
        
        scrollArea = QtGui.QScrollArea()
        scrollArea.setWidgetResizable(True)
        self.layout().addWidget(scrollArea,1)
            
        self.viewport = QtGui.QWidget()
        self.viewport.setLayout(QtGui.QVBoxLayout())
        self.viewport.layout().setContentsMargins(2,2,2,2)
        self.tagEditorLayout = dynamicgridlayout.DynamicGridLayout()
        self.tagEditorLayout.setColumnStretch(1,1) # Stretch the column holding the values
        self.tagEditorLayout.setSpacing(1)
        self.viewport.layout().addLayout(self.tagEditorLayout)
        self.viewport.layout().addStretch()
        scrollArea.setWidget(self.viewport)

        self.flagWidget = QtGui.QWidget()
        self.flagWidget.setLayout(QtGui.QHBoxLayout())
        self.flagWidget.layout().setContentsMargins(0,0,0,0)
        self.layout().addWidget(self.flagWidget)
        
        # Vertical mode of the flageditor is not used
        self.verticalFlagEditor = flageditor.FlagEditor(self.flagModel,vertical=False)   
        self.layout().addWidget(self.verticalFlagEditor)
        
        self.singleTagEditors = {}
        self.tagBoxes = {}
        
        self.setVertical(vertical)
        
        
        if elements is None:
            elements = []
        self.setElements(level,elements)
    
    def setVertical(self,vertical):
        """Set whether this tageditor should be displayed in vertical model."""
        if vertical == self.vertical:
            return
        for box in self.tagBoxes.values():
            box.setIconOnly(vertical)
            
        if vertical:
            for button in ['addButton','removeButton']:
                getattr(self,button).setText('')
        else:
            self.addButton.setText(self.tr("Add tag"))
            self.removeButton.setText(self.tr("Remove selected"))
        
        self.horizontalFlagEditor.setVisible(not vertical)
        # The place left by the horizontalFlagEditor is filled by the stretch we put there
        self.topLayout.setStretch(self.topLayout.count()-2,int(vertical))
        self.verticalFlagEditor.setVisible(vertical)
            
        self.vertical = vertical
            
    def setElements(self,level,elements):
        """Set the elements that are edited in the tageditor. *level* is the level that contains the
        elements."""
        self.levelLabel.setPixmap(utils.getPixmap('real.png' if level == levels.real or level is None
                                                   else 'editor.png'))
        self.model.setElements(level,elements)
        self.flagModel.setElements(level,elements)
        
    def _insertSingleTagEditor(self,row,tag):
        self.tagEditorLayout.insertRow(row)
        
        # Create the tagbox
        self.tagBoxes[tag] = SmallTagTypeBox(tag,self.vertical)
        self.tagBoxes[tag].tagChanged.connect(self._handleTagChangedByUser)
        self.tagEditorLayout.addWidget(self.tagBoxes[tag],row,0)
        
        # Create the Tag-Editor
        self.singleTagEditors[tag] = singletageditor.SingleTagEditor(self,tag,self.model)
        self.singleTagEditors[tag].commonList.setSelectionManager(self.selectionManager)
        self.singleTagEditors[tag].uncommonList.setSelectionManager(self.selectionManager)
        self.tagEditorLayout.addWidget(self.singleTagEditors[tag],row,1)

    def _removeSingleTagEditor(self,tag):
        # Simply removing the items would leave an empty row. Thus we use DynamicGridLayout.removeRow.
        # First we have to find the row
        row = None
        for r in range(self.tagEditorLayout.rowCount()):
            if self.tagEditorLayout.itemAtPosition(r,0).widget() == self.tagBoxes[tag]:
                row = r
                break
        assert row is not None
        self.tagEditorLayout.removeRow(row)

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
        for tag in list(self.singleTagEditors.keys()): # dict will change
            self._removeSingleTagEditor(tag)
        for tag in self.model.getTags():
            self._insertSingleTagEditor(len(self.singleTagEditors),tag)
        
        # Enable / disable buttons
        count = len(self.model.getElements())
        self.addButton.setEnabled(count > 0)
        self.removeButton.setEnabled(count > 0)
        self.horizontalFlagEditor.setEnabled(count > 0)
        self.verticalFlagEditor.setEnabled(count > 0)
        
    def _handleAddRecord(self,tag=None):
        dialog = RecordDialog(self,self.model.getElements(),defaultTag=tag)
        if dialog.exec_() == QtGui.QDialog.Accepted:
            self.model.addRecord(dialog.getRecord())

    def _handleRemoveSelected(self):
        records = self._getSelectedRecords()
        if len(records) > 0:
            self.model.removeRecords(records)
            
    # Note that the following _handle-functions only add new SingleTagEditors or remove SingleTagEditors
    # which have become empty. Unless they are newly created or removed, the editors are updated in their
    # own _handle-functions.
    def _handleTagInserted(self,pos,tag):
        self._insertSingleTagEditor(pos,tag)
        
    def _handleTagRemoved(self,tag):
        self._removeSingleTagEditor(tag)

    def _handleTagChanged(self,oldTag,newTag):
        for adict in (self.tagBoxes,self.singleTagEditors):
            # Change key from oldTag to newTag
            widget = adict[oldTag]
            del adict[oldTag]
            assert newTag not in adict
            adict[newTag] = widget
            self._ignoreHandleTagChangedByUser = True
            widget.setTag(newTag)
            self._ignoreHandleTagChangedByUser = False
    
    def _handleTagChangedByUser(self,changedTag):
        if self._ignoreHandleTagChangedByUser:
            return
        # First we have to get the tagBox responsible for this event and its tag
        tagBox = self.sender()
        oldTag = None
        for tag,widget in self.tagBoxes.items():
            if widget == tagBox:
                oldTag = tag
                break
        assert oldTag is not None
        newTag = tagBox.getTag()

        # If changeTag fails, then reset the box
        if not self.model.changeTag(oldTag,newTag):
            QtGui.QMessageBox.warning(self,self.tr("Invalid value"),
                                      self.tr("At least one value is invalid for the new type."))
            # reset the editor...unfortunately this emits valueChanged again
            tagBox.tagChanged.disconnect(self._handleTagChangedByUser)
            tagBox.setTag(oldTag)
            tagBox.tagChanged.connect(self._handleTagChangedByUser)
        
    def _handleSave(self):
        #TODO
        """Handle the save button (only if ''saveDirectly'' is True)."""
        if self.model.saveDirectly:
            raise RuntimeError("You must not call save in a TagEditor that saves directly.") 
        
        if not all(singleTagEditor.isValid() for singleTagEditor in self.singleTagEditors.values()):
            QtGui.QMessageBox.warning(self,self.tr("Invalid value"),self.tr("At least one value is invalid."))
        else:
            application.push(modify.commands.TagFlagUndoCommand(self.level,
                                                                self.model.getChanges(),
                                                                self.flagModel.getChanges(),
                                                                elements = self.model.getElements()))
            self.saved.emit()
                
    def contextMenuEvent(self,contextMenuEvent,record=None):
        menu = QtGui.QMenu(self)

        menu.addAction(self.model.stack.createUndoAction(self,self.tr("Undo")))
        menu.addAction(self.model.stack.createRedoAction(self,self.tr("Redo")))
        menu.addSeparator()
        
        addRecordAction = QtGui.QAction(self.tr("Add tag..."),self)
        tag = record.tag if record is not None else None
        addRecordAction.triggered.connect(lambda: self._handleAddRecord(tag))
        menu.addAction(addRecordAction)
        
        removeSelectedAction = QtGui.QAction(self.tr("Remove selected"),self)
        removeSelectedAction.triggered.connect(self._handleRemoveSelected)
        menu.addAction(removeSelectedAction)

        if record is not None:
            editRecordAction = QtGui.QAction(self.tr("Edit record..."),self)
            editRecordAction.triggered.connect(lambda: self._handleEditRecord(record))
            menu.addAction(editRecordAction)
            
        # Fancy stuff
        fancyMenu = menu.addMenu(self.tr("Fancy stuff"))
        selectedRecords = self._getSelectedRecords()

        if len(selectedRecords) > 0:
            if not all(record.isCommon() for record in selectedRecords):
                action = fancyMenu.addAction(self.tr("Extend to all elements"))
                action.triggered.connect(lambda: self.model.extendRecords(selectedRecords))
            
            if len(selectedRecords) > 1 and all(r.tag.type == tags.TYPE_VARCHAR for r in selectedRecords):
                commonPrefix = strutils.commonPrefix(record.value for record in selectedRecords)
                
                if len(commonPrefix) > 0:
                    action = fancyMenu.addAction(self.tr("Edit common start..."))
                    action.triggered.connect(self._editCommonStart)
                    
                    if commonPrefix[-1].upper() == "I":
                        # Bugfix: If up to four pieces using roman numbers are selected, the commonPrefix
                        # will contain an 'I'. Consequently the 'I' is missing in the rest and
                        # numberFromPrefix won't find a number in the first piece.
                        prefixLength = len(commonPrefix) - 1
                    else: prefixLength = len(commonPrefix)
                    rests = [str(record.value)[prefixLength:] for record in selectedRecords]
                    if any(strutils.numberFromPrefix(rest)[0] is not None for rest in rests):
                        action = fancyMenu.addAction(self.tr("Remove common start (including numbers)"))
                        newValues = []
                        for record,rest in zip(selectedRecords,rests):
                            number,prefix = strutils.numberFromPrefix(rest)
                            if number is not None:
                                newValues.append(record.value[prefixLength+len(prefix):])
                            else: newValues.append(record.value[prefixLength:])
                        action.triggered.connect(lambda: self.model.editMany(selectedRecords,newValues))
                    else:
                        action = fancyMenu.addAction(self.tr("Remove common start"))
                        newValues = [record.value[len(commonPrefix):] for record in selectedRecords]
                        action.triggered.connect(lambda: self.model.editMany(selectedRecords,newValues))
                else:
                    if any(strutils.numberFromPrefix(r.value)[0] is not None for r in selectedRecords):
                        action = fancyMenu.addAction(self.tr("Remove numbers from beginning"))
                        # Remove the prefix returned in the second tuple part
                        newValues = [r.value[len(strutils.numberFromPrefix(r.value)[1]):]
                                        for r in selectedRecords]
                        action.triggered.connect(lambda: self.model.editMany(selectedRecords,newValues))
            for separator in self.model.getPossibleSeparators(selectedRecords):
                action = fancyMenu.addAction(self.tr("Separate at '{}'").format(separator))
                action.triggered.connect(lambda: self.model.splitMany(selectedRecords,separator))

        menu.popup(contextMenuEvent.globalPos())

    def _editCommonStart(self):
        selectedRecords = [editor.getRecord() for editor in self.selectionManager.getSelectedWidgets()]
        commonStart = strutils.commonPrefix(str(record.value) for record in selectedRecords)
        text,ok = QtGui.QInputDialog.getText(self,self.tr("Edit common start"),
                         self.tr("Insert a new text will replace the common start of all selected records:"),
                         text=commonStart)
        if ok:
            newValues = [text+record.value[len(commonStart):] for record in selectedRecords]
            self.model.editMany(selectedRecords,newValues)
    
    def _handleEditRecord(self,record):
        dialog = RecordDialog(self,self.model.getElements(),record=record)
        if dialog.exec_() == QtGui.QDialog.Accepted:
            self.model.changeRecord(record,dialog.getRecord())

    #def _checkFlagEditorVisibility(self):
    #    """Set the flag editor's visibility depending on whether flags are present."""
    #    self.flagWidget.setVisible(not self.flagModel.isEmpty())
        
    def _getSelectedRecords(self):
        """Return all records that are selected and visible (i.e. not hidden by a collapsed ExpandLine."""
        return [editor.getRecord() for editor in self.selectionManager.getSelectedWidgets()
                                # Filter out ExpandLines and hidden records
                                if isinstance(editor,singletageditor.RecordEditor) and editor.isVisible()]
        
    def _handleOptionButton(self):
        """Open the option dialog."""
        dialog = OptionDialog(self.optionButton,self)
        dialog.show()


class RecordDialog(QtGui.QDialog):
    """Dialog to edit a single record. Parameters are:
    
        - *parent*: The parent widget
        - *elements*: The list of elements that can be selected in the dialog
        - *record*: If set the dialog will be initialized with the tag, value and selected elements from
          the record.
        - *tag*: If set and *record* is None, this tag will be displayed at the beginning.
    
    \ """
    def __init__(self,parent,elements,record=None,defaultTag=None):
        QtGui.QDialog.__init__(self,parent)
        self.setWindowTitle(self.tr("Add tag value"))
        assert len(elements) > 0
        
        if record is not None:
            defaultTag = record.tag
        self.typeEditor = tagwidgets.TagTypeBox(defaultTag=defaultTag)
        self.typeEditor.tagChanged.connect(self._handleTagChanged)
        
        self.valueEditor = tagwidgets.TagValueEditor(self.typeEditor.getTag())
        if record is not None:
            self.valueEditor.setValue(record.value)
            
        self.elementsBox = QtGui.QListView(self)
        self.elementsBox.setModel(simplelistmodel.SimpleListModel(elements,lambda el: el.getTitle()))
        self.elementsBox.setSelectionMode(QtGui.QAbstractItemView.MultiSelection)
        for i,element in enumerate(elements):
            if record is None or element in record.elementsWithValue:
                self.elementsBox.selectionModel().select(self.elementsBox.model().index(i,0),
                                                         QtGui.QItemSelectionModel.Select)
                
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel | QtGui.QDialogButtonBox.Ok)
        buttonBox.rejected.connect(self.reject)
        buttonBox.accepted.connect(self._handleOkButton)
        
        layout = QtGui.QVBoxLayout()
        self.setLayout(layout)
        firstLineLayout = QtGui.QHBoxLayout()
        secondLineLayout = QtGui.QHBoxLayout()
        layout.addLayout(firstLineLayout)
        layout.addLayout(secondLineLayout)
        firstLineLayout.addWidget(QtGui.QLabel(self.tr("Type: "),self))
        firstLineLayout.addWidget(self.typeEditor)
        firstLineLayout.addStretch(1)
        secondLineLayout.addWidget(QtGui.QLabel(self.tr("Value: "),self))
        secondLineLayout.addWidget(self.valueEditor)
        layout.addWidget(QtGui.QLabel(self.tr("Elements: "),self))
        layout.addWidget(self.elementsBox)

        layout.addWidget(buttonBox)
        
        if defaultTag is None:
            self.typeEditor.setFocus(Qt.PopupFocusReason)
        else: self.valueEditor.setFocus(Qt.PopupFocusReason)
    
    def _handleOkButton(self):
        """Check whether at least one element is selected and the current value is valid and if so, exit."""
        if self.elementsBox.selectionModel().hasSelection():
            if self.valueEditor.getValue() is not None:
                self.accept()
            else: QtGui.QMessageBox.warning(self,self.tr("Invalid value"),
                                            self.tr("The given value is invalid."))
        else: QtGui.QMessageBox.warning(self,self.tr("No element selected"),
                                        self.tr("You must select at lest one element."))
        
    def getRecord(self):
        """Return a record with the data from the dialog."""
        allElements = self.elementsBox.model().getItems()
        selectedElements = [allElements[i] for i in range(len(allElements))
                                if self.elementsBox.selectionModel().isRowSelected(i,QtCore.QModelIndex())]
        return tageditormodel.Record(self.typeEditor.getTag(),self.valueEditor.getValue(),
                                     allElements,selectedElements)

    def _handleTagChanged(self,tag):
        """Change the tag of the ValueEditor."""
        self.valueEditor.setTag(tag)


class SmallTagTypeBox(tagwidgets.TagTypeBox):
    """Special TagTypeBox for the tageditor. Contrary to regular StackedWidgets it will consume only the
    space necessary to display the current widget. Usually this is a TagLabel and thus much smaller than a
    combobox. In the tageditor's vertical mode the labels' iconOnly-mode is used to save further space.
    """
    def __init__(self,tag,iconOnly,parent = None):
        super().__init__(tag,parent,useCoverLabel=True)
        self.currentChanged.connect(self.updateGeometry)
        self.label.setIconOnly(iconOnly)
    
    def sizeHint(self):
        return self.currentWidget().sizeHint()
    
    def minimumSizeHint(self):
        return self.currentWidget().minimumSizeHint()
    
    def setIconOnly(self,iconOnly):
        """Set whether the label should use its iconOnly-mode. Confer TagLabel.setIconOnly."""
        self.label.setIconOnly(iconOnly)
        
        
class OptionDialog(dialogs.FancyPopup):
    """Option dialog for a TagEditorWidget."""
    def __init__(self,parent,tagEditor):
        super().__init__(parent)
        self.tagEditor = tagEditor
        layout = QtGui.QVBoxLayout(self)
        
        # loadRecursively is an attribute of the tageditor's dock widget. Do not show the option if the
        # tageditor is displayed as dialog (without dock)
        if tagEditor.dock is not None:
            loadRecursivelyBox = QtGui.QCheckBox(self.tr("Load elements recursively"))
            loadRecursivelyBox.setChecked(tagEditor.dock.loadRecursively)
            loadRecursivelyBox.stateChanged.connect(self._handleLoadRecursivelyBox)
            layout.addWidget(loadRecursivelyBox)
        
        layout.addStretch(1)
        
    def _handleLoadRecursivelyBox(self,state):
        self.tagEditor.dock.loadRecursively = state == Qt.Checked
        