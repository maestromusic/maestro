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

import functools, os

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
translate = QtCore.QCoreApplication.translate


class FlexFormConfig:
    """Configuration of a FlexForm. This is a list of fields. Use item-access to read fields and the
    addField-method to add new ones.
    If *config* is given, this list will be initialized with the fields from *config* (copy-constructor).
    """
    def __init__(self, config=None):
        if config is None:
            self.fields = []
        else: self.fields = config.fields[:]
        
    def addField(self, field, title=None, type=None, **kwargs):
        """Add a new field. Arguments may be either:
            - a Field-instance,
            - or a name (*field*), title and type, as well as optional keyword arguments which will be
              passed to the constructor of the Field-subclass (which is determined by *type*).
        """
        if not isinstance(field, Field):
            assert title is not None and type is not None
            field = createField(field, title, type, **kwargs)
        if field.name in self:
            raise KeyError("There is already a field named '{}'.".format(field.name))
        self.fields.append(field)
    
    def __len__(self):
        return len(self.fields)
      
    def __getitem__(self, key):
        for field in self.fields:
            if field.name == key:
                return field
        else: raise KeyError("There is no field named '{}'.".format(key))
    
    def __contains__(self, key):
        return any(field.name == key for field in self.fields)
    
    def __iter__(self):
        return self.fields.__iter__()
    
        
