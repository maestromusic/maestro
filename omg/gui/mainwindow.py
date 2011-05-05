# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""
This module implements OMG's flexible widget system. It consists of mainwindow.MainWindow which the toplevel window of OMG and a flexible amount of central widgets (which are displayed as tabs in the center) and dock widgets. This module manages a list of all available widget types (confer WidgetData). Plugins may add their own widgets using addWidgetData. From this list a View menu is created that allows the user to show/hide central widgets and add new dock widgets. While there can be only at most one instance of each central widget, dock widgets can have many instances (unless the unique-flag in the corresponding WidgetData is set to True).
At the end of the application the state and position of each widget is saved and at application start it will be restored again.

To work with this system central widgets or dock widget must follow some rules:

    - Data about them must be registered using addWidgetData.
    - The widget must provide a constructor which takes a parent as first parameter and has default values for all other parameters.
    - Dock widgets must be subclasses of QDockWidget.
    - Of course the generic system can only store the position and not the inner state of each widget. If a widget wants to store its state, it must provide the methods saveState to return a state object to be saved and restoreState which will be called with that state object as parameter on the next application start. The state object may be anything that can be stored in a variable in config.storage (i.e. any combination of standard Python types including lists and dicts).

"""

import functools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg import config, constants, logging

# This will contain the single instance of MainWindow once it is initialized
mainWindow = None

logger = logging.getLogger("omg.gui.mainwindow")

# Data about the available widgets
_widgetData = []


def addWidgetData(data):
    """Add widget data to the list of registered widgets."""
    if data in _widgetData:
        logging.warning("Attempt to add central widget data twice: {}".format(data))
    else: _widgetData.append(data)
    if mainWindow is not None:
        mainWindow._widgetDataAdded(data)


def removeWidgetData(id):
    """Remove the WidgetData instance with the given id from the list of registered widgets."""
    data = WidgetData.fromId(id)
    if data is None:
        logging.warning("Attempt to remove nonexistent widget data: {}".format(id))
    else: _widgetData.remove(data)
    if mainWindow is not None:
        mainWindow._widgetDataRemoved(data)


class MainWindow(QtGui.QMainWindow):
    """The main window of OMG. It contains a QTabWidget as actual central widget (in Qt sense) so that using tabs several widgets can be displayed as central widgets (in OMG's sense)."""

    # Dict mapping WidgetData instances to corresponding central widgets. If a central widget has been created once it will always be contained in this dict even if it has been hidden (except that it will be removed if the widget data has been removed. This may happen if a plugin is removed at runtime).
    _centralWidgets = None

    # Dict mapping WidgetData instances to lists of corresponding dock widgets. As above this dict may contain hidden docks.
    _dockWidgets = None
    
    def __init__(self,parent=None):
        QtGui.QMainWindow.__init__(self, parent)
        self.setDockNestingEnabled(True)
        self.setWindowTitle(self.tr('OMG version {}').format(constants.VERSION))
        self.setCentralWidget(QtGui.QTabWidget())
        self.initMenus()
        self.statusBar()

        self.restoreLayout()

        self.updateViewMenu()
        
        global mainWindow
        mainWindow = self

    def initMenus(self):
        """Initialize menus except the view menu which cannot be initialized before all widgets have been loaded."""
        self.menus = {}
        self.menus['view'] = self.menuBar().addMenu(self.tr("&View"))
        self.menus['extras'] = self.menuBar().addMenu(self.tr("&Extras"))
        self.menus['help'] = self.menuBar().addMenu(self.tr("&Help"))
        
        aboutAction = QtGui.QAction(self)
        aboutAction.setText(self.tr("&About"))
        aboutAction.triggered.connect(self.showAboutDialog)
        self.menus['help'].addAction(aboutAction)

    def updateViewMenu(self):
        """Update the view menu whenever the list of registered widgets has changed."""
        self.menus['view'].clear()
        # First create checkable entries for all central widgets
        for data in _widgetData:
            if data.central:
                action = QtGui.QAction(data.name,self.menus['view'])
                if data.icon is not None:
                    action.setIcon(data.icon)
                action.setCheckable(True)
                # At the first time this is executed the main window itself is not visible, so use isVisibleTo
                action.setChecked(data in self._centralWidgets and self._centralWidgets[data].isVisibleTo(self))
                action.toggled.connect(functools.partial(self._toggleCentralWidget,data))
                self.menus['view'].addAction(action)

        # Then create a menu which contains an entry for each dock widget
        self.menus['view'].addSeparator()
        self.menus['dockwidgets'] = self.menus['view'].addMenu(self.tr("New dock widget"))

        for data in _widgetData:
            if not data.central:
                action = QtGui.QAction(data.name,self.menus['dockwidgets'])
                action.triggered.connect(functools.partial(self.addDockWidget,data))
                if data.unique:
                    # This is used to find and enable the action if the single instance is hidden (closed)
                    action.setObjectName(data.id)
                    if data in self._dockWidgets and self._dockWidgets[data][0].isVisibleTo(self):
                        action.setEnabled(False)
                        
                if data.icon is not None:
                    action.setIcon(data.icon)
                self.menus['dockwidgets'].addAction(action)
                
    def _toggleCentralWidget(self,data,checked):
        """Show or hide the central widget corresponding to *data* according to *checked*."""
        if checked:
            self.addCentralWidget(data)
        elif data in self._centralWidgets:
            widget = self._centralWidgets[data]
            index = self.centralWidget().indexOf(widget)
            if index >= 0:
                self.centralWidget().removeTab(index)
        
    def addCentralWidget(self,data):
        """Add a central widget corresponding to the given WidgetData. If a widget of this type existed and was hidden once, simply show it again. Otherwise create a new widget."""
        if data not in self._centralWidgets:
            widget = data.theClass(self)
            self._centralWidgets[data] = widget
        else:
            widget = self._centralWidgets[data]
            index = self.centralWidget().indexOf(widget)
            if index >= 0:
                logger.error("Attempt to add central widget '{}' twice.".format(data))
                return
        if data.icon is not None:
            self.centralWidget().addTab(widget,data.icon,data.name)
        else: self.centralWidget().addTab(widget,data.name)
        return widget

    def addDockWidget(self,data,objectName=None):
        """Add a dock widget corresponding to the given WidgetData. If there is a hidden dock widget of this type, simply show it again. Otherwise create a new widget."""
        if data in self._dockWidgets:
            # First try to simply unhide an existing dock of this type
            for widget in self._dockWidgets[data]:
                if not widget.isVisibleTo(self):
                    widget.setVisible(True)
                    if data.unique:
                        self._setUniqueDockActionEnabled(data.id,False)
                    return # This was easy
        # If that did not work, create a new widget
        self._createDockWidget(data)

    def _createDockWidget(self,data,objectName=None):
        """Create a new dock widget for the given WidgetData and set its objectName to *objectName*. If that is None, compute an unused objectName."""
        if data not in self._dockWidgets:
            self._dockWidgets[data] = []
            
        # For the unique object name required by restoreState compute the first string of the form data.id+<int> that is not already in use. Unique dock widgets get simply their data.id as object name. This is also used by the event filter to find and enable the corresponding action in the view menu if the dock is closed.
        if objectName is None:
            if data.unique:
                objectName = data.id
            else:
                i = 1
                while data.id+str(i) in [widget.objectName() for widget in self._dockWidgets[data]]:
                    i += 1
                objectName = data.id + str(i)
        
        widget = data.theClass(self)
        widget.setObjectName(objectName)
        self._dockWidgets[data].append(widget)
        QtGui.QMainWindow.addDockWidget(self,data.preferredDockArea,widget)

        if data.unique:
            self._setUniqueDockActionEnabled(data.id,False)
            # This is used to enable the corresponding action again if the single instance is hidden (closed)
            widget.installEventFilter(self)

        return widget
        
    def restoreLayout(self):
        """Restore the geometry and state of the main window and the central widgets and dock widgets on application start."""
        # Resize and move the widget to the size and position it had when the program was closed
        if "mainwindow_geometry" in config.binary and isinstance(config.binary["mainwindow_geometry"],bytearray):
            success = self.restoreGeometry(config.binary["mainwindow_geometry"])
        else: success = False
        if not success: # Default geometry
            self.resize(800,600)
            # Center the window
            screen = QtGui.QDesktopWidget().screenGeometry()
            size = self.geometry()
            self.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)
        
        # Restore central widgets
        self._centralWidgets = {}
        for id,options in config.storage.gui.central_widgets:
            data = WidgetData.fromId(id)
            # It may happen that data is None (for example if it belongs to a widget from a plugin and this plugin has been removed since the last application shutdown). Simply do not load this widget
            if data is not None:
                widget = self.addCentralWidget(data)
                if hasattr(widget,"restoreState"):
                    widget.restoreState(options)
            else: logger.info("Could not load central widget '{}'".format(data))
        
        # Restore dock widgets (create them with correct object names and use QMainWindow.restoreState)
        self._dockWidgets = {}
        for id,objectName,options in config.storage.gui.dock_widgets:
            data = WidgetData.fromId(id)
            if data is not None: # As above it may happen that data is None.
                widget = self._createDockWidget(data,objectName)
                if hasattr(widget,"restoreState"):
                    widget.restoreState(options)
            else: logger.info("Could not load dock widget '{}' with object name '{}'".format(data,objectName))

        # Restore state
        if "mainwindow_state" in config.binary and isinstance(config.binary["mainwindow_state"],bytearray):
            success = self.restoreState(config.binary["mainwindow_state"])
        else: success = False
        if not success:
            for data,widgets in self._dockWidgets.items():
                for widget in widgets:
                    QtGui.QMainWindow.addDockWidget(self,data.preferredDockArea,widget)
            
    def saveLayout(self):
        """Save the geometry and state of the main window and the central widgets and dock widgets which are not hidden at application end."""
        # Store central widgets that are visible
        centralWidgetList = []
        for data,widget in self._centralWidgets.items():
            if widget.isVisibleTo(self):
                if hasattr(widget,"saveState"):
                    state = widget.saveState()
                else: state = None
                centralWidgetList.append((data.id,state))
        config.storage.gui.central_widgets = centralWidgetList

        # Store dock widgets that are visible and remove the rest so saveState won't store their position
        dockWidgetList = []
        for data,widgets in self._dockWidgets.items():
            for widget in widgets:
                if widget.isVisibleTo(self):
                    if hasattr(widget,"saveState"):
                        state = widget.saveState()
                    else: state = None
                    dockWidgetList.append((data.id,widget.objectName(),state))
                else:
                    # TODO: The idea of this is that the state of dock widgets that have been closed should not be stored. But it does not work (even using the commented lines) which in my opinion is a bug in Qt.
                    # If you open four dock widgets of a certain type (say logodock), the binary config file will forever contain information about logodock1 up to logodock4.
                    self.removeDockWidget(widget)
                    #widget.setObjectName(None)
                    widget.setParent(None)
                    del widget
        config.storage.gui.dock_widgets = dockWidgetList
        
        # Copy the bytearrays to avoid memory access errors
        config.binary["mainwindow_geometry"] = bytearray(self.saveGeometry())
        config.binary["mainwindow_state"] = bytearray(self.saveState())

    def showAboutDialog(self):
        """Display the About dialog."""
        box = QtGui.QMessageBox(QtGui.QMessageBox.NoIcon,self.tr("About OMG"),
                '<div align="center"><img src="images/omg.png" /><br />'
                + self.tr("This is OMG version {} by Martin Altmayer and Michael Helmling.").format(constants.VERSION)
                + '</div>',
                QtGui.QMessageBox.Ok)
        box.exec_()

    def _widgetDataAdded(self,data):
        """This is called when new widget data has been added."""
        self.updateViewMenu()

    def _widgetDataRemoved(self,data):
        """This is called when widget data has been removed."""
        if data.central:
            if data in self._centralWidgets:
                self._centralWidgets[data].setParent(None)
                del self._centralWidgets[data]
        else:
            if data in self._dockWidgets:
                for widget in self._dockWidgets[data]:
                    widget.setParent(None)
                del self._dockWidgets[data]
        self.updateViewMenu()

    def _setUniqueDockActionEnabled(self,id,enabled):
        if 'dockwidgets' in self.menus:
            action = self.menus['dockwidgets'].findChild(QtGui.QAction,id)
            if action is not None:
                action.setEnabled(enabled)
                
    def eventFilter(self,object,event):
        if isinstance(object,QtGui.QDockWidget) and event.type() == QtCore.QEvent.Close:
            # If a unique dock widget has been closed, enable the corresponding action in the view menu.
            # The event filter is only installed on unique docks.
            self._setUniqueDockActionEnabled(object.objectName(),True)
        return False # don't stop the event


