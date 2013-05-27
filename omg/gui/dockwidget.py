# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2013 Martin Altmayer, Michael Helmling
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

from . import mainwindow, dialogs
from .. import utils


class DockWidget(QtGui.QDockWidget):
    """QDockWidget subclass that uses our custom DockWidgetTitleBar and respects the 'Hide title bars'
    option.
    If *optionButton* is true, *parent* must have a method 'createOptionDialog' which is called, when the
    button is clicked. It receives a reference to the button as argument (use this to place popup dialogs).
    It must return either a FancyPopup dialog, which will be shown/hidden by the DockWidget, or None in
    which case *parent* must show/hide the dialog itself.
    """
    def __init__(self, parent=None, optionButton=False):
        super().__init__(parent)
        self.titleBarWidget = DockWidgetTitleBar(self, optionButton)
        self.setTitleBarWidget(self.titleBarWidget)
        mainwindow.mainWindow.hideTitleBarsAction.toggled.connect(self._handleHideAction)
        
    def setWindowTitle(self, title):
        super().setWindowTitle(title)
        self.titleBarWidget.label.setText(title)
        
    def _handleHideAction(self, checked):
        if checked:
            self.setTitleBarWidget(QtGui.QWidget())
        else: self.setTitleBarWidget(self.titleBarWidget)
            
            
class DockWidgetTitleBar(QtGui.QFrame):
    """Custom class for title bars of QDockWidgets. Compared with Qt's standard title bar, the 'float' button
    has been removed, but an 'options' button may be added."""
    
    # The option dialog if it is open, and the index of the tab that was active when the dialog was closed.
    _dialog = None
    _lastDialogTabIndex = 0
    
    def __init__(self, parent, optionButton=False):
        super().__init__(parent)
        
        layout = QtGui.QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 0, 0)
        layout.setSpacing(0)
        
        self.label = QtGui.QLabel(self.parent().windowTitle())
        layout.addWidget(self.label)
        layout.addStretch()
        layout.addSpacing(8)
        
        if optionButton:
            if self.style().objectName() == 'oxygen':
                optionButtonIcon = 'dockwidgetarrow_oxygen.png'
            #elif self.style().objectName() == 'gtk+':
            #TODO: add more styles
            else: optionButtonIcon = 'dockwidgetarrow_gtk.png'
            self.optionButton = DockWidgetTitleButton(utils.getIcon(optionButtonIcon))
            self.optionButton.clicked.connect(self._handleOptionButton)
            layout.addWidget(self.optionButton)
        
        self.closeButton = DockWidgetTitleButton(
                                        QtGui.qApp.style().standardIcon(QtGui.QStyle.SP_TitleBarCloseButton))
        self.closeButton.clicked.connect(self.parent().close)
        layout.addWidget(self.closeButton)
            
    def _handleOptionButton(self):
        """Open the option dialog."""
        if self._dialog is None:
            self._dialog = self.parent().createOptionDialog(self.optionButton)
            if self._dialog is not None:
                self._dialog.installEventFilter(self)
                if isinstance(self._dialog, dialogs.FancyTabbedPopup):
                    self._dialog.tabWidget.setCurrentIndex(self._lastDialogTabIndex)
                self._dialog.show()
    
    def _handleDialogClosed(self):
        """Close the option dialog."""
        # Note: This is called by the dialog and not by a signal (there is no 'closed' signal)
            
    def eventFilter(self, object, event):
        if event.type() == QtCore.QEvent.Close and self._dialog is not None:
            if isinstance(self._dialog, dialogs.FancyTabbedPopup):
                self._lastDialogTabIndex = self._dialog.tabWidget.currentIndex()
            self._dialog = None
        return False # do not filter the event out


class DockWidgetTitleButton(QtGui.QAbstractButton):
    """Python implementation of QDockWidgetTitleButton from the Qt source (gui/widgets/qdockwidget.cpp).
    Unfortunately that class is not part of the public API and hence this Python port is necessary to create
    custom buttons. Constructor and paintEvent have been slightly modified, the rest is the same.
    """ 
    def __init__(self, icon):
        super().__init__()
        self.setFocusPolicy(Qt.NoFocus)
        self.setIcon(icon)
        
    def minimumSizeHint(self):
        return self.sizeHint()

    def sizeHint(self):
        self.ensurePolished()
        size = 2*self.style().pixelMetric(QtGui.QStyle.PM_DockWidgetTitleBarButtonMargin, None, self)
        if not self.icon().isNull():
            iconSize = self.style().pixelMetric(QtGui.QStyle.PM_SmallIconSize, None, self)
            sz = self.icon().actualSize(QtCore.QSize(iconSize, iconSize))
            size += max(sz.width(), sz.height())
        return QtCore.QSize(size, size)

    def enterEvent(self, event):
        if self.isEnabled():
            self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.isEnabled():
            self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        opt = QtGui.QStyleOptionToolButton()
        opt.initFrom(self)
        opt.state |= QtGui.QStyle.State_AutoRaise;
        
        if self.style().styleHint(QtGui.QStyle.SH_DockWidget_ButtonsHaveFrame, None, self):
            if self.isEnabled() and self.underMouse() and not self.isChecked() and not self.isDown():
                opt.state |= QtGui.QStyle.State_Raised
            if self.isChecked():
                opt.state |= QtGui.QStyle.State_On
            if self.isDown():
                opt.state |= QtGui.QStyle.State_Sunken
            
            # QGtkStyle disables the frame (unless hovering). It does so by checking whether this widget
            # inherits QDockWidgetTitleButton, which is not part of the API.
            # Thus we have to anticipate this check here.
            if not self.style().inherits("QGtkStyle") or opt.state & QtGui.QStyle.State_MouseOver:
                if self.style().inherits("QGtkStyle"):
                    # This should be done in drawPrimitive, but for some reason it does not work.
                    opt.rect.adjust(2,2,-2,-2)
                self.style().drawPrimitive(QtGui.QStyle.PE_PanelButtonTool, opt, painter, self)
        
        opt.icon = self.icon()
        opt.subControls = QtGui.QStyle.SC_None
        opt.activeSubControls = QtGui.QStyle.SC_None
        opt.features = getattr(QtGui.QStyleOptionToolButton, 'None') # QStyleOptionToolButton::None
        opt.arrowType = Qt.NoArrow
        size = self.style().pixelMetric(QtGui.QStyle.PM_SmallIconSize, None, self)
        opt.iconSize = QtCore.QSize(size, size)
        self.style().drawComplexControl(QtGui.QStyle.CC_ToolButton, opt, painter, self)
