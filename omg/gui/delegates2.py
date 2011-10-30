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

import math, itertools

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from omg import models, tags, config
from omg.models import browser
from omg.gui import formatter

SIZE_HINT, PAINT = 1,2

LEFT,RIGHT = 1,2


class DelegateStyle:
    def __init__(self,fontSize,bold,italic):
        self.fontSize = fontSize
        self.bold = bold
        self.italic = italic


# Styles used in the delegates
STD_STYLE = DelegateStyle(11,False,False)
ITALIC_STYLE = DelegateStyle(11,False,True)
BOLD_STYLE = DelegateStyle(11,True,False)
        

class DefaultLayoutDelegate(QtGui.QStyledItemDelegate):
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
        self.left.append(item)
        
    def addRight(self,item):
        self.right.append(item)
        
    def newRow(self):
        self.center.append([])
        
    def addCenter(self,item,align=LEFT):
        if len(self.center) == 0:
            self.newRow()
        self.center[-1].append((item,align))
    
    def layout(self,index):
        """Layout the node with the given index. This method is called by paint and sizeHint."""
        raise NotImplementedError()
    
    def paint(self,painter,option,index):
        if self.state is not None:
            import sys
            sys.exit("Fatal error: DefaultLayoutDelegate.paint was called during painting.")
        self.state = PAINT
        
        # Initialize. Subclasses or Delegate items may access painter and option.
        self.painter = painter
        painter.save()
        painter.translate(option.rect.x(),option.rect.y())
        self.option = option
        
        # Collect items
        self.left,self.right,self.center = [],[],[]
        self.layout(index)
        
        leftOffset = self.hMargin
        rightOffset = self.hMargin
        availableHeight = option.rect.height() - 2*self.vMargin
        for item in self.left:
            rect = QtCore.QRect(leftOffset,self.vMargin,
                                option.rect.width() - leftOffset - rightOffset,availableHeight)
            width,height = item.paint(self,rect)
            leftOffset += width + self.hSpace
            
        for item in self.right:
            rect = QtCore.QRect(leftOffset,self.vMargin,
                                option.rect.width() - leftOffset - rightOffset,availableHeight)
            width,height = item.paint(self,rect,align=RIGHT)
            rightOffset += width + self.hSpace
        
        rowOffset = self.vMargin
        for row in self.center:
            lOff,rOff = leftOffset,rightOffset
            maxHeight = 0
            for item,align in row:
                rowLength = option.rect.width() - lOff - rOff
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
        
        painter.restore()
        self.painter = None
        self.option = None
        self.state = None

    # This is the implementation of QItemDelegate.sizeHint and will be called to compute the size of an item
    def sizeHint(self,option,index):
        if self.state is not None:
            import sys
            sys.exit("Fatal error: DefaultLayoutDelegate.sizeHint was called during painting.")
        self.state = SIZE_HINT

        # Total width available. Note that option.rect is useless due to a performance hack in Qt.
        # (Confer QTreeView::indexRowSizeHint in Qt's sources) 
        totalWidth = self.parent().viewport().width() - 2*self.hMargin
        totalWidth -= self.parent().indentation() * self.model.data(index).getDepth()
        
        # Collect items
        self.left,self.right,self.center = [],[],[]
        self.layout(index)
                       
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
        width = 0
        maxHeight = 0
        for item in items:
            w,h = item.sizeHint(self,availableWidth)
            width += w + self.hSpace
            if availableWidth is not None:
                availableWidth -= w + self.hSpace
            if h > maxHeight:
                maxHeight = h
        
        if width > 0:
            width -= self.hSpace # above loop adds one space too much
        return width,maxHeight
    
    def _getFontMetrics(self,style):
        """Return a QFontMetrics-object for a font with the given style."""
        if style is None:
            style = STD_STYLE
        self.font.setPixelSize(style.fontSize)
        self.font.setBold(style.bold)
        self.font.setItalic(style.italic)
        return QtGui.QFontMetrics(self.font)
                
    def _configurePainter(self,style):
        """Configure the painter of the current delegate context to draw in the given style."""
        if style is None:
            style = STD_STYLE
        self.font.setPixelSize(style.fontSize)
        self.font.setBold(style.bold)
        self.font.setItalic(style.italic)
        self.painter.setFont(self.font)
        return QtGui.QFontMetrics(self.font)