class WidgetData:
    """A WidgetData instance stores information about one type of widget (central or dock). It contains the following information:

        - id: a unique string to identify the WidgetData. This string is used to store the widgets persistently.
        - name: a nice name which will be displayed in the View menu.
        - theClass: the class that must be instantiated to create a widget of this type. Remember that this must be a subclass of QDockWidget if central is False.
        - central: Whether this is a central widget.
        - default: Whether this widget should be displayed if no information from the last application run is present (e.g. at the very first launch).
        - unique: Only relevant for dock widgets. It stores whether there may be more than one instance of this widget.
        - preferredDockArea: Only relevant for dock widgets. Contains the dock area where this widget will be placed when it is newly created. One of the values of Qt.DockWidgetAreas.
        - icon: Optional. An icon which is displayed in tabs or docks for this widget.

    """
    def __init__(self,id,name,theClass,central,default,unique=False,preferredDockArea=None,icon=None):
        self.id = id
        self.name = name
        self.theClass = theClass
        self.central = central
        self.default = default
        self.unique = unique
        self.preferredDockArea = preferredDockArea
        self.icon = icon

    def __eq__(self,other):
        return self.id == other.id

    def __ne__(self,other):
        return self.id != other.id

    def __hash__(self):
        return hash(self.id)
        
    def __str__(self):
        return "<WidgetData({},{},{})>".format(self.id,self.name,self.theClass.__name__)

    @staticmethod
    def fromId(id):
        """Get the registered WidgetData with the given id. Return None if such data cannot be found."""
        for data in _widgetData:
            if data.id == id:
                return data
        else: return None