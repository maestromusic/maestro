# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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

import math,itertools

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from omg import models, tags, config
from omg.models import browser
from omg.gui import formatter


# Constants for delegate.state
SIZE_HINT, PAINT = 1,2

# Constants to specify alignment
LEFT,RIGHT = 1,2


class DelegateStyle:
    """A DelegateStyle is used to specify the style of texts in a TextItem or MultiTextItem. It stores the
    three attributes *fontSize*, *bold* and *italic*. Note that *fontSize* stores the pointsize of the font.
    """
    def __init__(self,fontSize,bold,italic):
        self.fontSize = fontSize
        self.bold = bold
        self.italic = italic


# Some standard styles used in the delegates
STD_STYLE = DelegateStyle(8,False,False)
ITALIC_STYLE = DelegateStyle(STD_STYLE.fontSize,False,True)
BOLD_STYLE = DelegateStyle(STD_STYLE.fontSize,True,False)
        

class AbstractDelegate(QtGui.QStyledItemDelegate):
    hSpace = 3
    vSpace = 3
    hMargin = 1
    vMargin = 2
    state = None
    
    def __init__(self,view):
        super().__init__(view)
        self.model = view.model()
        self.font = QtGui.QFont()
    
    def addLeft(self,item):
        """Add an item to the left region. It will be drawn on the right of all previous items
        in that region."""
        self.left.append(item)
        
    def addRight(self,item):
        """Add an item to the right region. It will be drawn on the left of all previous items
        in that region."""
        self.right.append(item)
        
    def newRow(self):
        """Start a new row in the center. Use addCenter to add items to it."""
        self.center.append([])
        
    def addCenter(self,item,align=LEFT):
        """Add an item to the current row in the center. Depending on the optional parameter *align*, which
        must be one of the module constants ''LEFT'' or ''RIGHT'', the item will be drawn on the right or on
        the left of the row (default is left). In both cases items added first will be drawn further on the
        sides and items added later will be more in the middle.
        
        Use newRow to start a new row.
        """
        if len(self.center) == 0:
            self.newRow()
        self.center[-1].append((item,align))
    
    def layout(self,index):
        """Layout the node with the given index. This method is called by paint and sizeHint and must be
        implemented in subclasses."""
        raise NotImplementedError()
    
    def paint(self,painter,option,index):
        """Implementation of QtGui.QStyleItemDelegate.paint. This method is called by Qt. It will call
        self.layout (implemented in subclasses) to fill the lists ''left'', ''center'' and ''right'' and
        then paint the DelegateItems in those lists.
        """
        if self.state is not None:
            import sys
            sys.exit("Fatal error: AbstractDelegate.paint was called during painting/sizehinting.")
        self.state = PAINT
        
        # Initialize. Subclasses or Delegate items may access painter and option.
        self.painter = painter
        # Draw the background depending on selection etc.
        QtGui.QApplication.style().drawControl(QtGui.QStyle.CE_ItemViewItem,option,painter)
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
        for align,itemList in [(LEFT,self.left),(RIGHT,self.right)]:
            for item in itemList:
                availableWidth = option.rect.width() - leftOffset - rightOffset
                if availableWidth <= 0:
                    break
                rect = QtCore.QRect(leftOffset,self.vMargin,availableWidth,availableHeight)
                width,height = item.paint(self,rect,align)
                if align == LEFT:
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
                rect = QtCore.QRect(lOff,rowOffset,rowLength,option.rect.height()-rowOffset-self.vMargin)
                if align == LEFT:
                    width,height = item.paint(self,rect)
                    lOff += width + self.hSpace
                else:
                    width,height = item.paint(self,rect,align=RIGHT)
                    rOff += width + self.hSpace
                if height > maxHeight:
                    maxHeight = height
            if len(row) > 0:
                rowOffset += maxHeight + self.vSpace
        
        # Reset
        painter.restore()
        self.painter = None
        self.option = None
        self.state = None

    def sizeHint(self,option,index):
        """Implementation of QtGui.QStyleItemDelegate.sizHint. This method is called by Qt. It will call
        self.layout (implemented in subclasses) to fill the lists ''left'', ''center'' and ''right'' and
        then compute the sizeHint based on the DelegateItems in those lists.
        """
        if self.state is not None:
            import sys
            sys.exit("Fatal error: AbstractDelegate.sizeHint was called during painting/sizehinting.")
        self.state = SIZE_HINT

        # Total width available. Note that option.rect is useless due to a performance hack in Qt.
        # (Confer QTreeView::indexRowSizeHint in Qt's sources) 
        totalWidth = self.parent().viewport().width() - 2*self.hMargin
        totalWidth -= self.parent().indentation() * self.model.data(index).getDepth()
        
        # Collect items
        self.left,self.right,self.center = [],[],[]
        self.layout(index,totalWidth)
                       
        leftWidth,leftMaxHeight = self._rowDimensions(self.left)
        rightWidth,rightMaxHeight = self._rowDimensions(self.right)
        
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
            rowWidth,rowMaxHeight = self._rowDimensions((item for item,align in row),remainingWidth)
            centerHeight += rowMaxHeight + self.vSpace
            if rowWidth > centerMaxWidth: 
                centerMaxWidth = rowWidth
        if centerHeight > 0:
            centerHeight -= self.vSpace # above loop adds one space too much
        
        self.state = None
        
        return QtCore.QSize(leftWidth + centerMaxWidth + rightWidth + 2*self.hMargin,
                            max(leftMaxHeight,centerHeight,rightMaxHeight) + 2* self.vMargin)
                    
    def _rowDimensions(self,items,availableWidth = None):
        """Helper function for sizeHint: Compute the size of *items* when they are laid out in a row and get
        a maximum of *availableWidth* horizontal space space."""      
        width = 0
        maxHeight = 0
        for item in items:
            w,h = item.sizeHint(self,availableWidth)
            width += w + self.hSpace
            if h > maxHeight:
                maxHeight = h
            if availableWidth is not None:
                availableWidth -= w + self.hSpace
                if availableWidth <= 0:
                    break
        
        if width > 0:
            width -= self.hSpace # above loop adds one space too much
        return width,maxHeight
    
    def getFontMetrics(self,style=STD_STYLE):
        """Return a QFontMetrics-object for a font with the given style."""
        if style is None:
            style = STD_STYLE
        self.font.setPointSize(style.fontSize)
        self.font.setBold(style.bold)
        self.font.setItalic(style.italic)
        return QtGui.QFontMetrics(self.font)
                
    def _configurePainter(self,style):
        """Configure the current painter to draw in the given style. This may only be used in the paint
        methods of DelegateItems."""
        if style is None:
            style = STD_STYLE
        self.font.setPointSize(style.fontSize)
        self.font.setBold(style.bold)
        self.font.setItalic(style.italic)
        self.painter.setFont(self.font)
        return QtGui.QFontMetrics(self.font)


