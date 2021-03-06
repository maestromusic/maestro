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

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from ... import utils, logging, config


# Toplevel panels. Map path to Panel instance
panels = utils.OrderedDict()


def init():
    addPanel('profiles', translate('Preferences', 'Profiles'),
             description=translate('Preferences',
                                   'Manage configuration options that are organized in profiles.'),
             callable=('gui.preferences.profiles', 'CategoryMenu'),
             iconName='preferences-profiles')

    # Bugfix: do not call this profiles, otherwise the submodule is unreachable
    from maestro import profiles as profilesModule
    profilesModule.ProfileManager.instance().categoryAdded.connect(_addProfileCategory)
    profilesModule.ProfileManager.instance().categoryRemoved.connect(_removeProfileCategory)
    for category in profilesModule.categories():
        _addProfileCategory(category)

    addPanel('plugins', translate('Preferences', 'Plugins'),
             ('gui.preferences.plugins', 'PluginPanel'),
             iconName='preferences-plugin',
             description=translate('Preferences', 'Enable or disable plugins.<br />'
                                   '<b>Warning:</b> Changes are immediate!'))


def show(startPanel=None):
    """Open the preferences dialog. To start with a specific panel provide its path as *startPanel*."""
    from .. import mainwindow
    dialog = PreferencesDialog(mainwindow.mainWindow)
    if startPanel is not None:
        dialog.showPanel(startPanel)
    dialog.exec_()
    
    
class Panel:
    """A panel inside the preferences dialog, i.e. the part on the right of the panel treeview and below of
    the title label. Panels are identified by a path (e.g. "main/tagmanager") and store a callable which is
    used to produce the Panel's configuration widget.

    Constructor parameters are

        - *path*: A unique identifier for the panel which additionally specifies the parent node in the tree
          of panels.
        - *title*: The title of the panel
        - *callable*: A callable that will produce the widget that should be displayed on this panel.
          Often this is simply the widget's class.
          Alternatively, a tuple can be passed. It must consist of either a callable or a module name (e.g.
          "gui.preferences.tagmanager") and the name of a callable that is found in the module. In both cases
          this mandatory components can be followed by an arbitrary number of arguments.
          The callable will be invoked with the PreferencesDialog-instance, the PanelWidget-instance and
          the arguments from the tuple.
          In the second form, the module will only be imported when the panel is actually shown.
        - *icon*: Icon that will be displayed in the preferences' menu.

    \ """
    def __init__(self, path, title, callable, iconName=None, description=''):
        self.path = path
        self.title = title
        self._callable = callable
        self.iconName = iconName
        self.description = description
        self.subPanels = utils.OrderedDict()

    def icon(self):
        return utils.images.icon(self.iconName)

    def pixmap(self):
        return utils.images.icon(self.iconName).pixmap(48)

    def createWidget(self, dialog, panel):
        """Create a configuration widget for this panel using the 'callable' argument of the constructor.
        *dialog* and *panel* will be passed to the widget's constructor.
        """
        if isinstance(self._callable, tuple) and isinstance(self._callable[0], str):
            import importlib
            try:
                module = importlib.import_module('.'+self._callable[0], 'maestro')
                self._callable = (getattr(module, self._callable[1]), ) + self._callable[2:]
            except ImportError:
                logging.exception(__name__, "Cannot import module '{}'".format(self._callable[0]))
                self._callable = None
            except AttributeError:
                logging.error(__name__, "Module '{}' has no attribute '{}'"
                                        .format(self._callable[0], self._callable[1]))
                self._callable = None

        if self._callable is None:
            return QtWidgets.QWidget()
        elif not isinstance(self._callable, tuple):
            return self._callable(dialog, panel)
        else:
            return self._callable[0](dialog, panel, *self._callable[1:])


