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

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt


class IconLineEdit(QtGui.QLineEdit):
    """This is simply a line edit that displays an icon inside the lineedit at the right end. In fact the
    icon is a QToolButton that may be accessed via the attribute ''button''. The following will make the
    button clear the text::
    
        iconLineEdit.button.clicked.connect(iconLineEdit.clear)
    
    If the property ''hideIconWhenEmpty'' is set (default), the button will only be displayed, if the
    lineedit is not empty.
    """ 
    def __init__(self, icon, parent = None):
        QtGui.QLineEdit.__init__(self, parent)
        self.button = QtGui.QToolButton(self)
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


class LineEditWithHint(QtGui.QLineEdit):
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
        option = QtGui.QStyleOptionFrameV2()
        self.initStyleOption(option)
        style = QtGui.QApplication.style()
        r = style.subElementRect(QtGui.QStyle.SE_LineEditContents,option,self)
        
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
            