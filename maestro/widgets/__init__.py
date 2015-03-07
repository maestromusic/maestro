# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2015 Martin Altmayer, Michael Helmling
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

from maestro import application, logging

widgetClasses = [] # registered WidgetClass-instances


def current(widgetClassId):
    """Return the "current" widget of a certain widget class."""
    return application.mainWindow.currentWidgets.get(widgetClassId)

    
def addClass(widgetClass=None, **kwargs):
    """Register a WidgetClass instance. Afterwards the user may add widgets of this class to the GUI.
    Arguments must be either a single WidgetClass-instance or keyword-arguments which will be passed to the
    constructor of WidgetClass. This method returns the class.
    """
    if widgetClass is None:
        widgetClass = WidgetClass(**kwargs)
    if widgetClass in widgetClasses:
        logging.warning(__name__, "Attempt to add widget class twice: {}".format(widgetClass))
    else: widgetClasses.append(widgetClass)
    if application.mainWindow is not None:
        application.mainWindow._widgetClassAdded(widgetClass)
    return widgetClass


def removeClass(id):
    """Remove a registered WidgetClass instance with the given id from the list of registered widget
    classes."""
    widgetClass = getWidgetClass(id)
    if widgetClass is None:
        logging.warning(__name__, "Attempt to remove nonexistent widget class: {}".format(id))
    else: widgetClasses.remove(widgetClass)
    if application.mainWindow is not None:
        application.mainWindow._widgetClassRemoved(widgetClass)


def getClass(id):
    """Get the registered WidgetClass with the given id (or None)."""
    for c in widgetClasses:
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



class Widget(QtWidgets.QWidget):
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
            application.mainWindow._setUniqueWidgetActionEnabled(self.widgetClass.id, False)
    
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
        #return QtWidgets.QMessageBox.question(self, "Close?", "Close {}".format(self.widgetClass.id),
        #                                QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No) == QtWidgets.QMessageBox.Yes
        
    def _handleDockLocationChanged(self, location):
        area = {Qt.LeftDockWidgetArea: 'left', Qt.RightDockWidgetArea: 'right',
                Qt.TopDockWidgetArea: 'top', Qt.BottomDockWidgetArea: 'bottom'}[location]
        if area != self.area:
            self.area = area
            self.areaChanged.emit(area) 
            
    def containingWidget(self):
        """Return the DockWidget or the central TabWidget containing this widget."""
        if self.area == 'central':
            return application.mainWindow.centralWidget()
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
                from maestro.gui import dialogs
                if isinstance(self._dialog, dialogs.FancyTabbedPopup):
                    self._dialog.tabWidget.setCurrentIndex(self._lastDialogTabIndex)
                self._dialog.show()
        else:
            self._dialog.close()
        
    def eventFilter(self, object, event):
        if event.type() == QtCore.QEvent.Close and self._dialog is not None:
            from maestro.gui import dialogs
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
