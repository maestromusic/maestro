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

import math, itertools

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

translate = QtCore.QCoreApplication.translate

__all__ = ['AbstractDelegate', 'MultiTextItem', 'TextItem', 'ImageItem', 'ColorBarItem',
           'IconBarItem', 'DelegateStyle']


class DelegateStyle:
    """A DelegateStyle is used to specify the style of texts in a TextItem or MultiTextItem. It stores the
    three attributes *relFontSize*, *bold* and *italic*. *relFontSize* is a factor which is multiplied with
    the delegate option ''fontSize''.
    """
    def __init__(self, relFontSize=1, bold=False, italic=False, color=None):
        self.bold = bold
        self.italic = italic
        self.relFontSize = relFontSize
        if color is None:
            color = QtWidgets.qApp.palette().color(QtGui.QPalette.WindowText)
        self.color = color

    @classmethod
    def standardStyle(cls):
        if not hasattr(cls, '_stdStyle'):
            cls._stdStyle = cls()
        return cls._stdStyle

    @classmethod
    def italicStyle(cls):
        if not hasattr(cls, '_italicStyle'):
            cls._italicStyle = cls(italic=True)
        return cls._italicStyle

    @classmethod
    def boldStyle(cls):
        if not hasattr(cls, '_boldStyle'):
            cls._boldStyle = cls(bold=True)
        return cls._boldStyle

            