class PreferencesDialog(QtWidgets.QDialog):
    """The preferences dialog contains a list of panels on the left and the current panel's title together
    with the actual panel on the right. Except for the "main" panel which is shown at the beginning, it will
    only construct a panel (and in fact import the corresponding module) when the user selects it in the
    treeview.
    """
    # The one single instance
    _dialog = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Preferences - Maestro"))
        self.setWindowIcon(utils.images.icon('preferences-other'))
        self.finished.connect(self._handleFinished)

        # Restore geometry
        if config.binary.gui.preferences_geometry is not None:
            success = self.restoreGeometry(config.binary.gui.preferences_geometry)
        else:
            success = False
        if not success: # Default geometry
            self.resize(800, 600)

        # map paths to the widget of a panel once it has been constructed
        self.panelWidgets = {}
        self.currentPath = None

        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)

        splitter = QtWidgets.QSplitter(Qt.Horizontal)
        splitter.setContentsMargins(0,0,0,0)
        self.layout().addWidget(splitter, 1)

        self.treeWidget = QtWidgets.QTreeWidget()
        self.treeWidget.header().hide()
        self.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.treeWidget.header().setStretchLastSection(False)
        self.treeWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.treeWidget.itemSelectionChanged.connect(self._handleSelectionChanged)
        splitter.addWidget(self.treeWidget)

        self.stackedWidget = QtWidgets.QStackedWidget()
        splitter.addWidget(self.stackedWidget)

        splitter.setSizes([180, 620])

        self.fillTreeWidget()
        self.showPanel("main")
        PreferencesDialog._dialog = self

    def fillTreeWidget(self):
        """Fill the treeview with a tree of all panels."""
        self.treeWidget.clear()
        for path, panel in panels.items():
            item = QtWidgets.QTreeWidgetItem([panel.title])
            item.setData(0, Qt.UserRole, path)
            item.setIcon(0, panel.icon())
            self.treeWidget.addTopLevelItem(item)
            if len(panel.subPanels) > 0:
                self._addSubPanels(panel, item)

    def _addSubPanels(self, panel, item):
        """Add the subpanels of *panel* to the treeview. *item* is the QTreeWidgetItem for *panel*."""
        for p, subPanel in panel.subPanels.items():
            newPath = '{}/{}'.format(panel.path, p)
            newItem = QtWidgets.QTreeWidgetItem([subPanel.title])
            newItem.setData(0, Qt.UserRole, newPath)
            newItem.setIcon(0, subPanel.icon())
            item.addChild(newItem)
            if len(subPanel.subPanels) > 0:
                self._addSubPanels(subPanel, newItem)
            item.setExpanded(True)

    def showPanel(self, path):
        """Show the panel with the given path, constructing it, if it is shown for the first time."""
        if path == self.currentPath:
            return
        if self.stackedWidget.currentWidget() is not None \
                and not self.stackedWidget.currentWidget().okToClose():
            self.treeWidget.clearSelection()
            self._findItem(self.currentPath).setSelected(True) # Reset
            return
        self.currentPath = path
        if path not in self.panelWidgets:
            self._createPanelWidget(path)
        self.stackedWidget.setCurrentWidget(self.panelWidgets[path])
        self.treeWidget.clearSelection()
        self._findItem(path).setSelected(True)

    def _createPanelWidget(self, path):
        """Create a PanelWidget for the given path inside the preferences."""
        assert path not in self.panelWidgets
        panel = self.getPanel(path)
        widget = PanelWidget(self, panel)
        self.panelWidgets[path] = widget
        self.stackedWidget.addWidget(widget)

    def getPanel(self, path):
        """Return the Panel-instance (not the actual widget!) with the given *path*."""
        keys = path.split('/')
        currentPanels = panels
        for key in keys[:-1]:
            currentPanels = currentPanels[key].subPanels
        return currentPanels[keys[-1]]

    def getConfigurationWidget(self, path):
        """Return the configuration widget for the given path inside the preferences."""
        if not path in self.panelWidgets:
            self._createPanelWidget(path)
        return self.panelWidgets[path].configurationWidget

    def _findItem(self, path):
        """Return the QTreeWidgetItem for the given path from the menu."""
        def getItems(item):
            yield item
            for i in range(item.childCount()):
                for it in getItems(item.child(i)):
                    yield it
        items = [self.treeWidget.topLevelItem(i) for i in range(self.treeWidget.topLevelItemCount())]
        for i in range(self.treeWidget.topLevelItemCount()):
            toplevelItem = self.treeWidget.topLevelItem(i)
            for item in getItems(toplevelItem):
                if item.data(0, Qt.UserRole) == path:
                    return item
        raise KeyError("Path '{}' not found.".format(path))

    def _handleSelectionChanged(self):
        """Handle clicks on a panel in the treeview."""
        items = self.treeWidget.selectedItems()
        if len(items) > 0:
            path = items[0].data(0, Qt.UserRole)
            self.showPanel(path)

    def _handleFinished(self):
        """Handle the close button."""
        PreferencesDialog._dialog = None
        # Copy the bytearray to avoid memory access errors
        config.binary.gui.preferences_geometry = bytearray(self.saveGeometry())


