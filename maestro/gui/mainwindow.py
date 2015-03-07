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

"""
This module implements Maestro's flexible widget system. It consists of mainwindow.MainWindow which is the
toplevel window of Maestro and a flexible amount of central widgets (which are displayed as tabs in the center)
and docked widgets. This module manages a list of all available widget classes (confer widgets.WidgetClass).
Plugins may add their own widgets using widgets.addClass. From this list a View menu is created that allows
the user to add widgets. At the end of the application the state and position of each widget is saved
and at application start it will be restored again.

To work with this system central widgets or docked widgets must follow some rules:

    - A corresponding WidgetClass about them must be registered using widgets.addClass.
    - The widget must be a subclass of widgets.Widget.
    - Of course the generic system can only store the position and not the inner state of each widget. If a
    widget wants to store its state, it must reimplement the method saveState to return an object that
    will be passed to the constructor on the next startup.

"""

import functools

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from maestro import application, config, logging, utils, stack, VERSION, widgets
from maestro.gui import actions, selection, dialogs


translate = QtCore.QCoreApplication.translate
QWIDGETSIZE_MAX = 16777215

# This will contain the single instance of MainWindow once it is initialized
mainWindow = None
""":type: MainWindow"""

# "Name" of the default perspective (will never be displayed)
DEFAULT_PERSPECTIVE = ''
     
        
class MainWindow(QtWidgets.QMainWindow):
    """The main window of Maestro. It contains a CentralTabWidget as actual central widget (in Qt sense)
    so that several widgets (in tabs) can be displayed as central widgets (in Maestro's sense)."""
    # Do not use this! Use gui.selection.changed instead. We just need a QObject to put the signal in.
    _globalSelectionChanged = QtCore.pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._isClosing = False

        self.setDockNestingEnabled(True)
        self.setWindowTitle(self.tr('Maestro version {}').format(VERSION))
        self.setWindowIcon(QtGui.QIcon(":maestro/omg_square.svg"))

        selection.changed = self._globalSelectionChanged

        global mainWindow
        application.mainWindow = mainWindow = self

        self.currentWidgets = {}
        """:type: dict[str, widgets.Widget]"""

        # Resize and move the widget to the size and position it had when the program was closed
        if config.binary.gui.mainwindow_maximized:
            self.showMaximized()
        else:
            if config.binary.gui.mainwindow_geometry is not None:
                success = self.restoreGeometry(config.binary.gui.mainwindow_geometry)
            else: success = False
            if not success:  # Default geometry
                screen = QtWidgets.QDesktopWidget().availableGeometry()
                self.resize(min(1000, screen.width()), min(800, screen.height()))
                # Center the window
                screen = QtWidgets.QDesktopWidget().screenGeometry()
                size = self.geometry()
                self.move((screen.width() - size.width()) / 2, (screen.height() - size.height()) / 2)

        self.setCentralWidget(CentralTabWidget())
        self.initMenus()

        if DEFAULT_PERSPECTIVE in config.storage.gui.perspectives:
            try:
                self.restorePerspective()
            except Exception:
                logging.exception(__name__, "Exception when restoring perspective.")
                self.createDefaultWidgets()
        else:
            self.createDefaultWidgets()
        
        self.updateWidgetMenus()  # view menu can only be initialized after all widgets have been created
        
        QtWidgets.QApplication.instance().focusChanged.connect(self._handleFocusChanged)
        self.show()

    def closeEvent(self, event):
        # When the window is closed in a usual way this method is first called when the close icon is
        # clicked and a second time when the main shutdown code in application.py calls mainWindow.close.
        if self._isClosing:
            return
        self._isClosing = True
        for widget in self.getWidgets():
            if not widget.canClose():
                event.ignore()
                self._isClosing = False
                return  
        event.accept()
        self.savePerspective()
        for widget in self.getWidgets():
            self.closeWidget(widget, ask=False)
        config.binary.gui.mainwindow_maximized = self.isMaximized()
        config.binary.gui.mainwindow_geometry = bytearray(self.saveGeometry())
                   
    # Dock Widget handling
    #=======================================================================================================
    def centralWidgets(self, id=None):
        """Return all central widgets. If *id* is given return only those with this widgetClass-id."""
        widgets = [self.centralWidget().widget(i) for i in range(self.centralWidget().count())]
        return [w for w in widgets if id is None or w.widgetClass.id == id]

    def dockedWidgets(self, id=None):
        """Return all docked widgets. These are not the DockWidgets, but their contents.
        If *id* is given return only those with this widgetClass-id."""
        return [w.widget() for w in self.dockWidgets(id)]
        
    def dockWidgets(self, id=None):
        """Return all dock widgets. If *id* is given return only those with this widgetClass-id."""
        from . import dockwidget
        return [w for w in self.findChildren(dockwidget.DockWidget)
                if w.objectName() != '' # dock wigdets without object name have been deleted
                    and (id is None or w.widget().widgetClass.id == id) 
                    and not self.centralWidget().isAncestorOf(w)]

    def getWidgets(self, id=None):
        """Return all widgets (central and docked). If *id* is given return only those with this 
        widgetClass-id."""
        return self.centralWidgets(id) + self.dockedWidgets(id)

    def widgetExists(self, id):
        """Return whether any widget of the WidgetClass identified by *id* exists (either as docked widget
        or as central widget).
        """
        return len(self.getWidgets(id)) > 0

    def addCentralWidget(self, widgetClass, state=None):
        """Add a central widget corresponding to the given WidgetClass. *state* will be passed to the
        constructor. Return the widget."""
        if isinstance(widgetClass, str):
            widgetClass = widgets.getClass(widgetClass)
        if 'central' not in widgetClass.areas:
            raise ValueError("Widget '{}' is not allowed in central area".format(widgetClass.id))
        if widgetClass.unique and self.widgetExists(widgetClass.id):
            raise ValueError("There can be at most one widget of class '{}'.".format(widgetClass.id))
        try:
            widget = widgetClass.theClass(state=state, widgetClass=widgetClass, area='central')
        except Exception as e:
            logging.exception(__name__, "Could not load central widget '{}'".format(widgetClass.id))
            return None
        self.currentWidgets[widgetClass.id] = widget
        if widgetClass.icon is not None:
            self.centralWidget().addTab(widget, widgetClass.icon, widgetClass.name)
        else: self.centralWidget().addTab(widget, widgetClass.name)
        self.centralWidget().setCurrentWidget(widget)
        widget.initialize(state)
        return widget

    def addDockWidget(self, widgetClass):
        """Add a dock widget corresponding to the given WidgetClass and return it."""
        # The difference between _createDockWidget and addDockWidget is that the latter really adds the
        # widget to the MainWindow. The former is also used by restoreLayout and there dockwidgets are added
        # by QMainWindow.restoreState.
        if isinstance(widgetClass, str):
            widgetClass = widgets.getClass(widgetClass)
        if widgetClass.allowedDockAreas() == Qt.NoDockWidgetArea:
            raise ValueError("Widget '{}' is not allowed as dock widget.".format(widgetClass.id))
        frozen = self.isLayoutFrozen()
        if frozen:
            self.setLayoutFrozen(False)
        area = widgetClass.preferredDockArea
        dock = self._createDockWidget(widgetClass, area)
        if dock is None:
            return None
        super().addDockWidget(widgetClass.preferredDockAreaFlag(), dock)
        if frozen:
            # Wait until updated dockwidgets sizes are available
            QtCore.QTimer.singleShot(0, functools.partial(self.setLayoutFrozen, True))
        return dock

    def _createDockWidget(self, widgetClass, area, objectName=None, state=None):
        """Create a new dock widget for the given WidgetClass and set its objectName to *objectName*.
        If that is None, compute an unused objectName."""
        if widgetClass.unique and self.widgetExists(widgetClass.id):
            raise ValueError("There can be at most one widget of class '{}'.".format(widgetClass.id))

        # For the unique object name required by QMainWindow.restoreState compute the first string of the
        # form widgetClass.id+<int> that is not already in use. Unique dock widgets get simply their
        # widgetClass.id as object name. This is also used by the event filter to find and enable the
        # corresponding action in the view menu if the dock is closed.
        if objectName is None:
            if widgetClass.unique:
                objectName = widgetClass.id
            else:
                existingNames = [widget.objectName() for widget in self.dockWidgets()]
                i = 1
                while widgetClass.id + str(i) in existingNames:
                    i += 1
                objectName = widgetClass.id + str(i)

        try:
            widget = widgetClass.theClass(state=state, widgetClass=widgetClass, area=area)
        except Exception as e:
            logging.exception(__name__, "Could not load docked widget '{}'".format(widgetClass.id))
            return None
        self.currentWidgets[widgetClass.id] = widget
        from . import dockwidget
        dock = dockwidget.DockWidget(widget, title=widgetClass.name, icon=widgetClass.icon)
        dock.setObjectName(objectName)
        dock.setAllowedAreas(widgetClass.allowedDockAreas())
        widget.initialize(state)
        return dock
    
    def closeWidget(self, widget, ask=True):
        """Close the given widget (central or docked). If *ask* is true (default) call the widget's
        canClose-method first and do not close the widget if it returns False.
        """
        if ask and not widget.canClose():
            return
        container = widget.containingWidget()
        if container is self.centralWidget():
            index = self.centralWidget().indexOf(widget)
            widget.close()
            self.centralWidget().removeTab(index)
        else:
            # Dock widgets have the Qt.WA_DeleteOnClose flag. However, they are not directly deleted, but
            # when control returns to the event loop (QObject.deleteLater).
            # In restorePerspective this causes old widgets to still exist when QMainWindow.restoreState
            # is called. This may lead to errors when old and new widgets have the same object name.
            # Hence we clear those names here.
            widget.setObjectName('')
            container.setObjectName('')
            container.close() # closing the dock will also close the widget
            
        if widget.widgetClass.unique:
            self._setUniqueWidgetActionEnabled(widget.widgetClass.id, True)
            
    def _widgetClassAdded(self, widgetClass):
        """This is called when a new widgetClass has been added."""
        self.updateWidgetMenus()

    def _widgetClassRemoved(self, widgetClass):
        """This is called when a widgetClass has been removed."""
        for widget in self.getWidgets(widgetClass.id):
            self.closeWidget(widget, ask=False)
        self.updateWidgetMenus()
       
    # Perspectives
    #========================================================================================================
    def _handleSavePerspective(self):
        """Ask the user for a name and store the current widget layout and state under this name."""
        name, ok = QtWidgets.QInputDialog.getText(self, self.tr("Save perspective"),
                            self.tr("Save the layout and state of the current widgets as a perspective."
                                    "Please specify a name for the new perspective:"))
        if ok and len(name) > 0 and name != DEFAULT_PERSPECTIVE:
            self.savePerspective(name)
            self.updatePerspectiveMenu()

    def restorePerspective(self, name=DEFAULT_PERSPECTIVE):
        """Restore the layout and state of all central and dock widgets from the perspective with the given
        name. If no *name* is given, use the default perspective."""
        perspective = config.storage.gui.perspectives[name]
        for widget in self.getWidgets():
            if not widget.canClose():
                return
        for widget in self.getWidgets():
            self.closeWidget(widget, ask=False)
        # Restore central widgets
        for id, state in perspective['central']:
            widgetClass = widgets.getClass(id)
            # It may happen that widgetClass is None
            # (for example if it belongs to a widget from a plugin and this plugin has been removed
            # since the last application shutdown). Simply do not load this widget
            if widgetClass is not None:
                self.addCentralWidget(widgetClass, state)
            else:
                logging.info(__name__, "Could not load central widget '{}'".format(widgetClass.id))
        if perspective['centralTabIndex'] < self.centralWidget().count():
            self.centralWidget().setCurrentIndex(perspective['centralTabIndex'])

        # Restore dock widgets (create them with correct object names and use QMainWindow.restoreState)
        dockWidgets = []
        for id, objectName, area, state in perspective['dock']:
            widgetClass = widgets.getClass(id)
            if widgetClass is not None:  # As above it may happen that widgetClass is None.
                widget = self._createDockWidget(widgetClass, area, objectName, state)
                if widget is None:
                    continue
                widget.setParent(self)  # necessary for QMainWindow.restoreState
                dockWidgets.append(widget)
            else:
                logging.info(__name__, "Could not load dock widget {} named '{}'".format(id, objectName))

        self.hideTitleBarsAction.setChecked(perspective['hideTitleBars'])

        # Restore dock widget positions
        success = False
        if config.binary.gui.mainwindow_state is not None and name in config.binary.gui.mainwindow_state:
            success = self.restoreState(config.binary.gui.mainwindow_state[name])
        if not success:
            for dockWidget in dockWidgets:
                area = dockWidget.widget().widgetClass.preferredDockAreaFlag()
                super().addDockWidget(area, dockWidget)

        if self.isLayoutFrozen():
            # self.dockWidgets() does not work until event queue is reentered.
            QtCore.QTimer.singleShot(0, functools.partial(self.setLayoutFrozen, True, force=True))

    def savePerspective(self, name=DEFAULT_PERSPECTIVE):
        """Save the layout and state of all central and dock widgets. If no *name* is given, the default
        perspective will be overwritten."""
        # Store central widgets
        centralWidgetList = []
        for widget in self.centralWidgets():
            centralWidgetList.append((widget.widgetClass.id, widget.saveState()))

        dockedWidgetList = []
        for dock in self.dockWidgets():
            if dock.objectName() == '': # docks with empty object name have been deleted
                continue
            widget = dock.widget()
            dockedWidgetList.append((widget.widgetClass.id, dock.objectName(),
                                     widget.area, widget.saveState()))

        perspective = {'central': centralWidgetList,
                       'dock': dockedWidgetList,
                       'centralTabIndex': self.centralWidget().currentIndex(),
                       'hideTitleBars': self.hideTitleBarsAction.isChecked()
                       }

        config.storage.gui.perspectives[name] = perspective

        # Copy the bytearray to avoid memory access errors
        if config.binary.gui.mainwindow_state is None:
            config.binary.gui.mainwindow_state = {}
        config.binary.gui.mainwindow_state[name] = bytearray(self.saveState())

    def createDefaultWidgets(self):
        """Create the default set of central and dock widgets. Use this method if no widgets can be loaded
        from the storage file."""
        self.setLayoutFrozen(False)
        for id in 'playlist', 'editor':
            self.addCentralWidget(id)
        self.centralWidget().setCurrentIndex(0)
        for id in 'playback', 'browser', 'tageditor', 'filesystembrowser':
            self.addDockWidget(id)
    
    # Menus
    #=======================================================================================================         
    def initMenus(self):
        """Initialize menus except the view menu which cannot be initialized before all widgets have been
        loaded."""
        self.menus = {}

        # EDIT
        self.menus['edit'] = self.menuBar().addMenu(self.tr("&Edit"))
        self.menus['edit'].addAction(stack.createUndoAction())
        self.menus['edit'].addAction(stack.createRedoAction())

        action = QtWidgets.QAction(utils.getIcon('preferences/preferences_small.png'),
                               self.tr("Preferences..."),
                               self)
        
        action.triggered.connect(self.showPreferences)
        self.menus['edit'].addAction(action)

        # VIEW
        self.menus['view'] = self.menuBar().addMenu(self.tr("&View"))

        from maestro.widgets import browser
        self.menus['view'].addAction(browser.actions.GlobalSearchAction(self))
        self.menus['view'].addSeparator()

        self.menus['centralwidgets'] = self.menus['view'].addMenu(self.tr("New central widget"))
        self.menus['dockwidgets'] = self.menus['view'].addMenu(self.tr("New dock widget"))
        self.menus['perspectives'] = self.menus['view'].addMenu(self.tr("Perspective"))
        self.updatePerspectiveMenu()
        self.menus['view'].addSeparator()

        self.hideTitleBarsAction = QtWidgets.QAction(self.tr("Hide title bars"), self)
        self.hideTitleBarsAction.setCheckable(True)
        self.menus['view'].addAction(self.hideTitleBarsAction)

        self.freezeLayoutAction = QtWidgets.QAction(self.tr("Freeze layout"), self)
        self.freezeLayoutAction.setCheckable(True)
        self.freezeLayoutAction.setChecked(self.isLayoutFrozen())
        self.freezeLayoutAction.toggled.connect(self.setLayoutFrozen)
        self.menus['view'].addAction(self.freezeLayoutAction)

        fullscreenAction = actions.Action(self, 'fullScreen', self.tr("Toggle &fullscreen"))
        fullscreenAction.setCheckable(True)
        fullscreenAction.toggled.connect(lambda state: self.showFullScreen() if state else self.showNormal())
        self.menus['view'].addAction(fullscreenAction)

        # Playback
        from maestro.widgets import playback
        self.menus['playback'] = self.menuBar().addMenu(self.tr("Playback"))
        for command in playback.PlayCommand:
            self.menus['playback'].addAction(playback.PlayControlAction(self, command))

        # EXTRAS
        self.menus['extras'] = self.menuBar().addMenu(self.tr("&Extras"))

        # HELP
        self.menus['help'] = self.menuBar().addMenu(self.tr("&Help"))

        action = QtWidgets.QAction(self.tr("&About"), self)
        action.triggered.connect(self.showAboutDialog)
        self.menus['help'].addAction(action) 

    def updateWidgetMenus(self):
        """Update the central/dock widget menus whenever the list of registered widgets has changed."""
        def _updateMenu(widgetClasses, menu, method):
            menu.clear()
            for wClass in widgetClasses:
                action = QtWidgets.QAction(wClass.name, menu)
                action.triggered.connect(functools.partial(self._addWidget, widgetCls=wClass, method=method))
                if wClass.icon is not None:
                    action.setIcon(wClass.icon)
                if wClass.unique:
                    action.setObjectName(wClass.id)
                    if self.widgetExists(wClass.id):
                        action.setEnabled(False)
                menu.addAction(action)

        _updateMenu([wClass for wClass in widgets.widgetClasses if 'central' in wClass.areas],
                    self.menus['centralwidgets'],
                    self.addCentralWidget)
        _updateMenu([wClass for wClass in widgets.widgetClasses
                                    if wClass.allowedDockAreas() != Qt.NoDockWidgetArea],
                    self.menus['dockwidgets'],
                    self.addDockWidget)

    def _addWidget(self, widgetCls, method, **kwargs):
        method(widgetCls)

    def updatePerspectiveMenu(self):
        """Update the menu that lists available perspectives."""
        menu = self.menus['perspectives']
        menu.clear()

        for name, perspective in config.storage.gui.perspectives.items():
            if name == DEFAULT_PERSPECTIVE:
                continue
            action = QtWidgets.QAction(name, self)
            action.triggered.connect(functools.partial(self.restorePerspective, name))
            menu.addAction(action)
        if len(menu.actions()) > 0:
            menu.addSeparator()
        action = QtWidgets.QAction(self.tr("Save perspective..."), self)
        action.triggered.connect(self._handleSavePerspective)
        menu.addAction(action)

    def _setUniqueWidgetActionEnabled(self, id, enabled):
        """Enable/disable the menu actions for a unique widget type. *id* is the id of a registered
        WidgetClass-instance having the 'unique'-flag.
        """
        for menuId in 'centralwidgets', 'dockwidgets':
            action = self.menus[menuId].findChild(QtWidgets.QAction, id)
            if action is not None:
                action.setEnabled(enabled)
        
    def showPreferences(self):
        """Open preferences dialog."""
        from . import preferences
        preferences.show("main")

    def showAboutDialog(self):
        """Display the About dialog."""
        box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.NoIcon, self.tr("About Maestro"),
                '<div align="center"><img src=":maestro/omg.png" /><br />'
                + self.tr("This is Maestro version {} by Martin Altmayer and Michael Helmling.")
                             .format(VERSION)
                + '</div>',
                QtWidgets.QMessageBox.Ok)
        box.exec_()

    # Misc
    #========================================================================================================
    def isLayoutFrozen(self):
        """When the layout is frozen, it is impossible to resize the window or dockwidgets. Also, it is
        impossible to move or close dockwidgets."""
        return config.storage.gui.layoutFrozen

    def setLayoutFrozen(self, frozen, force=False):
        """Freeze/unfreeze layout. When the layout is frozen, it is impossible to resize the window or
        dockwidgets. Also, it is impossible to move or close dockwidgets."""
        frozen = bool(frozen)
        if force or frozen != config.storage.gui.layoutFrozen:
            config.storage.gui.layoutFrozen = frozen
            if frozen:
                self.setFixedSize(self.size())
            else: self.setFixedSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)
            self.centralWidget().closeButton.setVisible(not frozen)
            for widget in self.dockWidgets():
                widget.setFrozen(frozen)
                
    def _handleFocusChanged(self, old, new):
        """Handle the global QApplication.focusChanged signal to update current widgets."""
        while new is not self and new is not None and not isinstance(new, widgets.Widget):
            new = new.parent()
        if isinstance(new, widgets.Widget):
            self.currentWidgets[new.widgetClass.id] = new