class AbstractFlexForm(QtGui.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtGui.QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        self.toolBar = QtGui.QToolBar()
        layout.addWidget(self.toolBar)
        self.toolBar.hide()
        self._createView()
        self.buttonLayout = QtGui.QHBoxLayout()
        self.buttonLayout.addStretch()
        layout.addLayout(self.buttonLayout)
        
        self.buttons = {}
        
    def addField(self, field, title=None, type=None, **kwargs):
        config = FlexFormConfig()
        config.addField(field, title, type, **kwargs)
        self.addFields(config)
        
    def addFields(self, fields):
        raise NotImplementedError()
    
    def addToolButton(self, name, icon, method, text=None, toolTip=None, enabled=False):
        assert name not in self.buttons
        button = QtGui.QToolButton()
        if icon is not None:
            button.setIcon(icon)
        if text is not None:
            button.setText(text)
        if toolTip is not None:
            button.setToolTip(toolTip)
        if not enabled:
            button.setEnabled(False)
        button.clicked.connect(method)
        self.buttons[name] = button
        self.toolBar.addWidget(button)
        self.toolBar.show()
        
    def addAction(self, action):
        self.toolBar.addAction(action)
        self.toolBar.show()
        
    def addPushButton(self, name, title, method):
        assert name not in self.buttons
        button = QtGui.QPushButton(title)
        button.clicked.connect(method)
        self.buttons[name] = button
        self.buttonLayout.addWidget(button)
        
    
class FlexForm(AbstractFlexForm):
    valueChanged = QtCore.pyqtSignal(str, object)
    
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = FlexFormConfig()
        self.fields = self.config.fields
        self.editors = {}
        self.buttons = {}
        if config is not None:
            self.addFields(config)
            
    def _createView(self):
        self.formLayout = QtGui.QFormLayout()
        self.layout().addLayout(self.formLayout)
        
    def addFields(self, config):
        for field in config:
            self.config.addField(field)
            editor = field.createEditor()
            field.setValue(editor, field.default)
            field.connect(editor, functools.partial(self._valueChanged, field.name))
            self.editors[field.name] = editor
            if field.clickable:
                editor.installEventFilter(FieldEventFilter(field, editor))
            if field.hint is not None and len(field.hint) > 0 \
                        and field.type != 'check': # checkboxes contain their own hint
                layout = QtGui.QHBoxLayout()
                layout.addWidget(editor)
                hintLabel = QtGui.QLabel(field.hint)
                palette = hintLabel.palette()
                palette.setColor(QtGui.QPalette.WindowText, Qt.darkGray)
                hintLabel.setPalette(palette)
                layout.addWidget(hintLabel, 1)
                self.formLayout.addRow(field.title, layout)
            else: self.formLayout.addRow(field.title, editor)
        
    def getValue(self, name):
        field = self.config[name]
        return field.getValue(self.editors[name])
        
    def setValue(self, name, value):
        field = self.config[name]
        field.setValue(self.editors[name], value)
        
    def getValues(self):
        return {field.name: field.getValue(self.editors[field.name]) for field in self.fields}
    
    def setValues(self, values):
        for name, value in values.items():
            self.setValue(name, value)
            
    def _valueChanged(self, name):
        field = self.config[name]
        self.valueChanged.emit(name, field.getValue(self.editors[name]))
        

class FieldEventFilter(QtCore.QObject):
    def __init__(self, field, parent):
        super().__init__(parent)
        self.field = field
        
    def eventFilter(self, editor, event):
        if event.type() == QtCore.QEvent.MouseButtonRelease:
            result = self.field.handleClick(self.field.getValue(editor), editor)
            if result is not None:
                self.field.setValue(editor, result)
        return False


class FlexTableModel(QtCore.QAbstractTableModel):
    def __init__(self, fields=None, parent=None):
        super().__init__()
        self.config = FlexFormConfig(fields)
        self.fields = self.config.fields
        self.items = []
    
    def rowCount(self, parent=None):
        return len(self.items)
        
    def columnCount(self, parent=None):
        return len(self.fields)
    
    def flags(self, index):
        field = self.fields[index.column()]
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if field.editable and not field.clickable:
            flags |= Qt.ItemIsEditable
        if field.checkable:
            flags |= Qt.ItemIsUserCheckable
        return flags
    
    def getItemData(self, item, field):
        return getattr(item, field.name)
    
    def setItemData(self, item, field, value):
        setattr(item, field.name, value)
        row = self.items.index(row)
        column = self.fields.index(field)
        index = self.index(row, column)
        self.dataChanged.emit(index, index)
        return True
            
    def data(self, index, role=Qt.DisplayRole):
        if role not in [Qt.DisplayRole, Qt.EditRole, Qt.DecorationRole, Qt.ToolTipRole, Qt.CheckStateRole]:
            return None
        
        field = self.fields[index.column()]
        data = self.getItemData(self.items[index.row()], field)
        if role == Qt.EditRole:
            return data
        elif role == Qt.DisplayRole:
            if field.type not in ['image', 'check']:
                return str(data)
        elif role == Qt.DecorationRole:
            if field.type == 'image':
                return QtGui.QIcon(data)
        elif role == Qt.ToolTipRole:
            if field.type == 'image':
                return data
        elif role == Qt.CheckStateRole:
            if field.checkable:
                return Qt.Checked if data else Qt.Unchecked 
        return None
    
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.fields[section].title
        else: return None
        
    def setData(self, index, value, role=Qt.EditRole):
        item = self.items[index.row()]
        field = self.fields[index.column()]
        if role == Qt.EditRole:
            return self.setItemData(item, field, value)
        elif role == Qt.CheckStateRole and field.checkable:
            return self.setItemData(item, field, value == Qt.Checked)
        else: return False
            
    def addField(self, field, title=None, type=None, **kwargs):
        config = FlexFormConfig()
        config.addField(field, title, type, **kwargs)
        self.addFields(config)
        
    def addFields(self, config):
        first = self.columnCount()
        last = first + len(config)-1
        self.beginInsertColumns(QtCore.QModelIndex(), first, last)
        for field in config:
            self.config.addField(field)
        self.endInsertColumns()

    def addItem(self, item):
        self.insertItem(len(self.items), item)
    
    def insertItem(self, row, item):
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self.items.insert(row, item)
        self.endInsertRows()
        
    def itemChanged(self, item, startColumn=0, endColumn=None):
        row = self.items.index(item)
        if endColumn is None:
            endColumn = len(self.fields)-1
        self.dataChanged.emit(self.index(row, startColumn), self.index(row, endColumn))
    
    def removeItem(self, item):
        row = self.items.index(item)
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self.items[row]
        self.endRemoveRows()


class FlexTableTupleModel(FlexTableModel):
    def getItemData(self, item, field):
        return item[self.fields.index(field)]

    def setItemData(self, item, field, value):
        item[self.fields.index(field)] = value
        return True


class FlexTable(AbstractFlexForm):
    selectionChanged = QtCore.pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self.setModel(FlexTableModel())
        
    def setModel(self, model):
        if model != self.model:
            self.model = model
            self.view.setModel(model)
            self.view.setItemDelegate(FlexTableDelegate(self.model.fields))
            self.view.selectionModel().selectionChanged.connect(self.selectionChanged)
    
    def _createView(self):
        self.view = QtGui.QTableView()
        self.view.verticalHeader().hide()
        self.view.horizontalHeader().setResizeMode(QtGui.QHeaderView.ResizeToContents)
        self.view.doubleClicked.connect(self._clicked)       
        self.view.setContextMenuPolicy(Qt.CustomContextMenu) 
        self.view.customContextMenuRequested.connect(self._customContextMenuRequested)
        self.view.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.layout().addWidget(self.view)
        
    def _clicked(self, index):
        field = self.model.fields[index.column()]
        if field.clickable:
            value = self.model.data(index, Qt.EditRole)
            result = field.handleClick(value, self)
            if result is not None:
                self.model.setData(index, result)

    def _customContextMenuRequested(self, pos):
        row = self.view.rowAt(pos.y())
        field = self.model.fields[self.view.columnAt(pos.x())]
        if field.contextMenu and row != -1:
            item = self.model.items[row]
            menu = field.createContextMenu(item, self)
            menu.exec_(self.view.viewport().mapToGlobal(pos))
                
    def selectedItems(self):
        return [self.model.items[index.row()] for index in self.view.selectionModel().selectedRows()]

    def selectItems(self, items):
        sModel = self.view.selectionModel()
        sModel.clear()
        for i, item in enumerate(items):
            if item in self.model.items:
                row = self.model.items.index(item)
                if i > 0:
                    command = QtGui.QItemSelectionModel.Select
                else: command = QtGui.QItemSelectionModel.SelectCurrent 
                sModel.select(self.model.index(row, 0), command)
            

class FlexTableDelegate(QtGui.QStyledItemDelegate):
    def __init__(self, fields):
        super().__init__()
        self.fields = fields
        
    def sizeHint(self, option, index):
        field = self.fields[index.column()]
        sizeHint = super().sizeHint(option, index)
        if sizeHint.width() >= field.minColumnWidth:
            return sizeHint
        else: return QtCore.QSize(field.minColumnWidth, sizeHint.height())
        
    def createEditor(self, parent, option, index):
        field = self.fields[index.column()]
        if field.checkable: #TODO
            return None
        editor = field.createEditor(parent)
        editor.setAutoFillBackground(True)
        if isinstance(editor, QtGui.QFrame):
            editor.setFrameStyle(QtGui.QFrame.NoFrame)
        elif isinstance(editor, QtGui.QLineEdit):
            p = editor.palette()
            p.setColor(QtGui.QPalette.Base, Qt.white)
            editor.setPalette(p)
            editor.setFrame(False)
        return editor
    
    def setEditorData(self, editor, index):
        field = self.fields[index.column()]
        data = index.model().data(index, Qt.EditRole)
        field.setValue(editor, data)
        
    def setModelData(self, editor, model, index):
        field = self.fields[index.column()]
        data = field.getValue(editor)
        model.setData(index, data, Qt.EditRole)
        

def createField(name, title, type, **kwargs):
    type = type.lower()
    for aClass in Field.__subclasses__():
        if aClass.type == type:
            return aClass(name, title, **kwargs)
    else: raise ValueError("'{}' is not a known field type.".format(type))

    
class Field:
    """A field is a piece of data that can be configured for each item in a FlexForm. Possible fields
    include 'Name', 'Age', 'Path' etc.. There are many subclasses of Field which handle different data types
    and offer different editors. For example the subclass PathField handles a string, like StringField, but
    additionally offers a dialog to choose a path.
    
    Subclasses must at least implement 'createEditor'.
    
    Arguments:
        - *name*: The internal and unique name for this field.
        - *title*: A title displayed to the user.
        - *default*: Default value.
        - *hint*: Help text displayed with the option (currently only supported for FlexForm).
    """
    
    # Field properties. May be changed in subclasses and instances
    default = None      # default value for this field
    editable = True    
    clickable = False
    checkable = False
    contextMenu = False # whether the field offers a context menu
    minColumnWidth = 0 
    
    # The generic implementations of getValue, setValue and connect use these method/signal names to
    # connect to the editor returned by createEditor. Confer e.g. StringField
    methods = ('value', 'setValue', 'valueChanged')
    
    def __init__(self, name, title, **options):
        self.name = name
        self.title = title
        if 'default' in options:
            self.default = options['default'] # else use class attribute 'default'
        self.hint = options.get('hint', '')
        
    def getValue(self, editor):
        """Return the value from the given editor."""
        method = getattr(editor, self.methods[0])
        return method()
    
    def setValue(self, editor, value):
        """Set the value in the given editor."""
        method = getattr(editor, self.methods[1])
        method(value)
        
    def connect(self, editor, method):
        """Connect the 'changed'-signal of *editor* to *method*."""
        signal = getattr(editor, self.methods[2])
        signal.connect(method)
        
    def createEditor(self):
        """Return an editor that can be used to edit values of this field."""
        raise NotImplementedError()
    
    def handleClick(self, value, parent):
        """React to a click on a clickable field. *value* is the current field value, *parent* the widget
        that should be used as dialog parent."""
        raise NotImplementedError()
        
    
class StringField(Field):
    """Field for simple strings. Supports one option 'maxLength'."""
    type = "string"
    default = ''
    methods = ('text', 'setText', 'editingFinished')
    
    def __init__(self, name, title, **options):
        super().__init__(name, title, **options)
        self.maxLength = options.get('maxLength')
        
    def createEditor(self, parent=None):    
        editor = QtGui.QLineEdit(parent)
        if self.maxLength is not None:
            editor.setMaxLength(self.maxLength)
        return editor
        

class IntField(Field):
    """Field for integer values. Options:
        - widget: Either 'spinbox' or 'lineedit' or 'slider'.
        - min: Minimal value.
        - max: Maximal value.
        - step: Step size (ignored if widget=lineedit).
    """ 
    type = "integer"
    default = 0
    
    def __init__(self, name, title, **options):
        super().__init__(name, title, **options)
        self.min = options.get('min', 0)
        self.max = options.get('max', 2**31-1)
        self.step = options.get('step', 1)
        self.widget = options.get('widget', 'spinbox')
        assert self.widget in ('spinbox', 'lineedit', 'slider')
        
    def createEditor(self, parent=None):
        if self.widget == 'spinbox':
            editor = QtGui.QSpinBox(parent)
            editor.setRange(self.min, self.max)
            editor.setSingleStep(self.step)
        elif self.widget == 'lineedit':
            editor = QtGui.QLineEdit(parent)
            editor.setValidator(QtGui.QIntValidator(self.min, self.max))
            editor.sizeHint = editor.minimumSizeHint
        elif self.widget == 'slider':
            editor = QtGui.QSlider(Qt.Horizontal, parent)
            editor.setRange(self.min, self.max)
            editor.setSingleStep(self.step)
        else: assert False
        return editor
    
    def getValue(self, editor):
        if self.widget == 'lineedit':
            return int(editor.text())
        else: return editor.value()
        
    def setValue(self, editor, value):
        if self.widget == 'lineedit':
            editor.setText(str(value))
        else: editor.setValue(value)
            
    def connect(self, editor, method):
        signal = editor.editingFinished if self.widget == 'lineedit' else editor.valueChanged
        signal.connect(method)
        
        
class SelectionField(Field):
    type = "selection"
    
    def __init__(self, name, title, **options):
        super().__init__(name, title, **options)
        self.values = options.get('values', tuple()) # strings or tuples (data, title); both must be strings
        # transform single values to a (data,title)-tuple
        self.values = tuple(t if not isinstance(t, str) else (t,t) for t in self.values)
        if 'default' not in options and len(self.values) > 0:
            self.default = self.values[0][0]
        self.widget = options.get('widget', 'combobox')
        assert self.widget in ('combobox', 'radiobuttons')
       
    def createEditor(self, parent=None):
        if self.widget == 'combobox':
            editor = QtGui.QComboBox(parent)
            for data, title in self.values:
                editor.addItem(title, data)
        elif self.widget == 'radiobuttons':
            editor = RadioButtonGroup(self.values, parent)
        else: assert False
        return editor
            
    def getValue(self, editor):
        if self.widget == 'combobox':
            return editor.itemData(editor.currentIndex())
        elif self.widget == 'radiobuttons':
            for data, button in editor.buttons:
                if button.isChecked():
                    return data
            else: return None
        else: assert False
    
    def setValue(self, editor, value):
        if self.widget == 'combobox':
            editor.setCurrentIndex(editor.findData(value))
        elif self.widget == 'radiobuttons':
            for data, button in editor.buttons:
                if data == value:
                    button.setChecked(True)
                    return
        else: assert False
        
    def connect(self, editor, method):
        signal = editor.currentIndexChanged if self.widget == 'combobox' else editor.valueChanged
        signal.connect(method)
            
       
class RadioButtonGroup(QtGui.QWidget):
    valueChanged = QtCore.pyqtSignal(str)
    
    def __init__(self, values, parent=None):
        super().__init__(parent)
        layout = QtGui.QHBoxLayout(self)
        self.buttons = [] # list of (data, button) tuples
        for data, title in values:
            button = QtGui.QRadioButton(title)
            button.toggled.connect(functools.partial(self._toggled, data))
            layout.addWidget(button)
            self.buttons.append((data, button))
    
    def _toggled(self, data, checked):
        if checked:
            self.valueChanged.emit(data)
            
        
class CheckField(Field):
    type = "check"
    default = False
    checkable = True
    methods = ('isChecked', 'setChecked', 'toggled')
    
    def createEditor(self, parent=None):
        editor = QtGui.QCheckBox(self.hint if self.hint is not None else '', parent)
        return editor
   
  
class ImageField(Field):
    type = "image"
    default = None
    clickable = True
    contextMenu = True
    
    def __init__(self, name, title, **options):
        super().__init__(name, title, **options)
        self.folders = options.get('folders', [])
        
    def createEditor(self, parent=None):
        return ImageLabel(parent)
    
    def handleClick(self, value, parent):
        # Choose a sensible directory as starting point
        result = ImageChooser.getImage(self.folders, value, parent)
        if result is not None and result != value:
            return result
    
    def createContextMenu(self, item, view):
        value = view.model.getItemData(item, self)
        menu = QtGui.QMenu(view)
        if value is None:
            changeAction = QtGui.QAction(translate("ImageField", "Add image..."), menu)
        else: changeAction = QtGui.QAction(translate("ImageField", "Change image..."), menu)
        def changeImage():
            imagePath = ImageChooser.getImage(self.folders, value, view)
            if imagePath is not None:
                view.model.setItemData(item, self, imagePath)
        changeAction.triggered.connect(changeImage)
        menu.addAction(changeAction)
        
        removeAction = QtGui.QAction(translate("ImageField", "Remove image"), menu)
        removeAction.setEnabled(value is not None)
        removeAction.triggered.connect(lambda: view.model.setItemData(item, self, None))
        menu.addAction(removeAction)
        return menu
        
    def _changeAction(self, item):
        image = ImageChooser.getImage(self.folders, default, view)


class ImageLabel(QtGui.QLabel):
    valueChanged = QtCore.pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.path = None
    
    def value(self):
        assert not isinstance(self.path, tuple)
        return self.path
    
    def setValue(self, path):
        assert not isinstance(self.path, tuple)
        self.path = path
        if self.path is not None:
            self.setToolTip(self.path)
            pixmap = QtGui.QPixmap(self.path)
            if not pixmap.isNull() and max(pixmap.width(), pixmap.height()) > 100:
                pixmap = pixmap.scaled(100, 100, aspectRatioMode=Qt.KeepAspectRatio)
        else:
            pixmap = QtGui.QPixmap()
            self.setToolTip('')
        self.setPixmap(pixmap)
        self.valueChanged.emit()
        

class ImageChooser(QtGui.QDialog):
    """Lets the user choose an image from a list or an abitrary image using a file dialog. *folders*
    is a list of directory paths. The dialog will display all files in these directories. If *default*
    is the path of a displayed icon, it will be selected.
    """
    def __init__(self, folders, default, parent = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Choose an image"))
        
        layout = QtGui.QVBoxLayout(self)
        pixmaps = []
        for path in folders:
            for file in QtCore.QDir(path).entryInfoList(filters=QtCore.QDir.Files):
                try:
                    pixmap = QtGui.QPixmap(file.canonicalFilePath())
                    pixmaps.append((pixmap, file))
                except Exception as e:
                    pass
        self.view = QtGui.QListWidget(self)
        self.view.setViewMode(QtGui.QListView.IconMode)
        self.view.doubleClicked.connect(self.accept)
       
        if default is not None:
            defaultFile = QtCore.QFileInfo(default)
        else: defaultFile = None
        for pixmap, file in pixmaps:
            item = QtGui.QListWidgetItem(QtGui.QIcon(pixmap), '')
            item.setData(Qt.UserRole, file.canonicalFilePath())
            item.setToolTip(file.baseName())
            self.view.addItem(item)
            if file == defaultFile:
                self.view.setItemSelected(item, True)
                self.view.setCurrentItem(item)
                
        layout.addWidget(self.view)
        buttonBox = QtGui.QDialogButtonBox()
        layout.addWidget(buttonBox)
        
        addButton = QtGui.QPushButton(self.tr("Add..."))
        addButton.clicked.connect(self._handleAdd)
        buttonBox.addButton(addButton, QtGui.QDialogButtonBox.ActionRole)
        cancelButton = buttonBox.addButton(QtGui.QDialogButtonBox.Cancel)
        cancelButton.clicked.connect(self.reject)
        okButton = buttonBox.addButton(QtGui.QDialogButtonBox.Ok)
        okButton.clicked.connect(self.accept)
        
        self.resize(320, 350)
    
    @staticmethod
    def getImage(folders, default, parent=None):
        """Let the user choose an image using an ImageChooser-dialog. If the user selected an image, return
        its path. Otherwise return None.
        """
        chooser = ImageChooser(folders, default, parent)
        if chooser.exec_() == QtGui.QDialog.Accepted:
            item = chooser.view.currentItem()
            return item.data(Qt.UserRole)
        else: return None
                
    def _handleAdd(self):
        """Handle clicks on the add button: Open a file dialog."""
        fileName = QtGui.QFileDialog.getOpenFileName(self,self.tr("Choose an image"),
                                                     filter = self.tr("Images (*.png *.xpm *.jpg)"))
        if fileName:
            pixmap = QtGui.QPixmap(fileName)
            item = QtGui.QListWidgetItem(QtGui.QIcon(pixmap), '')
            item.setData(Qt.UserRole, fileName)
            item.setToolTip(fileName)
            self.view.addItem(item)
            self.view.setCurrentItem(item)


class CustomField(Field):
    type = "custom"
    
    def __init__(self, name, title, **options):
        super().__init__(name, title, **options)
        if 'widget' in options:
            self.widget = options['widget']
        else: self.widget = QtGui.QWidget()
        
    def createEditor(self, parent=None):
        return self.widget
        

class FixedField(Field):
    type = "fixed"
    editable = False
    
    def createEditor(self, parent=None):
        return QtGui.QLabel()
    
    def getValue(self, editor):
        if hasattr(editor, 'value'):
            return editor.value
        else: return ''
        
    def setValue(self, editor, value):
        editor.value = value
        editor.setText(str(value))
        

class DomainField(Field):
    type = "domain"
    methods = ('currentDomain', 'setCurrentDomain', 'domainChanged')
    
    def createEditor(self, parent=None):
        from omg.gui import widgets
        return widgets.DomainBox(parent=parent)
    
    def setValue(self, editor, value):
        if value is None:
            from omg.core import domains
            value = domains.domains[0]
        super().setValue(editor, value)

    
class TagField(Field):
    type = "tag"
    methods = ('getTag', 'setTag', 'tagChanged')
    
    def createEditor(self, parent=None):
        from omg.gui import tagwidgets
        return tagwidgets.TagTypeBox(parent=parent)

    def setValue(self, editor, value):
        if value is None:
            from omg.core import tags
            value = tags.TITLE
        super().setValue(editor, value)

    
class PathField(Field):
    type = "path"
    default = ''
    minColumnWidth = 200
    methods = ('text', 'setText', 'textChanged')
    
    def __init__(self, name, title, dialogTitle, pathType='path', **options):
        super().__init__(name, title, **options)
        self.dialogTitle = dialogTitle
        self.pathType = pathType
    
    def createEditor(self, parent=None):
        from .misc.lineedits import PathLineEdit
        return PathLineEdit(self.dialogTitle, self.pathType, os.path.expanduser('~'), parent)
    
    
class PasswordField(Field):
    type = "password"
    default = ''
    methods = ('text', 'setText', 'textChanged')
    
    def createEditor(self, parent=None):
        return PasswordEditor(parent)
    
    
class PasswordEditor(QtGui.QWidget):
    textChanged = QtCore.pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtGui.QHBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        self.lineEdit = QtGui.QLineEdit()
        self.lineEdit.setEchoMode(QtGui.QLineEdit.Password)
        self.lineEdit.textChanged.connect(self.textChanged)
        layout.addWidget(self.lineEdit)
        echoModeBox = QtGui.QCheckBox('Show password')
        echoModeBox.clicked.connect(lambda checked: self.lineEdit.setEchoMode(
                                    QtGui.QLineEdit.Normal if checked else QtGui.QLineEdit.Password))
        layout.addWidget(echoModeBox)

    def text(self):
        return self.lineEdit.text()
    
    def setText(self, text):
        self.lineEdit.setText(text)


if __name__ == "__main__":
    class Item:
        def __init__(self, **values):
            self.__dict__.update(values)
            
    from omg import application
    app = application.init()
    flexForm = FlexForm()
    flexForm.setWindowTitle("FlexForm Test")
    flexForm.addField("icon", "Icon", "image", folders=[':omg/flags', ':omg/tags'])
    flexForm.addField("string", "String", "string", maxLength=20)
    flexForm.addField("spinningint", "Spinning Integer", "integer", min=-10, max=-1)
    flexForm.addField("slidingint", "Sliding Integer", "integer", widget="slider", max=100)
    flexForm.addField("boringint", "Boring Integer", "integer", widget="lineedit", min=20, max=70,
                      hint="Minimum 20, Maximum 70")
    flexForm.addField("combo", "Combo", "selection", values=["One", "Two", "Three", "Four"])
    flexForm.addField("radio", "Radio", "selection", values=["One", "Two", "Three", "Four"],
                      widget="radiobuttons")
    flexForm.addField("check", "Check", "check", hint="Test text")
    flexForm.addField("domain", "Domain", "domain")
    flexForm.addField("tag", "Tag", "tag", hint="Your favourite tag")
    
    if isinstance(flexForm, FlexTable):
        defaults = {field.name: field.default for field in flexForm.model.fields}
        flexForm.model.addItem(Item(**defaults))
        defaults.update(string="bla", spinningint=1, slidingint=2, boringint=3,
                                    combo="Three", radio="Four")
        flexForm.model.addItem(Item(**defaults))
        
    def printValues():
        for name, value in flexForm.getValues().items():
            print("{}: {}".format(name, value))
    flexForm.addButton("printValues", "Print values", printValues)
    flexForm.addButton("close", "Close", flexForm.close)
    if isinstance(flexForm, FlexForm):
        flexForm.valueChanged.connect(functools.partial(print, "CHANGE:"))
    flexForm.show()
    app.exec_()