class AbstractDelegate(QtWidgets.QStyledItemDelegate):
    """Abstract base class for delegates. This class implements sizeHint and paint by calling ''layout'',
    which must be implemented in subclasses. In that method subclasses must use ''addLeft'', ''addCenter''
    and ''addRight'' to fill the three areas with DelegateItems. This class will then layout the items and
    compute a sizehint or paint them. While the left and right area only contain a list of items, the center
    area contains rows which itself contain a list of items each of which may be aligned left or right.
    
    This is how DelegateItems are laid out: First all items in the left area will be drawn left aligned
    (like in a QHBoxLayout), then all items in the right area will be drawn right aligned. Afterwards
    each row in the center is drawn. In each row items will be drawn in the order they were added to the row
    until all items have been drawn or no space is available anymore.
    
    Assume we have two items in both the left and right area and two rows in the center area where the rows
    contain the following items:
    
        - first row: two items with left alignment and one with right alignment
        - second row: two items with right alignment and one with left alignment

    Then the layout will look like this:
    |----------------------------------------------------------------------------|
    | left 1 | left 2 | row1 l1 | row1 l2          | row1 r1 | right 2 | right 1 |
    |        |        |--------------------------------------|         |         |
    |        |        | row2 l1 |          row2 r2 | row2 r1 |         |         |
    |----------------------------------------------------------------------------|
    
    Additionally, subclasses may implement ''background'' to give some nodes a background.
    
    Constructor arguments:
        - *view*: The view that uses this delegate (used to compute available width and to update it on
          profile changes). Maybe None.
        - *profile*: A DelegateProfile.
        
    """
    hSpace = 3   # horizontal space between DelegateItems
    vSpace = 3   # vertical space between DelegateItems
    hMargin = 1  # horizontal margin at the left and right side of the content
    vMargin = 2  # vertical margin at the top and bottom of the content
            
    def __init__(self, view, profile):
        super().__init__(view)
        self.view = view
        self.model = view.model() if view is not None else None
        self.font = QtGui.QFont()
        assert profile is not None
        self.profile = profile
        profile.category.profileRemoved.connect(self._handleProfileRemoved)
        profile.category.profileChanged.connect(self._handleProfileChanged)
    
    def setProfile(self, profile):
        """Set the profile and redraw the whole view."""
        if profile is None:
            raise ValueError("Profile must not be None")
        self.profile = profile
        if self.view is not None:
            self.view.scheduleDelayedItemsLayout()
    
    def addLeft(self, item):
        """Add an item to the left region. It will be drawn on the right of all previous items
        in that region."""
        self.left.append(item)
        
    def addRight(self, item):
        """Add an item to the right region. It will be drawn on the left of all previous items
        in that region."""
        self.right.append(item)
        
    def newRow(self):
        """Start a new row in the center. Use addCenter to add items to it."""
        self.center.append([])
        
    def addCenter(self, item, align=Qt.AlignLeft):
        """Add an item to the current row in the center. Depending on the optional parameter *align*, which
        must be one of the module constants ''Qt.AlignLeft'' or ''Qt.AlignRight'', the item will be drawn on the right or on
        the left of the row (default is left). In both cases items added first will be drawn further on the
        sides and items added later will be more in the middle.
        
        Use newRow to start a new row.
        """
        if len(self.center) == 0:
            self.newRow()
        self.center[-1].append((item, align))

    def _handleProfileRemoved(self, profile):
        if profile == self.profile:
            self.setProfile(self.profileType.default())
            
    def _handleProfileChanged(self, profile):
        if profile == self.profile and self.view is not None:
            self.view.scheduleDelayedItemsLayout()
                    
    def layout(self, index, availableWidth):
        """Layout the node with the given index. This method is called by paint and sizeHint and must be
        implemented in subclasses."""
        raise NotImplementedError()

    def sizeHint(self, option, index):
        """Implementation of QtWidgets.QStyleItemDelegate.sizHint. This method is called by Qt. It will call
        self.layout (implemented in subclasses) to fill the lists ''left'', ''center'' and ''right'' and
        then compute the sizeHint based on the DelegateItems in those lists.
        """

        # Total width available.
        if self.view is not None:
            # Note that option.rect is useless due to a performance hack in Qt.
            # (Confer QTreeView::indexRowSizeHint in Qt's sources) 
            totalWidth = self.view.viewport().width() - 2 * self.hMargin
            totalWidth -= self.parent().indentation() * self.model.data(index).depth()
        else:
            totalWidth = option.rect.width() - 2 * self.hMargin
        
        # Collect items
        self.left, self.right, self.center = [], [], []
        self.layout(index, totalWidth)
                       
        leftWidth, leftMaxHeight = self._rowDimensions(self.left)
        rightWidth, rightMaxHeight = self._rowDimensions(self.right)
        
        # Add the space separating the parts
        if leftWidth > 0:
            leftWidth += self.hSpace
        if rightWidth > 0:
            rightWidth += self.hSpace
        
        # Calculate the center's size
        remainingWidth = totalWidth - leftWidth - rightWidth;

        centerHeight = 0
        centerMaxWidth = 0
        for row in self.center:
            if len(row) == 0:
                continue
            rowWidth, rowMaxHeight = self._rowDimensions((item for item,align in row),remainingWidth)
            centerHeight += rowMaxHeight + self.vSpace
            if rowWidth > centerMaxWidth: 
                centerMaxWidth = rowWidth
        if centerHeight > 0:
            centerHeight -= self.vSpace  # above loop adds one space too much
        
        return QtCore.QSize(leftWidth + centerMaxWidth + rightWidth + 2 * self.hMargin,
                            max(leftMaxHeight, centerHeight, rightMaxHeight) + 2 * self.vMargin)
    
    def background(self, index):
        """Defines the background brush for the given ModelIndex. If None is returned, the default
        background is used. Reimplement this in subclasses to use custom background colors."""
        return None
        
    def paint(self, painter, option, index):
        """Implementation of QtWidgets.QStyleItemDelegate.paint. This method is called by Qt. It will call
        self.layout (implemented in subclasses) to fill the lists ''left'', ''center'' and ''right'' and
        then paint the DelegateItems in those lists.
        """
        
        # Initialize. Subclasses or delegate items may access painter and option.
        self.painter = painter
        background = self.background(index)
        if background is not None:
            option.backgroundBrush = background
        # Draw the background depending on selection etc.
        QtWidgets.QApplication.style().drawControl(QtWidgets.QStyle.CE_ItemViewItem,option,painter)
        painter.save()
        painter.translate(option.rect.x(),option.rect.y())
        self.option = option
        
        # Collect items
        self.left,self.right,self.center = [],[],[]
        self.layout(index,option.rect.width() - 2*self.hMargin)
        
        leftOffset = self.hMargin
        rightOffset = self.hMargin
        availableHeight = option.rect.height() - 2*self.vMargin
        
        # Draw left and right regions
        for align,itemList in [(Qt.AlignLeft,self.left),(Qt.AlignRight,self.right)]:
            for item in itemList:
                availableWidth = option.rect.width() - leftOffset - rightOffset
                if availableWidth <= 0:
                    break
                rect = QtCore.QRect(leftOffset,self.vMargin,availableWidth,availableHeight)
                width,height = item.paint(self,rect,align)
                if align == Qt.AlignLeft:
                    leftOffset += width + self.hSpace
                else: rightOffset += width + self.hSpace
            
        # Draw center regions
        rowOffset = self.vMargin # vertical space above the current row
        for row in self.center:
            lOff,rOff = leftOffset,rightOffset
            maxHeight = 0
            for item,align in row:
                rowLength = option.rect.width() - lOff - rOff
                if rowLength <= 0:
                    break
                rect = QtCore.QRect(lOff, rowOffset, rowLength, option.rect.height() -rowOffset - self.vMargin)
                if align == Qt.AlignLeft:
                    width, height = item.paint(self, rect)
                    lOff += width + self.hSpace
                else:
                    width, height = item.paint(self, rect, align=Qt.AlignRight)
                    rOff += width + self.hSpace
                if height > maxHeight:
                    maxHeight = height
            if len(row) > 0:
                rowOffset += maxHeight + self.vSpace
        
        # Reset
        painter.restore()
        self.painter = None
        self.option = None
                    
    def _rowDimensions(self, items, availableWidth=None):
        """Helper function for sizeHint: Compute the size of *items* when they are laid out in a row and get
        a maximum of *availableWidth* horizontal space space."""      
        width = 0
        maxHeight = 0
        for item in items:
            w, h = item.sizeHint(self, availableWidth)
            width += w + self.hSpace
            if h > maxHeight:
                maxHeight = h
            if availableWidth is not None:
                availableWidth -= w + self.hSpace
                if availableWidth <= 0:
                    break
        
        if width > 0:
            width -= self.hSpace  # above loop adds one space too much
        return width, maxHeight
    
    def getFontMetrics(self, style=None):
        """Return a QFontMetrics-object for a font with the given style."""
        if style is None:
            style = DelegateStyle.standardStyle()
        self.font.setPointSize(style.relFontSize * self.profile.options["fontSize"])
        self.font.setBold(style.bold)
        self.font.setItalic(style.italic)
        return QtGui.QFontMetrics(self.font)
                
    def _configurePainter(self, style):
        """Configure the current painter to draw in the given style. This may only be used in the paint
        methods of DelegateItems."""
        if style is None:
            style = DelegateStyle.standardStyle()
        self.font.setPointSize(style.relFontSize * self.profile.options["fontSize"])
        self.font.setBold(style.bold)
        self.font.setItalic(style.italic)
        self.painter.setFont(self.font)
        self.painter.setPen(style.color)
        return QtGui.QFontMetrics(self.font)
 