class DelegateItem:
    """A DelegateItem encapsulates one ore more pieces of information (e.g. a text, a cover, a list of
    icons) that can be drawn by a delegate. Given a node in a itemview, subclasses of AbstractDelegate
    will create DelegateItems for the information to display and add them to the delegate's regions (similar
    to adding widgets to a layout). Then the delegate will draw those items or compute the sizeHint using the
    items' paint and sizeHint methods.
    """
    def sizeHint(self,delegate,availableWidth=None):
        """Compute the sizeHint of this item. *delegate* may be used to access variables like delegate.option
        or methods like delegate.getFontMetrics. When *availableWidth* is not None, the item should try to
        not use more horizontal space (if that is not possible it still may use more).
        """ 
        raise NotImplementedError()
    
    def paint(self,delegate,rect,align=LEFT):
        """Draw this item. *delegate* must be used to access variables like delegate.painter, delegate.option
        and methods like delegate._configurePainter. *rect* is the QRect into which the item should be
        painted (this differs from option.rect). *align* is one of the module constants ''LEFT'' or ''RIGHT''
        and determines the alignment of the item in the available space.
        """
        raise NotImplementedError()
    

class TextItem(DelegateItem):
    """A TextItem displays a single text. Optionally you can set the DelegateStyle of the text."""
    def __init__(self,text,style=None):
        self.text = text
        self.style = style
        
    def sizeHint(self,delegate,availableWidth=-1):
        rect = QtCore.QRect(0,0,availableWidth,14)
        bRect = delegate.getFontMetrics(self.style).boundingRect(rect,Qt.TextSingleLine,self.text)
        return bRect.width(),bRect.height()

    def paint(self,delegate,rect,align=LEFT):
        delegate._configurePainter(self.style)
        flags = Qt.TextSingleLine
        if align == RIGHT:
            flags |= Qt.AlignRight
        else: flags |= Qt.AlignLeft
        # Enable elided text
        #text = delegate.painter.fontMetrics().elidedText(self.text,Qt.ElideRight,rect.width())
        bRect = delegate.painter.drawText(rect,flags,self.text)
        return bRect.width(),bRect.height()
    
    