class DelegateItem:
    def sizeHint(self,delegate,availableWidth=None):
        raise NotImplementedError()
    
    def paint(self,delegate,rect,align=LEFT):
        raise NotImplementedError()
    

class TextItem(DelegateItem):
    def __init__(self,text,style=None):
        self.text = text
        self.style = style
        
    def sizeHint(self,delegate,availableWidth=None):
        rect = QtCore.QRect(0,0,availableWidth,14)
        bRect = delegate._getFontMetrics(self.style).boundingRect(rect,Qt.TextSingleLine,self.text)
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


class IconBarItem(DelegateItem):
    iconSize = 16
    hSpace = 1
    vSpace = 1
    
    def __init__(self,icons,maxIcons=None):
        self.icons = icons
        self.maxIcons = maxIcons
    
    def sizeHint(self,delegate,availableWidth=None):
        if len(self.icons) == 0:
            return 0,0
        width = self.iconSize + 2*self.hSpace
        iconNumber = len(self.icons) if self.maxIcons is None else min(len(self.icons),self.maxIcons)
        return width,iconNumber * self.iconSize + (iconNumber + 1) * self.vSpace

    def paint(self,delegate,rect,align=LEFT):
        if len(self.icons) == 0:
            return 0,0
        
        if align == RIGHT:
            left = rect.x() + rect.width() - self.hSpace - self.iconSize
        else: left = rect.x() + self.hSpace
        
        top = self.vSpace
        for icon in self.icons:
            delegate.painter.drawPixmap(QtCore.QRect(left,top,self.iconSize,self.iconSize),
                                        icon.pixmap(self.iconSize,self.iconSize))
            top += self.iconSize + self.vSpace
        
        return self.iconSize + 2*self.hSpace, top


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
        fm = delegate._getFontMetrics(self.style)
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
    
        

class BrowserDelegate(DefaultLayoutDelegate):
    def __init__(self,view):
        super().__init__(view)
        self.leftTags = [tags.get(name) for name in
                            config.options.gui.browser.left_tags if tags.exists(name)]
        self.rightTags = [tags.get(name) for name in
                            config.options.gui.browser.right_tags if tags.exists(name)]
        self.coverSize = config.options.gui.browser.cover_size
        
    def layout(self,index):
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
            # Cover
            if node.hasCover():
                self.addLeft(CoverItem(node.getCover(32),32))
            
            # Tags (including title)
            if node.tags is None:
                node.loadTags()
            
            if not node.isContainer():
                self.addCenter(TextItem(f.title()))
            else:
                self.addCenter(TextItem(f.title(),BOLD_STYLE))
                leftTexts = []
                for tag in self.leftTags:
                    if tag in node.tags:
                        text = f.tag(tag,True,self._getTags)
                        if len(text) > 0:
                            leftTexts.append(text)
                rightTexts = []
                for tag in self.rightTags:
                    if tag in node.tags:
                        text = f.tag(tag,True,self._getTags)
                        if len(text) > 0:
                            rightTexts.append(text)
                
                if len(leftTexts) > 0 or len(rightTexts) > 0:
                    self.newRow()
                    self.addCenter(MultiTextItem(leftTexts,rightTexts))
                
            # Flags
            if node.flags is None:
                node.loadFlags()
            
            if node.isContainer():
                if len(node.flags) > 0:
                    icons = [flag.icon for flag in node.flags if flag.icon is not None]
                    if len(icons) > 0:
                        self.addRight(IconBarItem(icons,3))
                    
            #if node.tags is not None and tags.get("date") in node.tags:
            #    text = ", ".join(str(d) for d in node.tags[tags.get("date")])
             #   self.addCenter(TextItem(text),RIGHT)
            
    def _getTags(self,node,tag):
        """Return a list with the tag-values of the given tag of *node* which may be an element but also
        any other node appearing in the browser. This function is submitted to Formatter.tag.
        """
        if isinstance(node,models.Element):
            if node.tags is None:
                node.loadTags()
            return node.tags[tag] if tag in node.tags else []
        elif isinstance(node,browser.ValueNode) and tag.id in node.valueIds:
            return node.values
        else: return []