class DelegateItem:
    """A DelegateItem encapsulates one ore more pieces of information (e.g. a text, a cover, a list of
    icons) that can be drawn by a delegate. Given a node in a itemview, subclasses of AbstractDelegate
    will create DelegateItems for the information to display and add them to the delegate's regions (similar
    to adding widgets to a layout). Then the delegate will draw those items or compute the sizeHint using the
    items' paint and sizeHint methods.
    """
    def sizeHint(self, delegate, availableWidth=None):
        """Compute the sizeHint of this item. *delegate* may be used to access variables like delegate.option
        or methods like delegate.getFontMetrics. When *availableWidth* is not None, the item should try to
        not use more horizontal space (if that is not possible it still may use more).
        """ 
        raise NotImplementedError()
    
    def paint(self, delegate, rect, align=Qt.AlignLeft):
        """Draw this item. *delegate* must be used to access variables like delegate.painter, delegate.option
        and methods like delegate._configurePainter. *rect* is the QRect into which the item should be
        painted (this differs from option.rect). *align* is one of Qt.AlignLeft or Qt.AlignRight and determines the
        alignment of the item in the available space.
        """
        raise NotImplementedError()
    

class TextItem(DelegateItem):
    """A TextItem displays a single text. Optionally you can set the DelegateStyle of the text and a
    minimum height of the text line."""
    def __init__(self, text, style=None, minHeight=0):
        self.text = text
        self.style = style
        self.minHeight = minHeight
        
    def sizeHint(self, delegate, availableWidth=-1):
        rect = QtCore.QRect(0, 0, availableWidth, 1)
        bRect = delegate.getFontMetrics(self.style).boundingRect(rect, Qt.TextSingleLine, self.text)
        return bRect.width(), max(bRect.height(), self.minHeight)

    def paint(self, delegate, rect, align=Qt.AlignLeft):
        delegate._configurePainter(self.style)
        flags = Qt.TextSingleLine
        if align == Qt.AlignRight:
            flags |= Qt.AlignRight
        else:
            flags |= Qt.AlignLeft
        # Enable elided text
        # text = delegate.painter.fontMetrics().elidedText(self.text,Qt.ElideRight,rect.width())
        bRect = delegate.painter.drawText(rect, flags, self.text)
        return bRect.width(), max(bRect.height(), self.minHeight)
    
    