class CoverItem(DelegateItem):
    """A CoverItem displays a single cover in the given size (the cover is always quadratic)."""
    def __init__(self,coverPath,size):
        self.coverPath = coverPath
        self.size = size

    def sizeHint(self,delegate,availableWidth=None):
        return self.size,self.size
        
    def paint(self,delegate,rect,align=LEFT):
        if align == RIGHT:
            coverLeft = rect.x() + rect.width() - self.size
        else: coverLeft = rect.x()
        delegate.painter.drawPixmap(QtCore.QRect(coverLeft,rect.y(),self.size,self.size),
                                    QtGui.QPixmap(self.coverPath))
        return self.size,self.size


class ColorBarItem(DelegateItem):
    def __init__(self,background,width,height=None):
        self.background = background
        self.width = width
        self.height = height
        
    def sizeHint(self,delegate,availableWidth=None):
        return self.width,self.height if self.height is not None else 1
    
    def paint(self,delegate,rect,align=LEFT):
        if align == RIGHT:
            left = rect.x() + rect.width() - self.width
        else: left = rect.x()
        if self.height is None:
            height = rect.height()
        else: height = self.height()
        delegate.painter.fillRect(QtCore.QRect(left,rect.y(),self.width,height),
                                  self.background)
        return self.width,height


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

    def paint(self,delegate,rect,align=LEFT):
        if len(self.icons) == 0:
            return 0,0
        
        rows,columns = self._computeRowsAndColumns(rect.width())
        
        if align == RIGHT:
            right = rect.right() + 1 # Confer documentation of rect.right 
        else: left = rect.x()
        
        top = rect.top()
        for i,icon in enumerate(self.icons):
            if i >= columns:
                top += self.iconSize + self.vSpace
                i = 0
            if align == RIGHT:
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
    def __init__(self,leftTexts,rightTexts,style=STD_STYLE):
        self.leftTexts = leftTexts
        self.rightTexts = rightTexts
        self.style = style
        
    def sizeHint(self,delegate,availableWidth=None):
        fm = delegate.getFontMetrics(self.style)
        return self._layout(delegate,fm,availableWidth,0,paint=False) # availableHeight is not needed
    
    def paint(self,delegate,rect,align=LEFT):
        delegate.painter.save()
        fm = delegate._configurePainter(self.style)
        delegate.painter.translate(rect.x(),rect.y())
        result = self._layout(delegate,fm,rect.width(),rect.height(),paint=True)
        delegate.painter.restore()
        return result

    def _layout(self,delegate,fm,availableWidth,availableHeight,paint):
        #print("availableWidth{}: {}".format(" (paint)" if paint else '',availableWidth))
        leftFlags = Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap
        rightFlags = Qt.AlignRight | Qt.AlignTop | Qt.TextWordWrap
        
        baseHeight = 0
        for leftText,rightText in itertools.zip_longest(self.leftTexts,self.rightTexts,fillvalue=''):
            leftLength,leftMax = getTextInfo(fm,leftText)
            rightLength,rightMax = getTextInfo(fm,rightText)
            #print("Length: {} {}".format(leftLength,rightLength))
            #print("Max: {} {}".format(leftMax,rightMax))
            
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
            if paint:
                leftBRect = delegate.painter.drawText(rect,leftFlags,leftText)
            else: leftBRect = fm.boundingRect(rect,leftFlags,leftText)
            #print("LeftBRect{}: {}".format(" (paint)" if paint else '',leftBRect))
            
            rightColumnStart = leftBRect.width() + SEP_1
            #print("leftColumnLength: {}  | rightColumnStart: {}".format(leftColumnLength,rightColumnStart))
            rect = QtCore.QRect(rightColumnStart,baseHeight,
                                availableWidth-rightColumnStart,availableHeight-baseHeight)
            if paint:
                rightBRect = delegate.painter.drawText(rect,rightFlags,rightText)
            else: rightBRect = fm.boundingRect(rect,rightFlags,rightText)
            #print("RightBRect{}: {}".format(" (paint)" if paint else '',rightBRect))
            
            baseHeight += max(leftBRect.height(),rightBRect.height()) + LINESEP
        
        if baseHeight > 0:
            baseHeight -= LINESEP # above loop adds one space too much
        return availableWidth,baseHeight
    
        

