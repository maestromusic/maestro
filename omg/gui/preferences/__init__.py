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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ... import utils, logging, config, profiles

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

# Toplevel panels. Map path to Panel instance
panels = utils.OrderedDict()


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
          The callable will be invoked with the PreferencesDialog-instance and the arguments from the tuple.
          In the second case, the module will only be imported when the panel is actually shown.
        - *icon*: Icon that will be displayed in the preferences' menu.
        
    \ """
    def __init__(self, path, title, callable, iconPath=None, pixmapPath=None, description=''):
        self.path = path
        self.title = title
        self._callable = callable
        self.iconPath = iconPath
        self.pixmapPath = pixmapPath or ':omg/icons/preferences/preferences.png'
        self.description = description
        self.subPanels = utils.OrderedDict()
        
    def createWidget(self, buttonBar):
        """Create a configuration widget for this panel using the 'callable' argument of the constructor.
        *buttonBar* is the button bar of the panel and may be used to add buttons.
        """
        if isinstance(self._callable, tuple) and isinstance(self._callable[0], str):
            import importlib
            try:
                module = importlib.import_module('.'+self._callable[0], 'omg')
                self._callable = (getattr(module, self._callable[1]), ) + self._callable[2:]
            except ImportError:
                logger.error("Cannot import module '{}'".format(self._callable[0]))
                self._callable = None
            except AttributeError:
                logger.error("Module '{}' has no attribute '{}'"
                             .format(self._callable[0], self._callable[1]))
                self._callable = None
                
        if self._callable is None:
            return QtGui.QWidget()  
        elif not isinstance(self._callable, tuple):
            return self._callable(buttonBar)
        else: return self._callable[0](buttonBar, *self._callable[1:])
        
        
class PreferencesDialog(QtGui.QDialog):
    """The preferences dialog contains a list of panels on the left and the current panel's title together
    with the actual panel on the right. Except for the "main" panel which is shown at the beginning, it will
    only construct a panel (and in fact import the corresponding module) when the user selects it in the
    treeview.
    """ 
    # The one single instance
    _dialog = None
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Preferences - OMG"))
        self.setWindowIcon(utils.getIcon('preferences/preferences_small.png'))
        self.finished.connect(self._handleFinished)

        # Restore geometry
        if ("preferences_geometry" in config.binary and
                isinstance(config.binary["preferences_geometry"], bytearray)):
            success = self.restoreGeometry(config.binary["preferences_geometry"])
        else:
            success = False
        if not success: # Default geometry
            self.resize(800, 600)
        
        # map paths to the widget of a panel once it has been constructed
        self.panelWidgets = {}
        
        self.setLayout(QtGui.QVBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)
        
        splitter = QtGui.QSplitter(Qt.Horizontal)
        splitter.setContentsMargins(0,0,0,0)
        self.layout().addWidget(splitter, 1)
        
        self.treeWidget = QtGui.QTreeWidget()
        self.treeWidget.header().setVisible(False)
        self.treeWidget.itemSelectionChanged.connect(self._handleSelectionChanged)
        splitter.addWidget(self.treeWidget)
        
        self.stackedWidget = QtGui.QStackedWidget()
        splitter.addWidget(self.stackedWidget)
        
        splitter.setSizes([180, 620])
        
        self.fillTreeWidget()
        self.showPanel("main")
        PreferencesDialog._dialog = self
        
    def fillTreeWidget(self):
        """Fill the treeview with a tree of all panels."""
        self.treeWidget.clear()
        for path, panel in panels.items():
            item = QtGui.QTreeWidgetItem([panel.title])
            item.setData(0, Qt.UserRole, path)
            if panel.iconPath is not None:
                item.setIcon(0, QtGui.QIcon(panel.iconPath))
            self.treeWidget.addTopLevelItem(item)
            if len(panel.subPanels) > 0:
                self._addSubPanels(panel, item)

    def _addSubPanels(self, panel, item):
        """Add the subpanels of *panel* to the treeview. *item* is the QTreeWidgetItem for *panel*."""
        for p, subPanel in panel.subPanels.items():
            newPath = '{}/{}'.format(panel.path, p)
            newItem = QtGui.QTreeWidgetItem([subPanel.title])
            newItem.setData(0, Qt.UserRole, newPath)
            if subPanel.iconPath is not None:
                newItem.setIcon(0, QtGui.QIcon(subPanel.iconPath))
            item.addChild(newItem)
            if len(subPanel.subPanels) > 0:
                self._addSubPanels(subPanel, newItem)
            item.setExpanded(True)
        
    def showPanel(self, path):
        """Show the panel with the given path, constructing it, if it is shown for the first time."""
        if path not in self.panelWidgets:
            panel = self.getPanel(path)
            widget = PanelWidget(self, panel)
            self.panelWidgets[path] = widget
            self.stackedWidget.addWidget(widget)
        self.stackedWidget.setCurrentWidget(self.panelWidgets[path])
            
    def getPanel(self, path):
        """Return the Panel-instance (not the actual widget!) with the given *path*.""" 
        keys = path.split('/')
        i = 0
        currentPanels = panels
        while i < len(keys) - 1:
            currentPanels = panels[keys[i]].subPanels
            i += 1
        return currentPanels[keys[-1]]
        
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
        config.binary["preferences_geometry"] = bytearray(self.saveGeometry())


class PanelWidget(QtGui.QWidget):
    """PanelWidgets are used for the right part of the preferences dialog. They contain a title section,
    a configuration widget and a button bar. The configuration widget is created using the createWidget
    method of *panel*.
    """
    def __init__(self, dialog, panel):
        super().__init__(dialog)
        
        self.setLayout(QtGui.QVBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)
        
        frame = QtGui.QFrame()
        frame.setFrameStyle(QtGui.QFrame.StyledPanel | QtGui.QFrame.Sunken)
        frame.setLayout(QtGui.QVBoxLayout())
        frame.layout().setContentsMargins(0,0,0,0)
        self.layout().addWidget(frame)
        
        # Create title widget
        self.titleWidget = QtGui.QWidget()
        self.titleWidget.setObjectName("titleWidget")
        self.titleWidget.setStyleSheet(
                                "#titleWidget { background-color: white; border-bottom: 1px solid grey; }")
        
        titleLayout = QtGui.QHBoxLayout()
        titleLayout.setSpacing(20)
        self.titleWidget.setLayout(titleLayout)
        self.titleLabel = QtGui.QLabel()
        self.titleLabel.setText("<b>{}</b><br/>{}".format(panel.title, panel.description))
        self.titleLabel.setWordWrap(True)
        self.titleLabel.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        titleLayout.addWidget(self.titleLabel, 1)
        self.pixmapLabel = QtGui.QLabel()
        self.pixmapLabel.setPixmap(QtGui.QPixmap(panel.pixmapPath))
        self.pixmapLabel.setContentsMargins(20, 0, 20, 0)
        titleLayout.addWidget(self.pixmapLabel)
        frame.layout().addWidget(self.titleWidget)
        
        self.buttonBar = QtGui.QHBoxLayout()
        
        # Create configuration widget
        innerWidget = panel.createWidget(self.buttonBar)
        scrollArea = QtGui.QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setFrameStyle(QtGui.QFrame.NoFrame)
        scrollArea.setWidget(innerWidget)
        frame.layout().addWidget(scrollArea, 1)
        
        # Add button bar
        style = QtGui.QApplication.style()
        self.layout().addLayout(self.buttonBar)
        self.buttonBar.setContentsMargins(0, 0, style.pixelMetric(QtGui.QStyle.PM_LayoutRightMargin), 
                                          style.pixelMetric(QtGui.QStyle.PM_LayoutBottomMargin))
        if all(self.buttonBar.stretch(i) == 0 for i in range(self.buttonBar.count())):
            self.buttonBar.addStretch(1)
        closeButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogCloseButton),
                                        self.tr("Close"))
        closeButton.clicked.connect(dialog.accept)
        self.buttonBar.addWidget(closeButton)
        
    
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
    else: currentPanels = panels
        
    if key in currentPanels:
        raise ValueError("Panel '{}' does already exist".format('/'.join(keys)))
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
addPanel("main", translate("Preferences", "Main"), None)
addPanel("main/tagmanager", translate("Preferences", "Tag Manager"),
            ('gui.preferences.tagmanager', 'TagManager'),
            iconPath = ':omg/icons/tag_blue.png')
addPanel("main/flagmanager", translate("Preferences", "Flag Manager"),
            ('gui.preferences.flagmanager', 'FlagManager'),
            iconPath = ':omg/icons/flag_blue.png')
addPanel("main/filesystem", translate("Preferences", "File system"),
            ('filesystem.preferences', 'FilesystemSettings'),
            iconPath = ':omg/icons/folder.svg')

# Profile panels                   
def _addProfileCategory(category):
    classTuple = ('gui.profiles', 'ProfileConfigurationWidget', category)
    addPanel(path = "profiles/" + category.name,
             title = category.title,
             callable = classTuple,
             description = category.description,
             iconPath = category.iconPath,
             pixmapPath = category.pixmapPath)
    
def _removeProfileCategory(category):
    removePanel("profiles/" + category.name)
    
addPanel("profiles", translate("Preferences", "Profiles"), None,
         iconPath = ':omg/icons/preferences/profiles_small.png',
         pixmapPath = ':omg/icons/preferences/profiles.png')
profiles.manager.categoryAdded.connect(_addProfileCategory)
profiles.manager.categoryRemoved.connect(_removeProfileCategory)
for category in profiles.manager.categories:
    _addProfileCategory(category)


addPanel("plugins", translate("Preferences", "Plugins"), ('gui.preferences.plugins', 'PluginPanel'),
         iconPath = ':omg/icons/preferences/plugin.png',
         description = translate("Preferences", "Enable or disable plugins.<br />"
                                 "<b>Warning:</b> Changes will be performed immediately!"))
