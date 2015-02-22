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
and docked widgets. This module manages a list of all available widget classes (confer WidgetClass).
Plugins may add their own widgets using addWidgetClass. From this list a View menu is created that allows the
user to add widgets. At the end of the application the state and position of each widget is saved
and at application start it will be restored again.

To work with this system central widgets or docked widgets must follow some rules:

    - A corresponding WidgetClass about them must be registered using addWidgetClass.
    - The widget must be a subclass of mainwindow.Widget.
    - Of course the generic system can only store the position and not the inner state of each widget. If a
    widget wants to store its state, it must reimplement the method saveState to return an object that
    will be passed to the constructor on the next startup.

"""

import functools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from maestro import config, logging, utils, stack, VERSION
from maestro.gui import actions, selection, dialogs


translate = QtCore.QCoreApplication.translate
QWIDGETSIZE_MAX = 16777215

# This will contain the single instance of MainWindow once it is initialized
mainWindow = None
""":type: MainWindow"""

# "Name" of the default perspective (will never be displayed)
DEFAULT_PERSPECTIVE = ''


# Widget Class Management
#============================================================================================================
_widgetClasses = [] # registered WidgetClass-instances

def addWidgetClass(widgetClass):
    """Register a WidgetClass instance. Afterwards the user may add widgets of this class to the GUI."""
    if widgetClass in _widgetClasses:
        logging.warning(__name__, "Attempt to add widget class twice: {}".format(widgetClass))
    else: _widgetClasses.append(widgetClass)
    if mainWindow is not None:
        mainWindow._widgetClassAdded(widgetClass)


def removeWidgetClass(id):
    """Remove a registered WidgetClass instance with the given id from the list of registered widget
    classes."""
    widgetClass = getWidgetClass(id)
    if widgetClass is None:
        logging.warning(__name__, "Attempt to remove nonexistent widget class: {}".format(id))
    else: _widgetClasses.remove(widgetClass)
    if mainWindow is not None:
        mainWindow._widgetClassRemoved(widgetClass)


def getWidgetClass(id):
    """Get the registered WidgetClass with the given id (or None)."""
    for c in _widgetClasses:
        if c.id == id:
            return c


class WidgetClass:
    """A WidgetClass instance stores information about one class of widgets (central and/or docked).
    It contains the following information:

        - id: a unique string to identify the WidgetClass. This string is used to store the widgets
          persistently.
        - name: a nice name which will be displayed in the View menu.
        - theClass: the class that must be instantiated to create a widget of this type.
        - areas: Specifies where a widget may be used. Must be a list or a comma-separated string
          containing some of the values
          ['top', 'bottom', 'left', 'right', 'central', 'dock', 'all']
          The last two are combinations of the first five. Defaults to ['all'].
        - preferredDockArea: The default dock area (Omit if this widget may only be used in the center).
        - unique: If set, there may be only one widget of this class.
        - icon: Optional. An icon which is displayed in tabs or docks for this widget.

    """
    #TODO make an enum for DockAreas
    _areaFlags = {
            'top': Qt.TopDockWidgetArea,
            'bottom': Qt.BottomDockWidgetArea,
            'left': Qt.LeftDockWidgetArea,
            'right': Qt.RightDockWidgetArea,
        }
    
    def __init__(self, id, name, theClass, areas=None, preferredDockArea=None, unique=False, icon=None):
        self.id = id
        self.name = name
        self.theClass = theClass
        if areas is None or len(areas) == 0:
            areas = ['all']
        elif isinstance(areas, str):
            areas = [s.strip() for s in areas.split(',')]
        self.areas = []
        # note that the following order determines the default preferredDockArea
        for area in ['bottom', 'left', 'right', 'top', 'central']:
            if area in areas or 'all' in areas or (area != 'central' and 'dock' in areas):
                self.areas.append(area)
        if len(self.areas) == 0:
            raise ValueError("No valid area identifier given: {}".format(areas))
        self.preferredDockArea = preferredDockArea
        if preferredDockArea is None and self.areas[0] != 'central':
            self.preferredDockArea = self.areas[0]
        self.unique = unique
        self.icon = icon
        
    def allowedDockAreas(self):
        """Return the allowed dock areas as Qt::DockWidgetAreas flags."""
        result = Qt.NoDockWidgetArea
        for area in self.areas:
            if area != 'central':
                result |= self._areaFlags[area]
        return result
    
    def preferredDockAreaFlag(self):
        """Return the preferred dock area as Qt::DockWidgetAreas flag."""
        return self._areaFlags.get(self.preferredDockArea, Qt.NoDockWidgetArea)

    def __eq__(self, other):
        return self.id == other.id

    def __ne__(self, other):
        return self.id != other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return "<WidgetClass({}, {}, {})>".format(self.id, self.name, self.theClass.__name__)



class Widget(QtGui.QWidget):
    """This is the superclass of all widgets that can be used as central and/or docked widgets.
    The constructor of subclasses must take one argument *state* which is either None or what was returned
    by saveState on the last shutdown. It may have additional arguments and must pass all remaining
    keyword-arguments to the superclass constructor.
    
    Widget has three public attributes:
        - widgetClass: The Widget class this widget belongs to.
        - hasOptionDialog: If this is set to True in a subclass dockwidgets and the central tab widget
          will offer a button to open a option dialog (subclasses must also implement createOptionDialog).
        - area: The current area of the widget. A string from
          ['top', 'bottom', 'left', 'right', 'central', 'dock', 'all']
    """
    areaChanged = QtCore.pyqtSignal(str) # emitted when the widget is moved from one dock area to another
        
    def __init__(self, widgetClass, area=None):
        super().__init__()
        self.widgetClass = widgetClass
        self.hasOptionDialog = False
        self.area = area
        self._dialog = None          # The option dialog if it is open,
        self._lastDialogTabIndex = 0 # and the index of the tab that was active when the dialog was closed.
        if self.widgetClass.unique:
            mainWindow._setUniqueWidgetActionEnabled(self.widgetClass.id, False)
    
    def initialize(self, state=None):
        """This method is called after the widget has been added to its dock widget or to the central 
        tab widget. Thus methods like getContainingWidget().setWindowTitle can be used here (but not
        in the constructor. Remember to call the base implementation!
        """
        if self.area != 'central':
            self.containingWidget().dockLocationChanged.connect(self._handleDockLocationChanged)
    
    def canClose(self):
        """Return whether this widget may be closed. Subclasses should reimplement this function to ask
        the user in case of unsaved data.
        Do NOT use this method for tidy-up tasks, even if it returns True. When the main window is closed
        other widgets might abort the closing. For such tasks use the closeEvent-method. Note that you must
        not ignore CloseEvents, because they are only sent after this method has returned True.
        """
        # Because MainWindow.closeEvent has to ask many different widgets whether they can close, before
        # starting to really close them, there must be two methods: one that only checks and one that really
        # closes (including tidy up tasks). We use canClose for the former and close/closeEvent for the
        # latter.
        return True
        # Debug code
        #return QtGui.QMessageBox.question(self, "Close?", "Close {}".format(self.widgetClass.id),
        #                                QtGui.QMessageBox.Yes|QtGui.QMessageBox.No) == QtGui.QMessageBox.Yes
        
    def _handleDockLocationChanged(self, location):
        area = {Qt.LeftDockWidgetArea: 'left', Qt.RightDockWidgetArea: 'right',
                Qt.TopDockWidgetArea: 'top', Qt.BottomDockWidgetArea: 'bottom'}[location]
        if area != self.area:
            self.area = area
            self.areaChanged.emit(area) 
            
    def containingWidget(self):
        """Return the DockWidget or the central TabWidget containing this widget."""
        if self.area == 'central':
            return mainWindow.centralWidget()
        else: return self.parent() # the QDockWidget
        
    def saveState(self):
        """Return something (usually a dict) that can be encoded as JSON and stores the state of this widget.
        The next time the application is started, it will be passed as argument 'state' to the constructor.
        """
        return None
    
    def createOptionDialog(self, button=None):
        """Subclasses can reimplement this to return a custom option dialog (such subclasses must
        additionally set the attribute 'hasOptionDialog' to True).
        If not None, *button* is the button that triggered the dialog and may be used to position the
        dialog.
        """
        raise NotImplementedError()
    
    def toggleOptionDialog(self, button=None):
        """Open/close the option dialog. Call self.createOptionDialog to create the dialog (must be
        implemented in all subclasses that use option dialogs). If the result is a FancyPopup, take care of
        it. If *button* is not None, it may be used to position the dialog.
        """
        if self._dialog is None:
            self._dialog = self.createOptionDialog(button)
            if self._dialog is not None:
                self._dialog.setWindowTitle(self.tr("{} Options").format(self.widgetClass.name))
                self._dialog.installEventFilter(self)
                if isinstance(self._dialog, dialogs.FancyTabbedPopup):
                    self._dialog.tabWidget.setCurrentIndex(self._lastDialogTabIndex)
                self._dialog.show()
        else:
            self._dialog.close()
        
    def eventFilter(self, object, event):
        if event.type() == QtCore.QEvent.Close and self._dialog is not None:
            if isinstance(self._dialog, dialogs.FancyTabbedPopup):
                self._lastDialogTabIndex = self._dialog.tabWidget.currentIndex()
            self._dialog = None
        return False # do not filter the event out
        
    def setWindowTitle(self, title):
        """Change the title of this widget, or rather of its containing widget (dock or central tabwidget).
        """
        if self.area == 'central':
            tabWidget = self.containingWidget()
            tabWidget.setTabText(tabWidget.indexOf(self), title)
        else:
            self.containingWidget().setWindowTitle(title)
        
    def setWindowIcon(self, icon):
        """Change the icon of this widget, or rather of its containing widget (dock or central tabwidget)."""
        if self.area == 'central':
            tabWidget = self.containingWidget()
            tabWidget.setTabIcon(tabWidget.indexOf(self), icon)
        else:
            self.containingWidget().setWindowIcon(icon)
        
        
class MainWindow(QtGui.QMainWindow):
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
        mainWindow = self

        self.currentWidgets = {}
        """:type: dict[str, Widget]"""

        # Resize and move the widget to the size and position it had when the program was closed
        if config.binary.gui.mainwindow_maximized:
            self.showMaximized()
        else:
            if config.binary.gui.mainwindow_geometry is not None:
                success = self.restoreGeometry(config.binary.gui.mainwindow_geometry)
            else: success = False
            if not success:  # Default geometry
                screen = QtGui.QDesktopWidget().availableGeometry()
                self.resize(min(1000, screen.width()), min(800, screen.height()))
                # Center the window
                screen = QtGui.QDesktopWidget().screenGeometry()
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
        
        QtGui.QApplication.instance().focusChanged.connect(self._handleFocusChanged)
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
            widgetClass = getWidgetClass(widgetClass)
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
            widgetClass = getWidgetClass(widgetClass)
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
        name, ok = QtGui.QInputDialog.getText(self, self.tr("Save perspective"),
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
            widgetClass = getWidgetClass(id)
            # It may happen that widgetClass is None
            # (for example if it belongs to a widget from a plugin and this plugin has been removed
            # since the last application shutdown). Simply do not load this widget
            if widgetClass is not None:
                widget = self.addCentralWidget(widgetClass, state)
            else: logging.info(__name__, "Could not load central widget '{}'".format(widgetClass.id))
        if perspective['centralTabIndex'] < self.centralWidget().count():
            self.centralWidget().setCurrentIndex(perspective['centralTabIndex'])

        # Restore dock widgets (create them with correct object names and use QMainWindow.restoreState)
        dockWidgets = []
        for id, objectName, area, state in perspective['dock']:
            widgetClass = getWidgetClass(id)
            if widgetClass is not None:  # As above it may happen that widgetClass is None.
                widget = self._createDockWidget(widgetClass, area, objectName, state)
                if widget is None:
                    continue
                widget.setParent(self) # necessary for QMainWindow.restoreState
                dockWidgets.append(widget)
            else: logging.info(__name__, "Could not load dock widget '{}' with object name '{}'"
                                         .format(widgetClass.id, objectName))

        self.hideTitleBarsAction.setChecked(perspective['hideTitleBars'])

        # Restore dock widget positions
        success = False
        if config.binary.gui.mainwindow_state is not None and name in config.binary.gui.mainwindow_state:
            success = self.restoreState(config.binary.gui.mainwindow_state[name])
        if not success:
            for widgets in dockWidgets:
                super().addDockWidget(widget.widgetClass.preferredDockAreaFlag, widget)

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

        action = QtGui.QAction(utils.getIcon('preferences/preferences_small.png'),
                               self.tr("Preferences..."),
                               self)
        
        action.triggered.connect(self.showPreferences)
        self.menus['edit'].addAction(action)

        # VIEW
        self.menus['view'] = self.menuBar().addMenu(self.tr("&View"))

        from maestro.gui import browseractions
        self.menus['view'].addAction(browseractions.GlobalSearchAction(self))
        self.menus['view'].addSeparator()

        self.menus['centralwidgets'] = self.menus['view'].addMenu(self.tr("New central widget"))
        self.menus['dockwidgets'] = self.menus['view'].addMenu(self.tr("New dock widget"))
        self.menus['perspectives'] = self.menus['view'].addMenu(self.tr("Perspective"))
        self.updatePerspectiveMenu()
        self.menus['view'].addSeparator()

        self.hideTitleBarsAction = QtGui.QAction(self.tr("Hide title bars"), self)
        self.hideTitleBarsAction.setCheckable(True)
        self.menus['view'].addAction(self.hideTitleBarsAction)

        self.freezeLayoutAction = QtGui.QAction(self.tr("Freeze layout"), self)
        self.freezeLayoutAction.setCheckable(True)
        self.freezeLayoutAction.setChecked(self.isLayoutFrozen())
        self.freezeLayoutAction.toggled.connect(self.setLayoutFrozen)
        self.menus['view'].addAction(self.freezeLayoutAction)

        fullscreenAction = actions.Action(self, 'fullScreen', self.tr("Toggle &fullscreen"))
        fullscreenAction.setCheckable(True)
        fullscreenAction.toggled.connect(lambda state: self.showFullScreen() if state else self.showNormal())
        self.menus['view'].addAction(fullscreenAction)

        # Playback
        from maestro.gui import playback
        self.menus['playback'] = self.menuBar().addMenu(self.tr("Playback"))
        self.menus['playback'].addAction(playback.PlayPauseAction(self))
        self.menus['playback'].addAction(playback.StopAction(self))
        self.menus['playback'].addAction(playback.SkipAction(self, forward=True))
        self.menus['playback'].addAction(playback.SkipAction(self, forward=False))
        self.menus['playback'].addAction(playback.AddMarkAction(self))

        # EXTRAS
        self.menus['extras'] = self.menuBar().addMenu(self.tr("&Extras"))

        # HELP
        self.menus['help'] = self.menuBar().addMenu(self.tr("&Help"))

        action = QtGui.QAction(self.tr("&About"), self)
        action.triggered.connect(self.showAboutDialog)
        self.menus['help'].addAction(action) 

    def updateWidgetMenus(self):
        """Update the central/dock widget menus whenever the list of registered widgets has changed."""
        def _updateMenu(widgetClasses, menu, method):
            menu.clear()
            for wClass in widgetClasses:
                action = QtGui.QAction(wClass.name, menu)
                # Choose the signal without "checked" argument because *method* may accept optional arguments.
                action.triggered[tuple()].connect(functools.partial(method, wClass))
                if wClass.icon is not None:
                    action.setIcon(wClass.icon)
                if wClass.unique:
                    action.setObjectName(wClass.id)
                    if self.widgetExists(wClass.id):
                        action.setEnabled(False)
                menu.addAction(action)

        _updateMenu([wClass for wClass in _widgetClasses if 'central' in wClass.areas],
                    self.menus['centralwidgets'],
                    self.addCentralWidget)
        _updateMenu([wClass for wClass in _widgetClasses if wClass.allowedDockAreas() != Qt.NoDockWidgetArea],
                    self.menus['dockwidgets'],
                    self.addDockWidget)

    def updatePerspectiveMenu(self):
        """Update the menu that lists available perspectives."""
        menu = self.menus['perspectives']
        menu.clear()

        for name, perspective in config.storage.gui.perspectives.items():
            if name == DEFAULT_PERSPECTIVE:
                continue
            action = QtGui.QAction(name, self)
            action.triggered.connect(functools.partial(self.restorePerspective, name))
            menu.addAction(action)
        if len(menu.actions()) > 0:
            menu.addSeparator()
        action = QtGui.QAction(self.tr("Save perspective..."), self)
        action.triggered.connect(self._handleSavePerspective)
        menu.addAction(action)

    def _setUniqueWidgetActionEnabled(self, id, enabled):
        """Enable/disable the menu actions for a unique widget type. *id* is the id of a registered
        WidgetClass-instance having the 'unique'-flag.
        """
        for menuId in 'centralwidgets', 'dockwidgets':
            action = self.menus[menuId].findChild(QtGui.QAction, id)
            if action is not None:
                action.setEnabled(enabled)
        
    def showPreferences(self):
        """Open preferences dialog."""
        from . import preferences
        preferences.show("main")

    def showAboutDialog(self):
        """Display the About dialog."""
        box = QtGui.QMessageBox(QtGui.QMessageBox.NoIcon, self.tr("About Maestro"),
                '<div align="center"><img src=":maestro/omg.png" /><br />'
                + self.tr("This is Maestro version {} by Martin Altmayer and Michael Helmling.")
                             .format(VERSION)
                + '</div>',
                QtGui.QMessageBox.Ok)
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
        while new is not self and new is not None and not isinstance(new, Widget):
            new = new.parent()
        if isinstance(new, Widget):
            self.currentWidgets[new.widgetClass.id] = new


class CentralTabWidget(QtGui.QTabWidget):
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

    def _handleCurrentChanged(self):
        widget = self.currentWidget()
        self.optionButton.setEnabled(widget is not None and widget.hasOptionDialog)
        
    def _handleCloseButton(self):
        """React to the corner widget's close button: Close the current widget."""
        mainWindow.closeWidget(self.currentWidget())

    def _handleOptionButton(self):
        """React to the corner widget's option button: Open the option dialog of the current widget."""
        self.currentWidget().toggleOptionDialog(self.optionButton)


class CentralTabBar(QtGui.QTabBar):
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