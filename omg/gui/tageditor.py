# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

import itertools, os.path

from .. import constants, tags, strutils, utils, config, logging, modify, constants
from ..models import tageditor as tageditormodel, simplelistmodel, File, flageditor as flageditormodel
from ..gui import singletageditor, dialogs, tagwidgets, mainwindow, editor, flageditor
from ..gui.misc import widgetlist, dynamicgridlayout
from ..constants import REAL, EDITOR

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
        self.tabWidget = QtGui.QTabWidget()
        self.tabWidget.setTabPosition(QtGui.QTabWidget.North if vertical else QtGui.QTabWidget.East)
        self.setWidget(self.tabWidget)
        self.realEditorWidget = TagEditorWidget(REAL,vertical=vertical)
        self.editorEditorWidget = TagEditorWidget(EDITOR,vertical=vertical)
        self.tabWidget.addTab(self.realEditorWidget,self.tr("Real"))
        self.tabWidget.addTab(self.editorEditorWidget,self.tr("Editor"))
        self.setAcceptDrops(True)
        
        mainwindow.mainWindow.globalSelectionChanged.connect(self._handleSelectionChanged)
    
    def _handleLocationChanged(self,area):
        vertical = self.isFloating() or area in [Qt.LeftDockWidgetArea,Qt.RightDockWidgetArea]
        self.tabWidget.setTabPosition(QtGui.QTabWidget.North if vertical else QtGui.QTabWidget.East)
        self.realEditorWidget.setVertical(vertical)
        self.editorEditorWidget.setVertical(vertical) 
    
    def _handleSelectionChanged(self,elements,source):
        """React to changes to the global selection: Load the selected elements in the correct
        TagEditorWidget."""
        if isinstance(source,editor.EditorTreeView):
            self.editorEditorWidget.setElements(elements)
            self.tabWidget.setCurrentWidget(self.editorEditorWidget)
        else:
            self.realEditorWidget.setElements(elements)
            self.tabWidget.setCurrentWidget(self.realEditorWidget)
        
    def dragEnterEvent(self,event):
        if event.mimeData().hasFormat(config.options.gui.mime) or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self,event):
        mimeData = event.mimeData()
        if isinstance(event.source(),editor.EditorTreeView):
            editorWidget = self.editorEditorWidget
        else: editorWidget = self.realEditorWidget
        
        if mimeData.hasFormat(config.options.gui.mime):
            editorWidget.setElements(mimeData.getElements())
            event.acceptProposedAction()
        elif mimeData.hasUrls():
            elements = [File.fromFilesystem(url.toLocalFile()) for url in event.mimeData().urls()
                           if url.isValid() and url.scheme() == 'file' and os.path.exists(url.toLocalFile())]
            editorWidget.setElements(elements)
            event.acceptProposedAction()
        else:
            logger.warning("Invalid drop event (supports only {})".format(", ".join(mimeData.formats())))
        self.tabWidget.setCurrentWidget(editorWidget)
        
        
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
    def __init__(self,level,elements,parent=None):
        QtGui.QDialog.__init__(self,parent)
        self.setLayout(QtGui.QVBoxLayout())
        self.tagedit = TagEditorWidget(level,elements,dialog=self)
        self.layout().addWidget(self.tagedit)
        self.setWindowTitle(self.tr("Edit tags"))
        self.resize(600,450) #TODO: klüger
        self.tagedit.saved.connect(self.accept)
        
        
