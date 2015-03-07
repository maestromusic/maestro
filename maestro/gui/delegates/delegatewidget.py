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

from maestro.models import rootedtreemodel
from maestro.core.nodes import Wrapper, TextNode

class DelegateWidget(QtWidgets.QWidget):
    """This widget displays a single node using the given delegate."""
    def __init__(self, delegate, parent=None):
        super().__init__(parent)
        self.delegate = delegate
        self.model = rootedtreemodel.RootedTreeModel()
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Minimum)
        self._node = None
        
    def setNode(self, node):
        """Set the node that is displayed. *node* must not be part of a model already!"""
        self._node = node
        if node is not None:
            self.model.getRoot().setContents([node])
        else: self.model.getRoot().setContents([])
        #self.updateGeometry()
        self.update()
        
    def setElement(self, element):
        """Shortcut: Display the given element (inside a Wrapper)."""
        self.setNode(Wrapper(element))
        
    def setText(self, text):
        """Shortcut: Display the given text in a TextNode."""
        self.setNode(TextNode(text))
    
    def minimumSizeHint(self):
        print(self.delegate.getFontMetrics().lineSpacing())
        return QtCore.QSize(20, 3*self.delegate.getFontMetrics().lineSpacing())
    
    def sizeHint(self):
        if self._node is not None:
            option = QtWidgets.QStyleOptionViewItem()
            if self.width() > 0: # this is sometimes false during startup
                option.rect = self.rect()
            index = self.model.getIndex(self._node)
            return self.delegate.sizeHint(option, index)
        else:
            return QtCore.QSize()
    
    def paintEvent(self, event):
        if self._node is not None:
            painter = QtGui.QPainter(self)
            option = QtWidgets.QStyleOptionViewItem()
            option.rect = self.rect()
            index = self.model.getIndex(self._node)
            self.delegate.paint(painter, option, index)
            