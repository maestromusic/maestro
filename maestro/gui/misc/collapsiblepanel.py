# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2014-2015 Martin Altmayer, Michael Helmling
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


class CollapsiblePanel(QtGui.QWidget):
    """This panel takes a widget or layout and displays it below a title bar which contains the given title
    and a button that can be used to expand/collapse the widget or layout."""
    def __init__(self, title, widgetOrLayout, expanded=True, parent=None):
        super().__init__(parent)
        layout = QtGui.QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        topLayout = QtGui.QHBoxLayout()
        self.toggleButton = ToggleButton(self)
        topLayout.addWidget(self.toggleButton)
        self.titleLabel = QtGui.QLabel(title)
        self.titleLabel.setStyleSheet("QLabel { font-weight: bold }")
        topLayout.addWidget(self.titleLabel)
        topLayout.addStretch()
        layout.addLayout(topLayout)
        
        self.widget = QtGui.QWidget()
        self.widget.setContentsMargins(self.toggleButton.sizeHint().width(), 0, 0, 0)
        
        if isinstance(widgetOrLayout, QtGui.QWidget):
            self.widget.setLayout(QtGui.QHBoxLayout())
            self.widget.layout().addWidget(widgetOrLayout)
        else:
            widgetOrLayout.setContentsMargins(1,1,1,1)
            self.widget.setLayout(widgetOrLayout)
        layout.addWidget(self.widget)
        
        self.setExpanded(expanded)
        
    def title(self):
        """Return the title displayed in the title bar."""
        return self.titleLabel.text()
    
    def setTitle(self, title):
        """Set the title displayed in the title bar."""
        self.titleLabel.setText(title)
        
    def expanded(self):
        """Return whether the wrapped widget or layout is visible."""
        return self.toggleButton.down
    
    def setExpanded(self, expanded):
        """Set whether the wrapped widget or layout is visible."""
        self.toggleButton.down = expanded
        self.toggleButton.update()
        self.widget.setVisible(expanded)
        self.updateGeometry()
        
    def mousePressEvent(self, event):
        self.toggleButton.down = not self.toggleButton.down
        self.toggleButton.update()
        self.widget.setVisible(self.toggleButton.down)
        self.updateGeometry()
        

class ToggleButton(QtGui.QWidget):
    """Button used by CollapsiblePanel: Depending on the state it draws an arrow to the right or down."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.down = True
        
    def sizeHint(self):
        return QtCore.QSize(16, 16)
    
    def sizePolicy(self):
        return QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
    
    def paintEvent(self, paintEvent):
        super().paintEvent(paintEvent)
        painter = QtGui.QPainter(self)
        style = QtGui.QApplication.style()
        option = QtGui.QStyleOption()
        option.rect = self.rect()
        arrow = QtGui.QStyle.PE_IndicatorArrowDown if self.down else QtGui.QStyle.PE_IndicatorArrowRight
        style.drawPrimitive(arrow, option, painter)
