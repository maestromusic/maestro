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

"""
This module implements OMG's flexible widget system. It consists of mainwindow.MainWindow which is the
toplevel window of OMG and a flexible amount of central widgets (which are displayed as tabs in the center)
and dock widgets. This module manages a list of all available widget types (confer WidgetData). Plugins may
add their own widgets using addWidgetData. From this list a View menu is created that allows the user to
show/hide central widgets and add new dock widgets. While there can be only at most one instance of each
central widget, dock widgets can have many instances (unless the unique-flag in the corresponding WidgetData
is set to True). At the end of the application the state and position of each widget is saved and at
application start it will be restored again.

To work with this system central widgets or dock widget must follow some rules:

    - Data about them must be registered using addWidgetData.
    - The widget must provide a constructor which takes a parent as first parameter, has a keyword parameter
    'location' and has default values for all other parameters. When invoked 'location' will be a
    DockLocation object storing the last location of the dock. Note that the location will be restored after
    the widget has been initialized and thus methods like isFloating do not provide valid information.
    - Dock widgets must be subclasses of QDockWidget.
    - Of course the generic system can only store the position and not the inner state of each widget. If a
    widget wants to store its state, it must provide the method saveState to return a state object to be
    saved and a keyword parameter 'state' in the constructor (with default value None) to restore the state
    again. The state object may be anything that can be stored in a variable in config.storage (i.e. any
    combination of standard Python types including lists and dicts).

"""

import functools,itertools,collections

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt
QWIDGETSIZE_MAX = 16777215

from .. import application,config,constants,logging,utils
from . import selection,dialogs

# This will contain the single instance of MainWindow once it is initialized
mainWindow = None

logger = logging.getLogger(__name__)

# Data about the available widgets
_widgetData = []

# Global selection
_globalSelectionLevel = None
_globalSelection = None

# "Name" of the default perspective (will never be displayed)
DEFAULT_PERSPECTIVE = ''


def addWidgetData(data):
    """Add widget data to the list of registered widgets."""
    if data in _widgetData:
        logger.warning("Attempt to add widget data twice: {}".format(data))
    else: _widgetData.append(data)
    if mainWindow is not None:
        mainWindow._widgetDataAdded(data)


def removeWidgetData(id):
    """Remove the WidgetData instance with the given id from the list of registered widgets."""
    data = WidgetData.fromId(id)
    if data is None:
        logger.warning("Attempt to remove nonexistent widget data: {}".format(id))
    else: _widgetData.remove(data)
    if mainWindow is not None:
        mainWindow._widgetDataRemoved(data)


class WidgetData:
    """A WidgetData instance stores information about one type of widget (central and/or dock). It contains
    the following information:

        - id: a unique string to identify the WidgetData. This string is used to store the widgets
          persistently.
        - name: a nice name which will be displayed in the View menu.
        - theClass: the class that must be instantiated to create a widget of this type. Remember that this
          must be a subclass of QDockWidget if dock is true.
        - central: Whether this widget may be used in the center.
        - dock: Whether this widget may be used as dock widget.
        - unique: Only relevant for dock widgets. It stores whether there may be more than one instance of
          this widget.
        - preferredDockArea: Only relevant for dock widgets. Contains the dock area where this widget will be
          placed when it is newly created. One of the values of Qt.DockWidgetAreas.
        - icon: Optional. An icon which is displayed in tabs or docks for this widget.

    """
    def __init__(self,id,name,theClass,central=True,dock=True,
                 unique=False,preferredDockArea=None,icon=None):
        if not (central or dock):
            raise ValueError("Either central or dock must be True.")
        self.id = id
        self.name = name
        self.theClass = theClass
        self.central = central
        self.dock = dock
        self.unique = unique
        self.preferredDockArea = preferredDockArea or Qt.BottomDockWidgetArea
        self.icon = icon

    def __eq__(self,other):
        return self.id == other.id

    def __ne__(self,other):
        return self.id != other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return "<WidgetData({},{},{})>".format(self.id,self.name,self.theClass.__name__)

    @staticmethod
    def fromId(id):
        """Get the registered WidgetData with the given id. Return None if such data cannot be found."""
        for data in _widgetData:
            if data.id == id:
                return data
        else: return None