class CentralTabWidget(QtWidgets.QTabWidget):
    """This tab widget is used as the main window's central widget. Via the 'View'-menu the user can choose
    which widgets should be inside the tabs."""
    def __init__(self):
        super().__init__()
        self.setMovable(True)
        self.setTabBar(CentralTabBar())
        self._lastDialogTabIndexes = {}
        self.currentChanged.connect(self._handleCurrentChanged)

        # Create corner widget
        from . import dockwidget
        cornerWidget = QtWidgets.QWidget()
        cornerLayout = QtWidgets.QHBoxLayout(cornerWidget)
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

    def _handleCurrentChanged(self):
        widget = self.currentWidget()
        self.optionButton.setEnabled(widget is not None and widget.hasOptionDialog)
        
    def _handleCloseButton(self):
        """React to the corner widget's close button: Close the current widget."""
        mainWindow.closeWidget(self.currentWidget())

    def _handleOptionButton(self):
        """React to the corner widget's option button: Open the option dialog of the current widget."""
        self.currentWidget().toggleOptionDialog(self.optionButton)


class CentralTabBar(QtWidgets.QTabBar):
    """This tabbar makes a tab active when a drag enters its tabbutton."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)  # without this line we won't get dragEnterEvents

    def dragEnterEvent(self, event):
        tabIndex = self.tabAt(event.pos())
        if tabIndex != -1 and tabIndex != self.currentIndex():
            self.setCurrentIndex(tabIndex)
        return super().dragEnterEvent(event)


fullscreenAction = actions.ActionDefinition('view', 'fullScreen',
                                            translate('MainWindow', 'Toggle full-screen mode'),
                                            shortcut=translate('QShortcut', 'F11'))
actions.manager.registerAction(fullscreenAction)