class ImageItem(DelegateItem):
    """A ImageItem displays a single pixmap."""
    def __init__(self, pixmap):
        self.pixmap = pixmap

    def sizeHint(self, delegate, availableWidth=None):
        return self.pixmap.width(), self.pixmap.height()
        
    def paint(self, delegate, rect, align=Qt.AlignLeft):
        if align == Qt.AlignRight:
            imageLeft = rect.x() + rect.width() - self.pixmap.width()
        else:
            imageLeft = rect.x()
        delegate.painter.drawPixmap(imageLeft, rect.y(), self.pixmap.width(), self.pixmap.height(), self.pixmap)
        return self.pixmap.width(), self.pixmap.height()


class ColorBarItem(DelegateItem):
    """A ColorBarItem is simply a filled area. You must specify the *width* of the area, whereas the *height*
    may be None (the item will stretch over the available height). *background* may be everything that can
    be submitted to QPainter.fillRect, e.g. QColor, QBrush.
    """
    def __init__(self, background, width, height=None):
        self.background = background
        self.width = width
        self.height = height
        
    def sizeHint(self, delegate, availableWidth=None):
        return self.width, self.height if self.height is not None else 1
    
    def paint(self, delegate, rect, align=Qt.AlignLeft):
        if align == Qt.AlignRight:
            left = rect.x() + rect.width() - self.width
        else:
            left = rect.x()
        if self.height is None:
            height = rect.height()
        else:
            height = self.height
        delegate.painter.fillRect(QtCore.QRect(left, rect.y(), self.width, height),
                                  self.background)
        return self.width, height


class PlayTriangleItem(DelegateItem):
    """An item that displays a small triangle, indicating the currenty playing element in
    a playlist."""
    def __init__(self, color, width):
        self.color = color
        self.width = width
        
        poly = QtGui.QPolygonF()
        poly.append(QtCore.QPointF(0, 2))
        poly.append(QtCore.QPointF(9, 6))
        poly.append(QtCore.QPointF(0, 10))
        poly.append(QtCore.QPointF(0, 2))
        self.pp = QtGui.QPainterPath()
        self.pp.addPolygon(poly)
    
    def sizeHint(self, delegate, availableWidth=None):
        return self.width, self.width
    
    def paint(self, delegate, rect, align=Qt.AlignLeft):
        delegate.painter.fillPath(self.pp.translated(rect.x(), rect.y()), self.color)
        delegate.painter.drawPath(self.pp.translated(rect.x(), rect.y()))
        return self.width, self.width