class BrowserDelegate(AbstractDelegate):
    """Delegate used in the Browser. Does some effort to put flag icons at the optimal place using free space
    in the title row and trying not to increase the overall number of rows.
    """
    def __init__(self,view):
        super().__init__(view)
        self.leftTags = [tags.get(name) for name in
                            config.options.gui.browser.left_tags if tags.exists(name)]
        self.rightTags = [tags.get(name) for name in
                            config.options.gui.browser.right_tags if tags.exists(name)]
        self.coverSize = config.options.gui.browser.cover_size
        
    def layout(self,index,availableWidth):
        node = self.model.data(index)
        
        if isinstance(node,browser.ValueNode):
            for value in node.getDisplayValues():
                self.addCenter(TextItem(value))
                self.newRow()
        elif isinstance(node,browser.VariousNode):
            self.addCenter(TextItem(self.tr("Unknown/Various"),ITALIC_STYLE))
        elif isinstance(node,browser.HiddenValuesNode):
            self.addCenter(TextItem(self.tr("Hidden"),ITALIC_STYLE))
        elif isinstance(node,browser.LoadingNode):
            self.addCenter(TextItem(self.tr("Loading..."),ITALIC_STYLE))
        elif isinstance(node,models.Element):
            f = formatter.Formatter(node)
            
            # Prepare data
            if node.tags is None:
                node.loadTags()
            leftTexts,rightTexts,dateValues = self._prepareTags(f,node)
            if node.flags is None:
                node.loadFlags()
            flagIcons = [flag.icon for flag in f.flags(True) if flag.icon is not None]

            # Cover
            if node.hasCover():
                self.addLeft(CoverItem(node.getCover(self.coverSize),self.coverSize))
                availableWidth -= self.coverSize + self.hSpace
            
            # Title
            titleItem = TextItem(f.title(),BOLD_STYLE if node.isContainer() else STD_STYLE)
            self.addCenter(titleItem)
            
            # Flags
            # Here starts the mess...depending on the available space we want to put flags and if possible
            # even the date into the title row.
            if len(flagIcons) > 0:
                flagIconsItem = IconBarItem(flagIcons)
                titleLength = titleItem.sizeHint(self)[0]
                maxFlagsInTitleRow = flagIconsItem.maxColumnsIn(availableWidth - titleLength - self.hSpace)
                if maxFlagsInTitleRow >= len(flagIcons):
                    # Yeah, all flags fit into the title row
                    self.addCenter(flagIconsItem,align=RIGHT)
                    # Now we even try to fit the date into the first row
                    if dateValues is not None:
                        remainingWidth = availableWidth - titleLength \
                                         - flagIconsItem.sizeHint(self)[0] - 2* self.hSpace
                        if self.getFontMetrics().width(dateValues) <= remainingWidth:
                            self.addCenter(TextItem(dateValues),align=RIGHT)
                            rightTexts.pop(0) # Remove date from the tags we'll display
                    self.newRow()
                else:
                    self.newRow() # We'll put the flags either into right region or into a new row
                    
                    # Now we have an optimization problem: We want to minimize the rows, but the less rows
                    # we allow, the more columns we need. More columns means less space for tags in the
                    # center region and thus potentially a lot rows.

                    # First we compute a lower bound of the rows used by the tags
                    rowsForSure = max(len(leftTexts),len(rightTexts))
                    
                    if rowsForSure == 0:
                        # No tags
                        if 2*maxFlagsInTitleRow >= len(flagIcons):
                            flagIconsItem.rows = 2
                            self.addRight(flagIconsItem,align=RIGHT)
                        else: self.addCenter(flagIconsItem,align=RIGHT)
                    else:
                        # Do not use too many columns
                        maxFlagsInTitleRow = min(2,maxFlagsInTitleRow)
                        if maxFlagsInTitleRow == 0:
                            # Put all flags on the right side of the tags
                            flagIconsItem.columns = 1 if len(flagIcons) <= rowsForSure else 2
                            self.addCenter(flagIconsItem,align=RIGHT)
                        elif maxFlagsInTitleRow == 2:
                            # Also use the title row
                            flagIconsItem.columns = 1 if len(flagIcons) <= rowsForSure+1 else 2
                            self.addRight(flagIconsItem)
                        else:
                            # What's better? To use the title row (1 column) or not (2 columns)?
                            # Compare the number of additional rows we would need.
                            # Actually >= holds always, but in case of equality the first option is better
                            # (less columns).
                            if len(flagIcons)-1 <= math.ceil(len(flagIcons) / 2):
                                flagIconsItem.columns = 1
                                self.addRight(flagIconsItem)
                            else:
                                flagIconsItem.columns = 2
                                self.addCenter(flagIconsItem,align=RIGHT)
            else: 
                # This means len(flagIcons) == 0
                # Try to fit date tag into the first line
                if dateValues is not None:
                    titleLength = titleItem.sizeHint(self)[0]
                    if self.getFontMetrics().width(dateValues) <= availableWidth - titleLength - self.hSpace:
                        self.addCenter(TextItem(dateValues),align=RIGHT)
                        rightTexts.pop(0) # Remove date from the tags we'll display
                self.newRow()
            
            # Tags
            if len(leftTexts) > 0 or len(rightTexts) > 0:
                self.addCenter(MultiTextItem(leftTexts,rightTexts))
            
    def _prepareTags(self,formatter,element):
        leftTexts = []
        dateValues = None
        for tag in self.leftTags:
            if tag in element.tags:
                text = formatter.tag(tag,True,self._getTags)
                if len(text) > 0:
                    leftTexts.append(text)
        rightTexts = []
        for i,tag in enumerate(self.rightTags):
            if tag in element.tags:
                text = formatter.tag(tag,True,self._getTags)
                if len(text) > 0:
                    rightTexts.append(text)
                    if i == 0 and tag.name == "date":
                        dateValues = text
        
        return leftTexts,rightTexts,dateValues
                
    def _getTags(self,node,tag):
        """Return a list with the tag-values of the given tag of *node* which may be an element but also
        any other node appearing in the browser. This function is a callback function for Formatter.tag.
        """
        if isinstance(node,models.Element):
            if node.tags is None:
                node.loadTags()
            return node.tags[tag] if tag in node.tags else []
        elif isinstance(node,browser.ValueNode) and tag.id in node.valueIds:
            return node.values
        else: return []
        

