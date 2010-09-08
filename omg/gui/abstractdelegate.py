#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

class DelegateStyle:
    def __init__(self,fontSize,bold,italic):
        self.fontSize = fontSize
        self.bold = bold
        self.italic = italic

# Standard style which is used by default
STD_STYLE = DelegateStyle(11,False,False)

class DelegateContext:
    """A DelegateContext stores stuff during the process of painting a widget or computing its size."""
    def __init__(self,painter,option,rect=None):
        self.painter = painter
        self.option = option
        if painter is None:
            self.width = 0
            self.height = 0
            self.coverSize = None
        else:
            self.rect = rect


class AbstractDelegate(QtGui.QStyledItemDelegate):
    """This is how AbstractDelegate works: Whenever the view calls paint or sizeHint a DelegateContext is created to store some variables needed for the paint process (e.g. the painter) or the size computation (e.g. the size). In particular the context stores whether we are painting or computing the size. In the case of painting now getBackground is called and the background of the item is drawn. Now layout is invoked in both cases. This method which must be implemented in subclasses should use methods like addLine and drawCover to fill the item with data. The implementations of addLine, drawCover, etc. will paint or compute the size using the information of the stored DelegateContext. The advantage of this method is that you have to write only one method in the subclass that works for both paint and sizeHint...and that you don't have to deal with ugly size computations and drawing code."""
    context = None
    hSpace = 2
    vSpace = 1
    hMargin = 2
    vMargin = 1
    
    def __init__(self,parent):
        QtGui.QStyledItemDelegate.__init__(self,parent)
        self.font = QtGui.QFont()
    
    def setFont(self,font):
        self.font = font

    # Abstract methods which must be implemented in subclasses
    def layout(self,index):
        """Layout the node with the given index. This method is called by paint and sizeHint. Its implementation should use drawCover and addLine."""
        raise NotImplementedError()

    def getBackground(self,index):
        """Return a QBrush which should be used to fill the background of the node with the given index, or None if the background should not be filled. This method is called by paint. The default implementation returns None."""
        return None

    # This is the implementation of QItemDelegate.paint and will be called to draw an item.
    def paint(self,painter,option,index):
        if self.context is not None:
            # When an exception is raised in paint or sizeHint, it won't stop the programm. Paint/sizeHint is then called all the time and spams the console with unhelpful errors ("painter ended with unrestored states") which hide the exception's own error message. Therefore we stop here.
            import sys
            sys.exit("Fatal error: AbstractDelegate.paint was called during painting.")
        
        # Initialize
        option = QtGui.QStyleOptionViewItemV4(option)
        rect = QtCore.QRect(0,0,option.rect.width()-2*self.hMargin,option.rect.height()-2*self.vMargin)
        self.context = DelegateContext(painter,option,rect)
        painter.save()
        
        # Paint background
        background = self.getBackground(index)
        if background is not None:
            option.backgroundBrush = background
        QtGui.QApplication.style().drawControl(QtGui.QStyle.CE_ItemViewItem,option,painter)
        
        # Paint data
        painter.translate(option.rect.left()+self.hMargin,option.rect.top()+self.vMargin)
        self.layout(index)
        
        painter.restore()
        self.context = None

    # This is the implementation of QItemDelegate.sizeHint and will be called to compute the size of an item
    def sizeHint(self,option,index):
        if self.context is not None:
            # Confer self.paint
            import sys
            sys.exit("Fatal error: AbstractDelegate.paint was called during painting.")
        self.context = DelegateContext(None,option)
        self.layout(index)
        if self.context.coverSize is None:
            result = QtCore.QSize(self.context.width+2*self.hMargin,self.context.height+2*self.vMargin)
        else:
            result = QtCore.QSize(self.context.coverSize+self.hSpace+self.context.width+2*self.hMargin,
                                  max(self.context.coverSize,self.context.height)+2*self.vMargin)
        self.context = None
        return result
    
    def drawCover(self,coverSize,element=None,cover=None):
        """Draw the cover of <element> or, if <element> is None, the given cover using <coverSize>x<coverSize> pixels."""
        context = self.context
        if context.painter is None:
            if cover is not None or element.hasCover():
                context.coverSize = coverSize
        else: 
            if cover is None:
                if element is None:
                    raise ValueError("Either element or cover must be given")
                cover = element.getCover(coverSize,cache=True) # is None if element has no cover
            if cover is not None:
                imageRect = QtCore.QRect(0,0,min(context.option.rect.width(),coverSize),
                                         min(context.option.rect.height(),coverSize))
                context.painter.drawImage(imageRect,cover,imageRect)
                context.painter.translate(coverSize+self.hSpace,0)
                context.rect = QtCore.QRect(0,0,context.rect.width()-coverSize-self.hSpace,context.rect.height())
        
    def addLine(self,text1,text2="",style1=STD_STYLE,style2=None):
        """Add a line with one or two texts. <text1> will be aligned left, <text2> will be aligned right. Via the optional parameters <style1> and <style2> you may specify DelegateStyles which will be used for <text1> and <text2>, respectively. Note that <style1> defaults to abstractdelegate.STD_STYLE and <style2> defaults to None, which means that <style1> is used for both texts."""
        assert isinstance(text1,str) and isinstance(text2,str)
        
        if text1 == "" and text2 == "":
            return
        
        if style2 is None:
            style2 = style1
            
        context = self.context
        if context.painter is None:
            if text1 != "":
                size1 = self._getFontMetrics(style1).size(Qt.TextSingleLine,text1)
            else: size1 = QtCore.QSize(0,0)
            if text2 != "":
                size2 = self._getFontMetrics(style2).size(Qt.TextSingleLine,text2)
            else: size2 = QtCore.QSize(0,0)
            space = self.hSpace if text1 != "" and text2 != "" else 0  # space between the two entries
            
            context.width = max(context.width,size1.width()+size2.width()+space)
            context.height = context.height + self.vSpace + max(size1.height(),size2.height())
        else:
            if text1 != "":
                self._configurePainter(style1)
                boundingRect1 = context.painter.drawText(context.rect,Qt.TextSingleLine,text1)
            else: boundingRect1 = QtCore.QRect(context.rect.left,context.rect.top,0,0)
            
            if text2 != "":
                self._configurePainter(style2)
                # Compute the topleft corner of the second text
                topLeft = QtCore.QPoint(boundingRect1.right()+self.hSpace,context.rect.top())
                boundingRect2 = context.painter.drawText(QtCore.QRect(topLeft,context.rect.bottomRight()),
                                                         Qt.AlignRight|Qt.TextSingleLine,
                                                         text2)
                context.rect.setTop(context.rect.top()+self.vSpace+max(boundingRect1.height(),boundingRect2.height()))
            else: context.rect.setTop(context.rect.top()+self.vSpace+boundingRect1.height())
    
    def _configurePainter(self,style):
        """Configure the painter of the current delegate context to draw in the given style."""
        self.font.setPixelSize(style.fontSize)
        self.font.setBold(style.bold)
        self.font.setItalic(style.italic)
        self.context.painter.setFont(self.font)
        
    def _getFontMetrics(self,style):
        """Return a QFontMetrics-object for a font with the given style."""
        self.font.setPixelSize(style.fontSize)
        self.font.setBold(style.bold)
        self.font.setItalic(style.italic)
        return QtGui.QFontMetrics(self.font)