class MainWindow(QtGui.QMainWindow):
    """The main window of OMG. It contains a CentralTabWidget as actual central widget (in Qt sense) so that
    several widgets (in tabs) can be displayed as central widgets (in OMG's sense)."""
    # Use gui.selection.changed instead
    _globalSelectionChanged = QtCore.pyqtSignal(selection.Selection)

    def __init__(self,parent=None):
        super().__init__(parent)

        self.setDockNestingEnabled(True)
        self.setWindowTitle(self.tr('OMG version {}').format(constants.VERSION))
        self.setWindowIcon(QtGui.QIcon(":omg/omg_square.svg"))

        selection.changed = self._globalSelectionChanged

        global mainWindow
        mainWindow = self

        # Resize and move the widget to the size and position it had when the program was closed
        if "mainwindow_maximized" in config.binary and config.binary["mainwindow_maximized"]:
            self.showMaximized()
        else:
            if "mainwindow_geometry" in config.binary \
                  and isinstance(config.binary["mainwindow_geometry"],bytearray):
                success = self.restoreGeometry(config.binary["mainwindow_geometry"])
            else: success = False
            if not success:  # Default geometry
                screen = QtGui.QDesktopWidget().availableGeometry()
                self.resize(min(1000,screen.width()),min(800,screen.height()))
                # Center the window
                screen = QtGui.QDesktopWidget().screenGeometry()
                size = self.geometry()
                self.move((screen.width() - size.width()) / 2,(screen.height() - size.height()) / 2)

        self.setCentralWidget(CentralTabWidget())
        self.initMenus()
        if DEFAULT_PERSPECTIVE in config.storage.gui.perspectives:
            try:
                self.restorePerspective()
            except Exception as e:
                logger.exception(e)
                self.createDefaultWidgets()
        else: self.createDefaultWidgets()
        self.updateWidgetMenus()  # view menu can only be initialized after all widgets have been created


        # TODO: Replace this hack by something clever.
        browserShortcut = QtGui.QShortcut(QtGui.QKeySequence(self.tr("Ctrl+F")),self,
                                          self._handleBrowserShortcut)
        self.show()
        QtCore.QTimer.singleShot(1000, self._initLater)

    def _initLater(self):
        print("_INITLATER")
        if "mainwindow_dockwidget_sizes" in config.binary and "mainwindow_maximized" in config.binary and config.binary["mainwindow_maximized"]:
            print("RESTORE")
            print(config.binary["mainwindow_dockwidget_sizes"])
            for w in self.dockWidgets():
                name = w.objectName()
                if name in config.binary["mainwindow_dockwidget_sizes"]:
                    w.resize(*config.binary["mainwindow_dockwidget_sizes"][name])
                    

    def centralWidgets(self):
        return [self.centralWidget().widget(i) for i in range(self.centralWidget().count())]

    def dockWidgets(self,includeHidden=False):
        # Get all dock widgets except those in the central widget.
        # When dock widgets are closed, they are actually only hidden and marked for later deletion
        # (via QObject.deleteLater). For this reason we skip hidden widgets.
        return [w for w in self.findChildren(QtGui.QDockWidget)
                if (includeHidden or w.isVisible()) and not self.centralWidget().isAncestorOf(w)]

    def widgetExists(self,data):
        """Return whether any widget for the given WidgetData exists (either as dock widget or as central
        widget)."""
        return any(w.widgetData == data for w in itertools.chain(self.centralWidgets(),
                                                                 self.dockWidgets()))

    def close(self):
        self.savePerspective()
        config.binary["mainwindow_maximized"] = self.isMaximized()
        if self.isMaximized():
            config.binary["mainwindow_dockwidget_sizes"] = \
                        {w.objectName(): (w.size().width(), w.size().height())
                         for w in self.dockWidgets(includeHidden=True)}
            print("SAVE")
            print(config.binary["mainwindow_dockwidget_sizes"])
        config.binary["mainwindow_geometry"] = bytearray(self.saveGeometry())
        super().close()

    def initMenus(self):
        """Initialize menus except the view menu which cannot be initialized before all widgets have been
        loaded."""
        self.menus = {}

        # EDIT
        self.menus['edit'] = self.menuBar().addMenu(self.tr("&Edit"))
        self.menus['edit'].addAction(application.stack.createUndoAction())
        self.menus['edit'].addAction(application.stack.createRedoAction())

        action = QtGui.QAction(utils.getIcon('preferences/preferences_small.png'),
                               self.tr("Preferences..."),
                               self)
        
        action.triggered.connect(self.showPreferences)
        self.menus['edit'].addAction(action)

        # VIEW
        self.menus['view'] = self.menuBar().addMenu(self.tr("&View"))

        self.menus['centralwidgets'] = self.menus['view'].addMenu(self.tr("New central widget"))
        self.menus['dockwidgets'] = self.menus['view'].addMenu(self.tr("New dock widget"))
        self.menus['perspectives'] = self.menus['view'].addMenu(self.tr("Perspective"))
        self.updatePerspectiveMenu()
        self.menus['view'].addSeparator()

        self.hideTitleBarsAction = QtGui.QAction(self.tr("Hide title bars"),self)
        self.hideTitleBarsAction.setCheckable(True)
        self.menus['view'].addAction(self.hideTitleBarsAction)

        self.freezeLayoutAction = QtGui.QAction(self.tr("Freeze layout"),self)
        self.freezeLayoutAction.setCheckable(True)
        self.freezeLayoutAction.setChecked(self.isLayoutFrozen())
        self.freezeLayoutAction.toggled.connect(self.setLayoutFrozen)
        self.menus['view'].addAction(self.freezeLayoutAction)

        self.fullscreenAction = QtGui.QAction(self.tr("&Fullscreen"),self)
        self.fullscreenAction.setCheckable(True)
        self.fullscreenAction.setChecked(False)
        self.fullscreenAction.setShortcut(self.tr("F12"))
        self.fullscreenAction.toggled.connect(self._handleFullscreen)
        self.menus['view'].addAction(self.fullscreenAction)

        # EXTRAS
        self.menus['extras'] = self.menuBar().addMenu(self.tr("&Extras"))

        # HELP
        self.menus['help'] = self.menuBar().addMenu(self.tr("&Help"))

        action = QtGui.QAction(self.tr("&About"),self)
        action.triggered.connect(self.showAboutDialog)
        self.menus['help'].addAction(action)

    def _handleFullscreen(self,state):
        """React to the 'Fullscreen' option in the view menu."""
        if state:
            self.showFullScreen()
        else: self.showNormal()

    def isLayoutFrozen(self):
        """When the layout is frozen, it is impossible to resize the window or dockwidgets. Also, it is
        impossible to move or close dockwidgets."""
        return config.storage.gui.layoutFrozen

    def setLayoutFrozen(self,frozen,force=False):
        """Freeze/unfreeze layout. When the layout is frozen, it is impossible to resize the window or
        dockwidgets. Also, it is impossible to move or close dockwidgets."""
        frozen = bool(frozen)
        if force or frozen != config.storage.gui.layoutFrozen:
            config.storage.gui.layoutFrozen = frozen
            if frozen:
                self.setFixedSize(self.size())
            else: self.setFixedSize(QWIDGETSIZE_MAX,QWIDGETSIZE_MAX)
            self.centralWidget().closeButton.setVisible(not frozen)
            for widget in self.dockWidgets():
                widget.setFrozen(frozen)

    def updateWidgetMenus(self):
        """Update the central/dock widget menus whenever the list of registered widgets has changed."""
        def _updateMenu(widgetData,menu,method):
            menu.clear()
            for data in widgetData:
                action = QtGui.QAction(data.name,menu)
                # Choose the signal without "checked" argument because *method* may accept optional arguments.
                action.triggered[tuple()].connect(functools.partial(method,data))
                if data.icon is not None:
                    action.setIcon(data.icon)
                if data.unique:
                    action.setObjectName(data.id)
                    if self.widgetExists(data):
                        action.setEnabled(False)
                menu.addAction(action)

        _updateMenu([data for data in _widgetData if data.central],
                    self.menus['centralwidgets'],
                    self.addCentralWidget)
        _updateMenu([data for data in _widgetData if data.dock],
                    self.menus['dockwidgets'],
                    self.addDockWidget)

    def updatePerspectiveMenu(self):
        menu = self.menus['perspectives']
        menu.clear()

        for name,perspective in config.storage.gui.perspectives.items():
            if name == DEFAULT_PERSPECTIVE:
                continue
            action = QtGui.QAction(name,self)
            action.triggered.connect(functools.partial(self.restorePerspective,name))
            menu.addAction(action)
        if len(menu.actions()) > 0:
            menu.addSeparator()
        action = QtGui.QAction(self.tr("Save perspective..."),self)
        action.triggered.connect(self._handleSavePerspective)
        menu.addAction(action)

    def addCentralWidget(self,data,state=None):
        """Add a central widget corresponding to the given WidgetData. If a widget of this type existed and
        was hidden once, simply show it again. Otherwise create a new widget. In this case *state* will be
        passed to the constructor, if the class has a 'saveState'-method. Return the widget."""
        if data.unique and self.widgetExists(data):
            raise ValueError("There can be at most one widget of type '{}'.".format(data.id))
        if hasattr(data.theClass,'saveState'):
            widget = data.theClass(self,state)
        else: widget = data.theClass(self)
        widget.widgetData = data
        if data.icon is not None:
            self.centralWidget().addTab(widget,data.icon,data.name)
        else: self.centralWidget().addTab(widget,data.name)
        self.centralWidget().setCurrentWidget(widget)
        if data.unique:
            self._setUniqueWidgetActionEnabled(data.id,False)
            widget.installEventFilter(self)
        return widget

    def addDockWidget(self,data):
        """Add a dock widget corresponding to the given WidgetData and return it."""
        # The difference between _createDockWidget and addDockWidget is that the latter really adds the
        # widget to the MainWindow. The former is also used by restoreLayout and there dockwidgets are added
        # by QMainWindow.restoreState.
        frozen = self.isLayoutFrozen()
        if frozen:
            self.setLayoutFrozen(False)
        widget = self._createDockWidget(data,DockLocation(data.preferredDockArea,False))
        super().addDockWidget(data.preferredDockArea,widget)
        if frozen:
            # Wait until updated dockwidgets sizes are available
            QtCore.QTimer.singleShot(0,functools.partial(self.setLayoutFrozen,True))

    def _createDockWidget(self,data,location,objectName=None,state=None):
        """Create a new dock widget for the given WidgetData and set its objectName to *objectName*. If that
        is None, compute an unused objectName."""
        if data.unique and self.widgetExists(data):
            raise ValueError("There can be at most one widget of type '{}'.".format(data.id))

        # For the unique object name required by QMainWindow.restoreState compute the first string of the
        # form data.id+<int> that is not already in use. Unique dock widgets get simply their data.id as
        # object name. This is also used by the event filter to find and enable the corresponding action in
        # the view menu if the dock is closed.
        if objectName is None:
            if data.unique:
                objectName = data.id
            else:
                existingNames = [widget.objectName() for widget in self.dockWidgets()]
                i = 1
                while data.id + str(i) in existingNames:
                    i += 1
                objectName = data.id + str(i)

        args = {'location': location,'title': data.name}
        if hasattr(data.theClass,'saveState'):
            args['state'] = state
        if data.icon is not None:
            args['icon'] = data.icon
        widget = data.theClass(self,**args)
        widget.setObjectName(objectName)
        widget.widgetData = data
        if data.unique:
            self._setUniqueWidgetActionEnabled(data.id,False)
            widget.installEventFilter(self)
        return widget

    def _handleSavePerspective(self):
        """Ask the user for a name and store the current widget layout and state under this name."""
        name,ok = QtGui.QInputDialog.getText(self,self.tr("Save perspective"),
                            self.tr("Save the layout and state of the current widgets as a perspective."
                                    "Please specify a name for the new perspective:"))
        if ok and len(name) > 0 and name != DEFAULT_PERSPECTIVE:
            self.savePerspective(name)
            self.updatePerspectiveMenu()

    def restorePerspective(self,name=DEFAULT_PERSPECTIVE):
        """Restore the layout and state of all central and dock widgets from the perspective with the given
        name. If no *name* is given, use the default perspective."""
        perspective = config.storage.gui.perspectives[name]
        self.centralWidget().clear()
        for widget in self.dockWidgets():
            # Dock widgets have the Qt.WA_DeleteOnClose flag. However, they are not directly deleted, but
            # when control returns to the event loop (QObject.deleteLater). Thus the widgets do still exist
            # when QMainWindow.restoreState is called. This may lead to errors when old and new widgets have
            # the same object name. Hence we clear those names here.
            widget.setObjectName('')
            widget.close()

        # Restore central widgets
        for id,state in perspective['central']:
            data = WidgetData.fromId(id)
            # It may happen that data is None (for example if it belongs to a widget from a plugin and this
            # plugin has been removed since the last application shutdown). Simply do not load this widget
            if data is not None:
                widget = self.addCentralWidget(data,state)
            else: logger.info("Could not load central widget '{}'".format(data))
        if perspective['centralTabIndex'] < self.centralWidget().count():
            self.centralWidget().setCurrentIndex(perspective['centralTabIndex'])

        # Restore dock widgets (create them with correct object names and use QMainWindow.restoreState)
        dockWidgets = []
        for id,objectName,location,state in perspective['dock']:
            data = WidgetData.fromId(id)
            if data is not None:  # As above it may happen that data is None.
                widget = self._createDockWidget(data,DockLocation(*location),objectName,state)
                dockWidgets.append(widget)
            else: logger.info("Could not load dock widget '{}' with object name '{}'"
                              .format(data,objectName))

        self.hideTitleBarsAction.setChecked(perspective['hideTitleBars'])

        # Restore dock widget positions
        success = False
        if 'mainwindow_state' in config.binary and name in config.binary['mainwindow_state']:
            success = self.restoreState(config.binary['mainwindow_state'][name])
        if not success:
            for widgets in dockWidgets:
                super().addDockWidget(widget.widgetData.preferredDockArea,widget)

        if self.isLayoutFrozen():
            # self.dockWidgets() does not work until event queue is reentered.
            QtCore.QTimer.singleShot(0,functools.partial(self.setLayoutFrozen,True,force=True))

    def savePerspective(self,name=DEFAULT_PERSPECTIVE):
        """Save the layout and state of all central and dock widgets. If no *name* is given, the default
        perspective will be overwritten."""
        # Store central widgets
        centralWidgetList = []
        for widget in self.centralWidgets():
            if hasattr(widget,"saveState"):
                state = widget.saveState()
            else: state = None
            centralWidgetList.append((widget.widgetData.id,state))

        # Store dock widgets that are visible and remove the rest so saveState won't store their position
        dockWidgetList = []
        for widget in self.dockWidgets(includeHidden=True):
            if hasattr(widget,"saveState"):
                state = widget.saveState()
            else: state = None
            location = (self.dockWidgetArea(widget),widget.isFloating())
            dockWidgetList.append((widget.widgetData.id,widget.objectName(),location,state))

        perspective = {'central': centralWidgetList,
                       'dock': dockWidgetList,
                       'centralTabIndex': self.centralWidget().currentIndex(),
                       'hideTitleBars': self.hideTitleBarsAction.isChecked()
                       }

        config.storage.gui.perspectives[name] = perspective

        # Copy the bytearray to avoid memory access errors
        if 'mainwindow_state' not in config.binary \
                    or not isinstance(config.binary["mainwindow_state"],dict):
            config.binary['mainwindow_state'] = {}
        config.binary['mainwindow_state'][name] = bytearray(self.saveState())

    def createDefaultWidgets(self):
        """Create the default set of central and dock widgets. Use this method if no widgets can be loaded
        from the storage file."""
        self.setLayoutFrozen(False)
        for id in 'playlist','editor':
            data = WidgetData.fromId(id)
            self.addCentralWidget(data)
        self.centralWidget().setCurrentIndex(1)
        for id in 'browser', 'filesystembrowser', 'tageditor', 'playback':
            data = WidgetData.fromId(id)
            self.addDockWidget(data)

    def showPreferences(self):
        """Open preferences dialog."""
        from . import preferences
        preferences.show("main")

    def showTagManager(self):
        """Open tag manager within preferences."""
        from . import preferences
        preferences.show("main/tagmanager")

    def showFlagManager(self):
        """Open flag manager within preferences."""
        from . import preferences
        preferences.show("main/flagmanager")

    def showAboutDialog(self):
        """Display the About dialog."""
        box = QtGui.QMessageBox(QtGui.QMessageBox.NoIcon,self.tr("About OMG"),
                '<div align="center"><img src=":omg/omg.png" /><br />'
                + self.tr("This is OMG version {} by Martin Altmayer and Michael Helmling.")
                             .format(constants.VERSION)
                + '</div>',
                QtGui.QMessageBox.Ok)
        box.exec_()

    def _widgetDataAdded(self,data):
        """This is called when new widget data has been added."""
        self.updateWidgetMenus()

    def _widgetDataRemoved(self,data):
        """This is called when widget data has been removed."""
        for widget in itertools.chain(self.centralWidgets(),self.dockWidgets()):
            if widget.widgetData == data:
                widget.setParent(None)
        self.updateWidgetMenus()

    def _setUniqueWidgetActionEnabled(self,id,enabled):
        """Enable/disable the menu actions for a unique widget type. *id* is the id of a registered
        WidgetData-instance having the 'unique'-flag.
        """
        for menuId in 'centralwidgets','dockwidgets':
            action = self.menus[menuId].findChild(QtGui.QAction,id)
            if action is not None:
                action.setEnabled(enabled)

    def eventFilter(self,object,event):
        if event.type() == QtCore.QEvent.Close:
            if object.widgetData.unique:
                # If a unique widget has been closed, enable the corresponding action in the
                # view menu. The event filter is only installed on unique widgets.
                self._setUniqueWidgetActionEnabled(object.widgetData.id,True)
        return False  # don't stop the event

    def _handleBrowserShortcut(self):
        """Set the focus to the next browser' searchbox (By pressing the browser shortcut repeatedly
        the focus will run through all browsers).
        """
        browserDocks = self.getWidgets('browser')
        for i,browserDock in enumerate(browserDocks):
            if browserDock.searchBox.hasFocus():
                nextIndex = (i + 1) % len(browserDocks)
                browserDocks[nextIndex].searchBox.setFocus(Qt.OtherFocusReason)
                return
        browserDocks[0].searchBox.setFocus(Qt.ShortcutFocusReason)

    def getWidgets(self,id):
        """Given the id of a WidgetData-instance, return all widgets (central and dock) of that WidgetData."""
        return [widget for widget in itertools.chain(self.centralWidgets(),self.dockWidgets())
                        if widget.widgetData.id == id]

    def closeEvent(self,event):
        # If this widget.okToClose opens a dialog, we will get a new change event. Use this list to
        # avoid calling okToClose on the same widget twice.
        if not hasattr(self,'_okClosed'):
            self._okClosed = []
        for widget in itertools.chain(self.centralWidgets(),self.dockWidgets()):
            if hasattr(widget,"okToClose") and widget not in self._okClosed and not widget.okToClose():
                event.ignore()
                return
            else: self._okClosed.append(widget)
        event.accept()


