# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2013-2014 Martin Altmayer, Michael Helmling
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

import functools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import mainwindow, dialogs
from .. import utils
        

class DockWidget(QtGui.QDockWidget):
    """QDockWidget subclass that uses our custom DockWidgetTitleBar and respects the 'Hide title bars'
    option. DockWidgets are created automatically by MainWindow when a mainwindow.Widget is added to a
    dock area.
    
    *widget* is the mainwindow.Widget-instance for the dock. *title* and *icon* are used for the
    dockwidget's title bar. 
    """    
    def __init__(self, widget, title='', icon=None):
        super().__init__()
        self.setFeatures(QtGui.QDockWidget.DockWidgetClosable | QtGui.QDockWidget.DockWidgetMovable)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.tbWidget = DockWidgetTitleBar(self)
        self.setWindowTitle(title)
        self.setWindowIcon(icon)
        self.setWidget(widget)
        self.tbWidget.setWidget(widget)
        self._handleHideTitleBarAction(mainwindow.mainWindow.hideTitleBarsAction.isChecked())
        mainwindow.mainWindow.hideTitleBarsAction.toggled.connect(self._handleHideTitleBarAction)
        
    def close(self):
        return self.widget().close() and super().close() # make sure self.widget().close is called
        
    def setWindowTitle(self, title):
        """Set the title displayed in the title bar of this dock widget."""
        super().setWindowTitle(title)
        if self.tbWidget is not None:
            self.tbWidget.titleLabel.setText(title)
        
    def setWindowIcon(self, icon):
        """Set the icon displayed in the title bar of this dock widget. If *icon* is None, the icon will be
        hidden."""
        if self.tbWidget is None:
            return
        if icon is not None:
            self.tbWidget.iconLabel.setPixmap(icon.pixmap(16, 16))
            self.tbWidget.iconLabel.show()
        else:
            self.tbWidget.iconLabel.setPixmap(QtGui.QPixmap())
            self.tbWidget.iconLabel.hide()
            
    def _handleHideTitleBarAction(self, checked):
        """Set whether the title bar is visible."""
        if checked:
            self.setTitleBarWidget(QtGui.QWidget())
            self.tbWidget.hide()
        else:
            self.setTitleBarWidget(self.tbWidget)
            self.tbWidget.show()
    
    def setFrozen(self, frozen):
        """Freeze/unfreeze dockwidget. Frozen dockwidgets cannot be resized, moved or closed."""
        if frozen:
            self.setFixedSize(self.size())
            self.setFeatures(QtGui.QDockWidget.NoDockWidgetFeatures)
        else:
            self.setFixedSize(mainwindow.QWIDGETSIZE_MAX, mainwindow.QWIDGETSIZE_MAX)
            self.setFeatures(QtGui.QDockWidget.DockWidgetClosable | QtGui.QDockWidget.DockWidgetMovable)
        self.tbWidget.closeButton.setVisible(not frozen)


class DockWidgetTitleBar(QtGui.QFrame):
    """Custom class for title bars of DockWidgets. Compared with Qt's standard title bar, the 'float' button
    has been removed, but an 'options' button may be added."""
    def __init__(self, parent):
        super().__init__(parent)
        
        layout = QtGui.QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 0, 0)
        layout.setSpacing(0)
        
        self.iconLabel = QtGui.QLabel()
        layout.addWidget(self.iconLabel)
        layout.addSpacing(3)
        self.titleLabel = QtGui.QLabel()
        self.titleLabel.setStyleSheet('QLabel { font-weight: bold }')
        layout.addWidget(self.titleLabel)
        layout.addStretch()
        layout.addSpacing(8)
        
        self.optionButton = DockWidgetTitleButton('options')
        self.optionButton.setEnabled(False)
        layout.addWidget(self.optionButton)
        self.closeButton = DockWidgetTitleButton('close')
        self.closeButton.clicked.connect(self._handleCloseButton)
        layout.addWidget(self.closeButton)
    
    def _handleCloseButton(self):
        mainwindow.mainWindow.closeWidget(self.parent().widget())
        
    def setWidget(self, widget):
        """Give the title bar a reference to its dock's inner widget.""" 
        if widget.hasOptionDialog:
            self.optionButton.clicked.connect(functools.partial(widget.toggleOptionDialog,
                                                                self.optionButton))
            self.optionButton.setEnabled(True)


class DockWidgetTitleButton(QtGui.QAbstractButton):
    """Python implementation of QDockWidgetTitleButton from the Qt source (gui/widgets/qdockwidget.cpp).
    Unfortunately that class is not part of the public API and hence this Python port is necessary to create
    custom buttons. Constructor and paintEvent have been slightly modified, the rest is the same.
    
    *icon* may be either a QIcon or one of the following special strings, which stand for style-dependent
    icons:
        - 'close': The close button used in dockwidgets' title bars.
        - 'options': The option button used in dockwidgets' title bars.
    """ 
    def __init__(self, icon):
        super().__init__()
        self.setFocusPolicy(Qt.NoFocus)
        if isinstance(icon, str):
            if icon == 'close':
                icon = QtGui.qApp.style().standardIcon(QtGui.QStyle.SP_TitleBarCloseButton)
            elif icon == 'options':
                if self.style().objectName() == 'oxygen':
                    icon = utils.getIcon('dockwidgetarrow_oxygen.png')
                #elif self.style().objectName() == 'gtk+':
                #TODO: add more styles
                else: icon = utils.getIcon('dockwidgetarrow_gtk.png')
            else:
                raise ValueError("*icon* must be either a QIcon or one of ['close', 'options'].")
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