class PanelWidget(QtWidgets.QWidget):
    """PanelWidgets are used for the right part of the preferences dialog. They contain a title section,
    a configuration widget and a button bar. The configuration widget is created using the createWidget
    method of *panel*.
    """
    def __init__(self, dialog, panel):
        super().__init__(dialog)
        self.dialog = dialog

        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)

        # Create title widget
        titleWidget = QtWidgets.QFrame()
        titleWidget.setFrameStyle(QtWidgets.QFrame.StyledPanel | QtWidgets.QFrame.Raised)
        titleWidget.setStyleSheet("QFrame { background-color: white; }")
        self.layout().addWidget(titleWidget)

        titleLayout = QtWidgets.QHBoxLayout(titleWidget)
        titleLayout.setSpacing(20)
        self.titleLabel = QtWidgets.QLabel()
        self.titleLabel.setText("<b>{}</b><br/>{}".format(panel.title, panel.description))
        self.titleLabel.setWordWrap(True)
        self.titleLabel.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        titleLayout.addWidget(self.titleLabel, 1)
        pixmapLabel = QtWidgets.QLabel()
        pixmapLabel.setPixmap(panel.pixmap())
        pixmapLabel.setContentsMargins(20, 0, 20, 0)
        titleLayout.addWidget(pixmapLabel)

        self.buttonBar = QtWidgets.QHBoxLayout()

        # Create configuration widget
        self.configurationWidget = panel.createWidget(dialog, self)
        scrollArea = QtWidgets.QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setWidget(self.configurationWidget)
        self.layout().addWidget(scrollArea, 1)

        # Add button bar
        style = QtWidgets.QApplication.style()
        self.layout().addLayout(self.buttonBar)
        self.buttonBar.setContentsMargins(0, 0, style.pixelMetric(QtWidgets.QStyle.PM_LayoutRightMargin),
                                          style.pixelMetric(QtWidgets.QStyle.PM_LayoutBottomMargin))
        if all(self.buttonBar.stretch(i) == 0 for i in range(self.buttonBar.count())):
            self.buttonBar.addStretch(1)
        closeButton = QtWidgets.QPushButton(style.standardIcon(QtWidgets.QStyle.SP_DialogCloseButton),
                                        self.tr("Close"))
        closeButton.clicked.connect(self._handleCloseButton)
        self.buttonBar.addWidget(closeButton)

    def _handleCloseButton(self):
        if self.okToClose():
            self.dialog.accept()

    def okToClose(self):
        """Give the current panel a chance to abort closing the preferences dialog or switching to
        another panel. Return True if closing is admissible."""
        return not hasattr(self.configurationWidget, 'okToClose') or self.configurationWidget.okToClose()