class TagEditorWidget(QtGui.QWidget):
    
    saved = QtCore.pyqtSignal()
        
    # This hack is necessary to ignore changes in the tagboxes while changing the tag programmatically
    # confer _handleTagChanged and _handleTagChangedByUser.
    _ignoreHandleTagChangedByUser = False
    
    def __init__(self,level,elements=None,parent = None,dialog=None,saveDirectly=True,vertical=False):
        QtGui.QWidget.__init__(self,parent)
        self.level = level
        self.vertical = None # will be set in setVertical below
        if elements is None:
            elements = []
        if dialog is not None:
            saveDirectly = False
        
        self.model = tageditormodel.TagEditorModel(level,elements,saveDirectly)
        self.model.tagInserted.connect(self._handleTagInserted)
        self.model.tagRemoved.connect(self._handleTagRemoved)
        self.model.tagChanged.connect(self._handleTagChanged)
        self.model.resetted.connect(self._handleReset)

        self.flagModel = flageditormodel.FlagEditorModel(level,elements,saveDirectly,self.model)
        self.flagModel.resetted.connect(self._checkFlagEditorVisibility)
        self.flagModel.recordInserted.connect(self._checkFlagEditorVisibility)
        self.flagModel.recordRemoved.connect(self._checkFlagEditorVisibility)
        
        elements = None # ensure that these are not used anymore; the models will contain copies

        self.selectionManager = widgetlist.SelectionManager()
        # Do not allow the user to select ExpandLines
        self.selectionManager.isSelectable = \
            lambda wList,widget: not isinstance(widget,singletageditor.ExpandLine)
        
        self.setLayout(QtGui.QVBoxLayout())
        self.topLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(self.topLayout)
        
        iconLabel = QtGui.QLabel()
        iconLabel.setPixmap(utils.getPixmap('real.png' if level == REAL else 'editor.png'))
        iconLabel.setToolTip(self.tr("Real level") if level == REAL else self.tr("Editor level"))
        self.topLayout.addWidget(iconLabel)

        # Texts will be set in _changeLayout
        self.addButton = QtGui.QPushButton()
        self.addButton.setIcon(utils.getIcon("add.png"))
        self.addButton.clicked.connect(lambda: self._handleAddRecord(None))
        self.topLayout.addWidget(self.addButton)
        self.removeButton = QtGui.QPushButton()
        self.removeButton.setIcon(utils.getIcon("remove.png"))
        self.removeButton.clicked.connect(self._handleRemoveSelected)
        self.topLayout.addWidget(self.removeButton)
        
        self.addFlagButton = QtGui.QPushButton()
        self.addFlagButton.setIcon(utils.getIcon("flag_blue.png"))
        self.addFlagButton.clicked.connect(self._handleAddFlagButton)
        self.topLayout.addWidget(self.addFlagButton)
        
        if not saveDirectly:
            style = QtGui.QApplication.style()
            self.resetButton = QtGui.QPushButton()
            self.resetButton.setIcon(style.standardIcon(QtGui.QStyle.SP_DialogResetButton))
            self.resetButton.clicked.connect(self.model.reset)
            self.topLayout.addWidget(self.resetButton)
            if dialog is not None:
                self.cancelButton = QtGui.QPushButton()
                self.cancelButton.setIcon(style.standardIcon(QtGui.QStyle.SP_DialogCancelButton))
                self.cancelButton.clicked.connect(dialog.reject)
                self.topLayout.addWidget(self.cancelButton)
            self.saveButton = QtGui.QPushButton()
            self.saveButton.setIcon(style.standardIcon(QtGui.QStyle.SP_DialogSaveButton))
            self.saveButton.clicked.connect(self._handleSave)
            self.topLayout.addWidget(self.saveButton)
        
        self.label = QtGui.QLabel()
        self.topLayout.addStretch(1)
        
        scrollArea = QtGui.QScrollArea()
        scrollArea.setWidgetResizable(True)
        self.layout().addWidget(scrollArea,1)
            
        self.viewport = QtGui.QWidget()
        self.viewport.setLayout(QtGui.QVBoxLayout())
        self.tagEditorLayout = dynamicgridlayout.DynamicGridLayout()
        self.tagEditorLayout.setColumnStretch(1,1) # Stretch the column holding the values
        self.viewport.layout().addLayout(self.tagEditorLayout)
        self.viewport.layout().addStretch(1)
        scrollArea.setWidget(self.viewport)

        self.flagWidget = QtGui.QWidget()
        self.flagWidget.setLayout(QtGui.QHBoxLayout())
        self.flagWidget.layout().setContentsMargins(0,0,0,0)
        self.layout().addWidget(self.flagWidget)
        
        self.flagLabel = QtGui.QLabel() # Text will be set in setVertical
        self.flagLabel.setToolTip(self.tr("Flags"))
        self.flagWidget.layout().addWidget(self.flagLabel)
        
        flagScrollArea = QtGui.QScrollArea()
        flagScrollArea.setWidgetResizable(True)
        flagScrollArea.setMaximumHeight(40)
        # Vertical model of the flageditor is not used
        flagEditor = flageditor.FlagEditor(self.flagModel,False)
        flagScrollArea.setWidget(flagEditor)
        self.flagWidget.layout().addWidget(flagScrollArea,1)
        self._checkFlagEditorVisibility()
        
        self.singleTagEditors = {}
        self.tagBoxes = {}
        
        self.setVertical(vertical)
        self._handleReset()
    
    def setVertical(self,vertical):
        """Set whether this tageditor should be displayed in vertical model."""
        if vertical == self.vertical:
            return
        for box in self.tagBoxes.values():
            box.setIconOnly(vertical)
            
        if vertical:
            for button in ['addButton','removeButton','addFlagButton']:
                getattr(self,button).setText('')
            for button in ['resetButton','cancelButton','saveButton']:
                if hasattr(self,button):
                    getattr(self,button).setText('')
            if not self.vertical: # Not when this function is called for the first time
                self.topLayout.removeWidget(self.label)
            self.layout().insertWidget(1,self.label)
            self.flagLabel.setText('<img src="images/icons/flag_blue.png">')
        else:
            self.addButton.setText(self.tr("Add tag"))
            self.removeButton.setText(self.tr("Remove selected"))
            self.addFlagButton.setText(self.tr("Add flag"))
            
            if hasattr(self,'resetButton'):
                self.resetButton.setText(self.tr("Reset"))
            if hasattr(self,'cancelButton'):
                self.cancelButton.setText(self.tr("Cancel"))
            if hasattr(self,'saveButton'):
                self.saveButton.setText(self.tr("Save"))
            if self.vertical: # Not when this function is called for the first time
                self.layout().removeWidget(self.label)
            self.topLayout.insertWidget(self.topLayout.count()-1,self.label) # -1 due to the stretch
            self.flagLabel.setText('<img src="images/icons/flag_blue.png"> '+self.tr("Flags: "))
            
        self.vertical = vertical
            
    def setElements(self,elements):
        self.model.setElements(elements)
        self.flagModel.setElements(elements)
        
    def _insertSingleTagEditor(self,row,tag):
        self.tagEditorLayout.insertRow(row)
        
        # Create the tagbox
        self.tagBoxes[tag] = SmallTagTypeBox(tag,self.vertical)
        self.tagBoxes[tag].tagChanged.connect(self._handleTagChangedByUser)
        self.tagEditorLayout.addWidget(self.tagBoxes[tag],row,0)
        
        # Create the Tag-Editor
        self.singleTagEditors[tag] = singletageditor.SingleTagEditor(self,tag,self.model)
        self.singleTagEditors[tag].widgetList.setSelectionManager(self.selectionManager)
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
        tagEditor.widgetList.setSelectionManager(None)
        tagEditor.setParent(None)
        del self.singleTagEditors[tag]

    def _handleReset(self):
        for tag in list(self.singleTagEditors.keys()): # dict will change
            self._removeSingleTagEditor(tag)
        for tag in self.model.getTags():
            self._insertSingleTagEditor(len(self.singleTagEditors),tag)
        count = len(self.model.getElements())
        self.label.setText(self.tr("Edit tags of %n element(s).",'',count))
        # Enable / disable buttons
        for i in range(1,self.topLayout.count()): # Skip the iconLabel
            widget = self.topLayout.itemAt(i).widget()
            if widget is not None:
                widget.setEnabled(count > 0)
        
    def _handleAddRecord(self,tag=None):
        dialog = RecordDialog(self,self.model.getElements(),defaultTag=tag)
        if dialog.exec_() == QtGui.QDialog.Accepted:
            self.model.addRecord(dialog.getRecord())

    def _handleRemoveSelected(self):
        records = [re.getRecord() for re in self.selectionManager.getSelectedWidgets() if re.isVisible()]
        if len(records) > 0:
            self.model.removeRecords(records)
          
    def _handleAddFlagButton(self):
        if not flageditor.AddFlagPopup.isActive(self.addFlagButton):
            popup = flageditor.AddFlagPopup(self.flagModel,self.addFlagButton)
            popup.show()
            
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
        """Handle the save button (only if ''saveDirectly'' is True)."""
        if self.model.saveDirectly:
            raise RuntimeError("You must not call save in a TagEditor that saves directly.") 
        
        if not all(singleTagEditor.isValid() for singleTagEditor in self.singleTagEditors.values()):
            QtGui.QMessageBox.warning(self,self.tr("Invalid value"),self.tr("At least one value is invalid."))
        else:
            modify.push(modify.commands.TagFlagUndoCommand(self.level,
                                                           self.model.getChanges(),
                                                           self.flagModel.getChanges(),
                                                           elements = self.model.getElements()))
            self.saved.emit()
                
    def contextMenuEvent(self,contextMenuEvent,record=None):
        menu = QtGui.QMenu(self)

        menu.addAction(self.model.createUndoAction(self,self.tr("Undo")))
        menu.addAction(self.model.createRedoAction(self,self.tr("Redo")))
        menu.addSeparator()
        
        addRecordAction = QtGui.QAction(self.tr("Add tag..."),self)
        addRecordAction.triggered.connect(lambda: self._handleAddRecord(record.tag))
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
        selectedRecords = [editor.getRecord() for editor in self.selectionManager.getSelectedWidgets()]

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

    def _checkFlagEditorVisibility(self):
        self.flagWidget.setVisible(not self.flagModel.isEmpty())


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
        self.elementsBox.setModel(simplelistmodel.SimpleListModel(elements,lambda el: el.title))
        self.elementsBox.setSelectionMode(QtGui.QAbstractItemView.MultiSelection)
        for i,element in enumerate(elements):
            if record is None or element in record.elementsWithValue:
                self.elementsBox.selectionModel().select(self.elementsBox.model().index(i,0),
                                                         QtGui.QItemSelectionModel.Select)
                
        abortButton = QtGui.QPushButton(self.tr("Cancel"),self)
        abortButton.clicked.connect(self.reject)
        okButton = QtGui.QPushButton(self.tr("OK"),self)
        okButton.clicked.connect(self._handleOkButton)
        
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
        lastLineLayout = QtGui.QHBoxLayout()
        lastLineLayout.addStretch(1)
        lastLineLayout.addWidget(abortButton,0)
        lastLineLayout.addWidget(okButton,0)
        layout.addLayout(lastLineLayout)
    
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
        