class EditorDelegate(AbstractDelegate):
    """Delegate for the editor."""
    showPaths = True
    
    def __init__(self,view):
        super().__init__(view)
        self.leftTags = [tags.get(name) for name in
                            config.options.gui.editor.left_tags if tags.exists(name)]
        self.rightTags = [tags.get(name) for name in
                            config.options.gui.editor.right_tags if tags.exists(name)]
        self.coverSize = config.options.gui.editor.cover_size
        
    def layout(self,index,availableWidth):
        element = self.model.data(index)
        f = formatter.Formatter(element)
        
        # Prepare data
        if element.tags is None:
            element.loadTags()
        leftTexts,rightTexts = self._prepareTags(f,element)
        if element.flags is None:
            element.loadFlags()
        flagIcons,flagsWithoutIcon = [],[]
        for flag in f.flags(True):
            if flag.icon is not None:
                flagIcons.append(flag.icon)
            else: flagsWithoutIcon.append(flag)

        # In DB
        if not element.isInDB():
            self.addLeft(ColorBarItem(QtGui.QColor("yellow"),10))
            
        # Cover
        if element.hasCover():
            self.addLeft(CoverItem(element.getCover(self.coverSize),self.coverSize))
        
        # Flag-Icons
        if len(flagIcons) > 0:
            self.addRight(IconBarItem(flagIcons,columns=2 if len(flagIcons) > 2 else 1))
            
        # Title
        titleItem = TextItem(f.title(),BOLD_STYLE if element.isContainer() else STD_STYLE)
        self.addCenter(titleItem)
        
        self.newRow()
        
        if self.showPaths and element.isFile():
            self.addCenter(TextItem(element.path,ITALIC_STYLE))
            self.newRow()
            
        # Tags
        if len(leftTexts) > 0 or len(rightTexts) > 0:
            self.addCenter(MultiTextItem(leftTexts,rightTexts))
            self.newRow()
            
        # Flags without icon
        if len(flagsWithoutIcon) > 0:
            self.addCenter(TextItem(', '.join(flag.name for flag in flagWithoutIcon)))
            
    def _prepareTags(self,formatter,element):
        leftTexts = []
        for tag in self.leftTags:
            if tag in element.tags:
                text = formatter.tag(tag,True)
                if len(text) > 0:
                    leftTexts.append(text)
        rightTexts = []
        for i,tag in enumerate(self.rightTags):
            if tag in element.tags:
                text = formatter.tag(tag,True)
                if len(text) > 0:
                    rightTexts.append(text)
        
        return leftTexts,rightTexts
    