def _getParentPanel(path):
    """Return the parent panel of the one identified by *path*. This method even works when no panel is
    registered for *path* (the parent must be registered, of course)."""
    keys = path.split('/')
    i = 0
    parent = None
    currentPanels = panels
    while i < len(keys) - 1:
        if keys[i] not in currentPanels:
            raise ValueError("Panel '{}' does not contain a subpanel '{}'"
                             .format('/'.join(keys[:i]), keys[i]))
        parent = currentPanels[keys[i]]
        currentPanels = parent.subPanels
        i += 1

    return parent, keys[-1]


def addPanel(path, *args, **kwargs):
    """Add a panel to the preferences dialog. *path* specifies the position in the panel tree.
    All other arguments are passed to the constructor of Panel."""
    insertPanel(path, -1, *args, **kwargs)


def insertPanel(path, position, *args, **kwargs):
    """Insert a panel into the preferences dialog. *path* specifies the position in the panel tree.
    *position* is the position among the panels with the same parent in the tree. If *position* is -1 it
    will be in inserted at the end. The other arguments are passed to the constructor of Panel.
    """
    parent, key = _getParentPanel(path)
    if parent is not None:
        currentPanels = parent.subPanels
    else:
        currentPanels = panels

    if key in currentPanels:
        raise ValueError("Panel '{}' does already exist".format('/'.join(key)))
    if position == -1:
        position = len(currentPanels)
    currentPanels.insert(position, key, Panel(path, *args, **kwargs))
    if PreferencesDialog._dialog is not None:
        PreferencesDialog._dialog.fillTreeWidget()


def removePanel(path):
    """Remove the panel with the given path."""
    parent, key = _getParentPanel(path)
    if parent is not None:
        currentPanels = parent.subPanels
    else: currentPanels = panels

    if key not in currentPanels:
        raise ValueError("Panel '{}' does not contain a subpanel '{}'".format(parent.path, key))
    del currentPanels[key]
    if PreferencesDialog._dialog is not None:
        PreferencesDialog._dialog.fillTreeWidget()


# Add core panels
addPanel('main', translate('Preferences', 'Main'), None, iconName='preferences-other')
addPanel('main/domainmanager', translate('Preferences', 'Domain manager'),
    callable = ('gui.preferences.domainmanager', 'DomainManager'),
    description = translate('Preferences',
        'A domain is a big category of elements, like "Music", "Movies", etc..'),
    iconName='preferences-domains')

addPanel('main/tagmanager', translate('Preferences', 'Tag manager'),
    callable = ('gui.preferences.tagmanager', 'TagManager'),
    description = translate('Preferences',
        'Note that you cannot change or remove tags that already appear in elements.'
        '<br />Use drag&drop to change the order in which tags are usually displayed.'),
    iconName='tag')

addPanel('main/flagmanager', translate('Preferences', 'Flag manager'),
    ('gui.preferences.flagmanager', 'FlagManager'),
    description = translate('Preferences', 'Flags can be added to elements to mark e.g. your favourite '
        'songs, CDs that you own, music that should go on your portable music player etc. Flags are not '
        'stored in music files, but only in the database.'),
    iconName='flag')

addPanel('main/filesystem', translate('Preferences', 'File system'),
    ('gui.preferences.filesystem', 'FilesystemSettings'),
    iconName='folder')

addPanel('main/shortcuts', translate('Preferences', 'Keyboard shortcuts'),
    ('gui.preferences.shortcuts', 'ShortcutSettings'),
    description=translate('Preferences', 'Assign shortcuts to common actions in Maestro. Double click on an '
                          'entry to set a keyboard shortcut.'),
    iconName='configure-shortcuts')


# Profile panels
def _addProfileCategory(category):
    classTuple = ('gui.preferences.profiles', 'ProfileConfigurationPanel', category)
    addPanel(path='profiles/' + category.name,
             title=category.title,
             callable=classTuple,
             description=category.description,
             iconName=category.iconName)


def _removeProfileCategory(category):
    removePanel("profiles/" + category.name)


