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

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from ... import utils


class IconLineEdit(QtWidgets.QLineEdit):
    """This is simply a line edit that displays an icon inside the lineedit at the right end. In fact the
    icon is a QToolButton that may be accessed via the attribute ''button''. The following will make the
    button clear the text::
    
        iconLineEdit.button.clicked.connect(iconLineEdit.clear)
    
    If the property ''hideIconWhenEmpty'' is set (default), the button will only be displayed, if the
    lineedit is not empty.
    """ 
    def __init__(self, icon, parent = None):
        QtWidgets.QLineEdit.__init__(self, parent)
        self.button = QtWidgets.QToolButton(self)
        self.button.setIcon(QtGui.QIcon(icon))
        self.button.setCursor(Qt.ArrowCursor)

        # Do not render a button
        self.button.setStyleSheet("QToolButton { padding: 0px; border: none; }")
        # This ensures that there is no text over or under the icon
        paddingRight = self.button.sizeHint().width() + 2
        self.setStyleSheet("QLineEdit { padding-right: "+str(paddingRight)+"px; }")
        
        # Keep at least the size of the icon
        min = self.minimumSizeHint()
        self.setMinimumSize(max(min.width(), self.button.sizeHint().height() + 2),
                            max(min.height(), self.button.sizeHint().height() + 2))
                            
        self.hideIconWhenEmpty = None
        self.setHideIconWhenEmpty(True)

    def getHideIconWhenEmpty(self):
        """Return whether the icon will be hidden when there is no text."""
        return self.hideIconWhenEmpty
        
    def setHideIconWhenEmpty(self,hide):
        """Set whether the icon will be hidden when there is no text."""
        if hide != self.hideIconWhenEmpty:
            self.hideIconWhenEmpty = hide
            if hide:
                self.button.setVisible(len(self.text()) > 0)
                self.textChanged.connect(self._updateIcon)
            else:
                self.button.setVisible(True)
                self.textChanged.disconnect(self._updateIcon)
    
    def _updateIcon(self,text):
        if self.hideIconWhenEmpty:
            self.button.setVisible(len(text) > 0)
        
    def resizeEvent(self,resizeEvent):
        sizeHint = self.button.sizeHint()
        self.button.move(self.rect().right() - sizeHint.width(), self.rect().bottom() - sizeHint.height())


class LineEditWithHint(QtWidgets.QLineEdit):
    """A lineedit with the additional feature that it draws a gray text in its right corner. The text is
    only visible if there is enough space."""
    def __init__(self,text='',parent=None):
        super().__init__(text,parent)
        self._rightText = None
        
    def rightText(self):
        """Return the text that is displayed in the right corner."""
        return self._rightText
    
    def setRightText(self,text):
        """Set the text that will be displayed in the right corner. *text* may be None."""
        if text != self._rightText:
            self._rightText = text
            self.update()
            
    def paintEvent(self,event):
        super().paintEvent(event)
        
        # Much of the code here is similarly used in QLineEdit::paintEvent to draw the placeHolderText
        # (which is uncool because it is not shown when the lineedit has focus...)
        
        spaceRight = 5
        spaceLeft = 10
        
        # Compute available rect
        option = QtWidgets.QStyleOptionFrame()
        self.initStyleOption(option)
        style = QtWidgets.QApplication.style()
        r = style.subElementRect(QtWidgets.QStyle.SE_LineEditContents,option,self)
        
        margins = self.getTextMargins()
        r.setX(r.x() + margins[0])
        r.setY(r.y() + margins[1])
        r.setRight(r.right() - margins[2] - spaceRight)
        r.setBottom(r.bottom() - margins[3])
        
        # Decide whether there is enough space to draw
        fm = self.fontMetrics()
        if fm.width(self.text()) + fm.width(self._rightText) + spaceLeft <= r.width(): 
            painter = QtGui.QPainter(self)
            oldPen = painter.pen()
            color = self.palette().text().color()
            color.setAlpha(128)
            painter.setPen(color)
            painter.drawText(r,Qt.AlignRight | Qt.AlignVCenter,self._rightText)
            painter.setPen(oldPen)
            
            
class PathLineEdit(QtWidgets.QWidget):
    """A line edit together with a small button that opens a file dialog. The user can select an existing
    directory which will then be inserted into the line edit.
    
    Arguments:
        - *dialogTitle*: title of the dialog,
        - *pathType*: Determines which paths are accepted. Possible values are 
                ['path', 'existingFile', 'existingDirectory']
        - *path*: start value,
        - *parent*: Qt parent object
    """
    textChanged = QtCore.pyqtSignal(str)
    
    def __init__(self, dialogTitle, pathType="path", path=None, parent=None):
        super().__init__(parent)
        self.dialogTitle = dialogTitle
        self.pathType = pathType
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        self.lineEdit = QtWidgets.QLineEdit()
        if path is not None:
            self.lineEdit.setText(path)
        self.lineEdit.textChanged.connect(self.textChanged)
        layout.addWidget(self.lineEdit, 1)
        button = QtWidgets.QPushButton()
        button.setIcon(utils.images.standardIcon('directory'))
        button.setIconSize(QtCore.QSize(16, 16))
        button.clicked.connect(self._handleButton)
        layout.addWidget(button)
        
    def _handleButton(self):
        """Handle the button next to the line edit: Open a file dialog."""
        if self.pathType == 'path':
            method = QtGui.QFileDialog.getSaveFileName
        elif self.pathType == 'existingFile':
            method = QtGui.QFileDialog.getOpenFileName
        else: method = QtGui.QFileDialog.getExistingDirectory
        result = method(self, self.dialogTitle, self.lineEdit.text())
        if result:
            self.lineEdit.setText(result)
            
    def text(self):
        """Return the current text."""
        return self.lineEdit.text()
    
    def setText(self, text):
        """Set the text of this line edit."""
        self.lineEdit.setText(text)