class CentralTabWidget(QtGui.QTabWidget):
    """This tab widget is used as the main window's central widget. Via the 'View'-menu the user can choose
    which widgets should be inside the tabs."""
    # The option dialog if it is open, and the index of the tab that was active when the dialog was closed.
    _dialog = None
    _lastDialogTabIndex = 0

    def __init__(self):
        super().__init__()
        self.setMovable(True)
        self.setTabBar(CentralTabBar())
        self._lastDialogTabIndexes = {}
        self.currentChanged.connect(self._handleCurrentChanged)

        # Create corner widget
        from . import dockwidget
        cornerWidget = QtGui.QWidget()
        cornerLayout = QtGui.QHBoxLayout(cornerWidget)
        cornerLayout.setContentsMargins(2,0,0,0)
        cornerLayout.setSpacing(0)
        self.optionButton = dockwidget.DockWidgetTitleButton('options')
        self.optionButton.clicked.connect(self._handleOptionButton)
        cornerLayout.addWidget(self.optionButton)
        self.closeButton = dockwidget.DockWidgetTitleButton('close')
        self.closeButton.clicked.connect(self._handleCloseButton)
        cornerLayout.addWidget(self.closeButton)
        self.setCornerWidget(cornerWidget)

    def minimumSizeHint(self):
        return QtCore.QSize(0,0)

    def getWidgets(self):
        return [self.widget(i) for i in range(self.count())]

    def _handleCurrentChanged(self):
        widget = self.currentWidget()
        hasOptionDialog = hasattr(widget,'hasOptionDialog') and widget.hasOptionDialog()
        self.optionButton.setEnabled(hasOptionDialog)

    def _handleCloseButton(self):
        """React to the corner widget's close button: Close the current tab."""
        self.removeTab(self.currentIndex())

    def clear(self):
        for i in range(self.count()):
            self.removeTab(0)

    def removeTab(self,index):
        tab = self.widget(index)
        super().removeTab(index)
        tab.close()
        tab.setParent(None)

    def _handleOptionButton(self):
        """React to the corner widget's option button: Open the option dialog of the current widget."""
        self._dialog = self.currentWidget().createOptionDialog(self.optionButton)
        if self._dialog is not None:
            self._dialog.installEventFilter(self)
            if isinstance(self._dialog,dialogs.FancyTabbedPopup) \
                        and self.currentWidget() in self._lastDialogTabIndexes:
                self._dialog.tabWidget.setCurrentIndex(self._lastDialogTabIndexes[self.currentWidget()])
            self._dialog.show()

    def eventFilter(self,object,event):
        if event.type() == QtCore.QEvent.Close and self._dialog is not None:
            if isinstance(self._dialog,dialogs.FancyTabbedPopup):
                self._lastDialogTabIndexes[self.currentWidget()] = self._dialog.tabWidget.currentIndex()
            self._dialog = None
        return False  # do not filter the event out


class CentralTabBar(QtGui.QTabBar):
    """This tabbar makes a tab active when a drag enters its tabbutton."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)  # no dragEnterEvents with this line

    def dragEnterEvent(self,event):
        tabIndex = self.tabAt(event.pos())
        if tabIndex != -1 and tabIndex != self.currentIndex():
            self.setCurrentIndex(tabIndex)
        return super().dragEnterEvent(event)


class DockLocation:
    """This small class stores location information for dockwidgets when the layout is saved/restored. Note
    that during restoring the widgets are created before they are placed at their positions. Thus methods
    like isFloating won't provide valid results. In order to have the location information in the
    dock's constructor we have to separately store and pass a DockLocation object.
    
    Parameters:
        - area: Qt.DockWidgetArea of the widget
        - floating: Whether the widget is floating (i.e. using its own window). 
    """
    def __init__(self,area,floating):
        self.area = area
        self.floating = floating

    def __str__(self):
        return "<DockLocation {},{}>".format(self.area,self.floating)