class IconBarItem(DelegateItem):
    """An IconBarItem displays a list of icons in a grid. The size of the grid is specified by the parameters
    *rows* and *columns*, of which at least one must be None: The None-parameter will be set to the minimum
    that is necessary to display all icons given the not-None parameter. If both are None, the number of
    columns will be chosen depending on the availableSpace (but at least 1).
    
    This class will optimize its grid to look nicely: Let's say we have 7 icons and columns=6,rows=None.
    We need 2 rows to display all columns. But instead of putting 6 icons in the first row and only one in
    the second one, an IconBarItem will display 4 icons in the first row and 3 in the second one. Thus even
    if there are more icons than columns, you must not rely on all columns being used.
    
    Besides the constructor parameters there are three attributes:
    
        - *iconSize*: size of the icon (icons are assumed to be quadratic). Default is 16.
        - *hSpace*: horizontal space between icons
        - *vSpace*: vertical space between icons
        
    \ """
    iconSize = 16
    hSpace = 1
    vSpace = 1
    
    def __init__(self,icons,rows=None,columns=None):
        self.icons = icons
        self.rows = rows
        self.columns = columns
    
    def _computeRowsAndColumns(self,availableWidth):
        """Compute the grid to use given the number of icons and the attributes ''self.rows'' and
        ''self.columns''. If both are None, use *availableWidth* to compute the number of columns.
        If this is also None, use a single row.
        """
        if len(self.icons) == 0:
            return 0,0
        
        columns = self.columns
        rows = self.rows
        assert columns is None or rows is None
        assert columns != 0 and rows != 0 # Avoid division by zero
        
        if columns is None and rows is None:
            if availableWidth is not None:
                columns = max(1,self.maxColumnsIn(availableWidth)) # We'll need at least one column
            else: rows = 1 # If we do not have any information, put all into one row
        
        if columns is not None:
            rows = math.ceil(len(self.icons)/columns)
            # The second step leads to a better packed layout (e.g. len(self.icons)=7, columns=6).
            # Furthermore it avoids results that are too big.
            columns = math.ceil(len(self.icons)/rows)
        else: # rows not None
            columns = math.ceil(len(self.icons)/rows)
            rows = math.ceil(len(self.icons)/columns)
        
        return rows,columns
    
    def sizeHint(self,delegate,availableWidth=None):
        if len(self.icons) == 0:
            return 0,0
        rows,columns = self._computeRowsAndColumns(availableWidth)
        width = columns * self.iconSize + (columns-1) * self.hSpace
        height = rows * self.iconSize + (rows-1) * self.vSpace
        return width,height

    def paint(self,delegate,rect,align=Qt.AlignLeft):
        if len(self.icons) == 0:
            return 0,0
        
        rows,columns = self._computeRowsAndColumns(rect.width())
        
        if align == Qt.AlignRight:
            right = rect.right() + 1 # Confer documentation of rect.right 
        else: left = rect.x()
        
        top = rect.top()
        for i,icon in enumerate(self.icons):
            if i >= columns:
                top += self.iconSize + self.vSpace
                i = 0
            if align == Qt.AlignRight:
                rect = QtCore.QRect(right - (i+1)*self.iconSize - i*self.hSpace,top,
                                    self.iconSize,self.iconSize)
            else: rect = QtCore.QRect(left+i*(self.iconSize+self.hSpace),top,self.iconSize,self.iconSize)
            delegate.painter.drawPixmap(rect,icon.pixmap(self.iconSize,self.iconSize))
        
        return columns*self.iconSize + (columns-1)*self.hSpace, rows*self.iconSize + (rows-1)*self.vSpace
    
    def maxColumnsIn(self,width):
        """Return the maximum number of icon columns that fit into *width*."""
        # max{n: n*iconSize + (n-1)*hSpace <= width}
        if width <= 0:
            return 0
        return (width+self.hSpace) // (self.iconSize+self.hSpace)


SEP_1 = 10
SEP_2 = 40
LINESEP = 3

def getTextInfo(fm,text):
    max,length = 0,0
    for word in text.replace('-',' ').split():
        l = fm.width(word)
        length += l
        if l > max:
            max = l
    return length,max   


class MultiTextItem(DelegateItem):
    """A MultiTextItem stores two columns, each containing several rows of text. In contrast to a usual
    two-column layout, the width of the columns may differ in different rows. MultiTextItem will try to 
    compute the width cleverly, so that a minimal number of rows is needed in total.
    
    *leftTexts* and *rightTexts* are lists of the columns' texts. These lists may contain strings or
    QTextDocuments, allowing for e.g. multi-colored text. If you use QTextDocuments in *rightTexts* you
    should set the document's alignment to right.
    
    *style* is the DelegateStyle applied to all strings (not the QTextDocuments) in the list.
    
    Warning: MultiTextItems will take all available horizontal space. Thus you can usually use it only in
    the center region of an AbstractDelegate and must add it last to its row.
    """
    def __init__(self,leftTexts,rightTexts,style=None):
        if style is None:
            style = DelegateStyle.standardStyle()
        self.leftTexts = leftTexts
        self.rightTexts = rightTexts
        self.style = style
        
    def sizeHint(self,delegate,availableWidth=None):
        fm = delegate.getFontMetrics(self.style)
        return self._layout(delegate,fm,availableWidth,0,paint=False) # availableHeight is not needed
    
    def paint(self,delegate,rect,align=Qt.AlignLeft):
        delegate.painter.save()
        fm = delegate._configurePainter(self.style)
        delegate.painter.translate(rect.x(),rect.y())
        result = self._layout(delegate,fm,rect.width(),rect.height(),paint=True)
        delegate.painter.restore()
        return result

    def _layout(self,delegate,fm,availableWidth,availableHeight,paint):
        """Paint (if *paint* is True) or compute sizeHint given the *delegate*, fontMetrics *fm* and
        available space. The main task is to compute the distribution of space in each row based on the
        length of the texts in both columns.
        """
        #print("availableWidth{}: {}".format(" (paint)" if paint else '',availableWidth))
        leftFlags = Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap
        rightFlags = Qt.AlignRight | Qt.AlignTop | Qt.TextWordWrap
        
        baseHeight = 0
        for leftThing,rightThing in itertools.zip_longest(self.leftTexts,self.rightTexts,fillvalue=''):
            # Check for QTextDocuments
            if isinstance(leftThing,QtGui.QTextDocument):
                leftText = leftThing.toPlainText()
            else: leftText = leftThing
            if isinstance(rightThing,QtGui.QTextDocument):
                rightText = rightThing.toPlainText()
            else: rightText = rightThing
            
            # Compute length of the columns
            leftLength,leftMax = getTextInfo(fm,leftText)
            rightLength,rightMax = getTextInfo(fm,rightText)
            #print("Length: {} {}".format(leftLength,rightLength))
            #print("Max: {} {}".format(leftMax,rightMax))
            
            if leftLength == 0 and rightLength == 0: # Avoid division by zero
                continue # Nothing to display
            
            leftColumnLength = math.ceil(leftLength/(leftLength+rightLength) * (availableWidth - SEP_1))
                
            if leftMax + rightMax > availableWidth - SEP_1:
                #leftColumnLength = math.ceil(leftMax/(leftMax+rightMax) * (availableWidth - SEP_1))
                leftFlags |= Qt.TextWrapAnywhere
                rightFlags |= Qt.TextWrapAnywhere
            elif leftColumnLength < leftMax:
                leftColumnLength = leftMax
            elif leftColumnLength > availableWidth - SEP_1 - rightMax:
                leftColumnLength = availableWidth - SEP_1 - rightMax
            
                         
            rect = QtCore.QRect(0,baseHeight,leftColumnLength,availableHeight-baseHeight)
            #print("Paint in left rect{}: {}".format(" (paint)" if paint else '',rect))
            if isinstance(leftThing,QtGui.QTextDocument):
                leftBRect = self.processTextDocument(leftThing,rect,delegate.painter if paint else None)
            else:
                if paint:
                    leftBRect = delegate.painter.drawText(rect,leftFlags,leftText)
                else: leftBRect = fm.boundingRect(rect,leftFlags,leftText)
            #print("LeftBRect{}: {}".format(" (paint)" if paint else '',leftBRect))
            
            rightColumnStart = leftBRect.width() + SEP_1
            #print("leftColumnLength: {}  | rightColumnStart: {}".format(leftColumnLength,rightColumnStart))
            rect = QtCore.QRect(rightColumnStart,baseHeight,
                                availableWidth-rightColumnStart,availableHeight-baseHeight)
            if isinstance(rightThing,QtGui.QTextDocument):
                rightBRect = self.processTextDocument(rightThing,rect,delegate.painter if paint else None)
            else:
                if paint:
                    rightBRect = delegate.painter.drawText(rect,rightFlags,rightText)
                else: rightBRect = fm.boundingRect(rect,rightFlags,rightText)
            #print("RightBRect{}: {}".format(" (paint)" if paint else '',rightBRect))
            
            baseHeight += max(leftBRect.height(),rightBRect.height()) + LINESEP
        
        if baseHeight > 0:
            baseHeight -= LINESEP # above loop adds one space too much
        return availableWidth,baseHeight
    
    def processTextDocument(self,document,rect,painter):
        """Compute the size of the given QTextDocument when rendered in *rect* and paint it if *painter* is
        not None.
        """
        document.setTextWidth(rect.width())
        if painter is not None:
            painter.save()
            painter.translate(rect.topLeft())
            document.drawContents(painter,QtCore.QRectF(rect.translated(-rect.x(),-rect.y())))
            #painter.drawRect(rect.translated(-rect.x(),-rect.y()))
            painter.restore()
        size = document.size().toSize()
        return QtCore.QRect(rect.x(),rect.top(),size.width(),size.height())
        
        
#class RichTextItem(DelegateItem):
#    def __init__(self,document):
#        self.document = document
#        
#    def sizeHint(self,delegate,availableWidth=None):
#        assert availableWidth is not None
#        self.document.setTextWidth(availableWidth)
#        size = self.document.size().toSize()
#        return size.width(),size.height()
#    
#    def paint(self,delegate,rect,align=LEFT):
#        self.document.setTextWidth(rect.width())
#        self.document.drawContents(delegate.painter,QtCore.QRectF(rect))
#        size = self.document.size().toSize()
#        return size.width(),size.height()
