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
from omg import config, strutils, tags
from omg.models import playlist

def _drawControl(option,painter):
    QtGui.QApplication.style().drawControl(QtGui.QStyle.CE_ItemViewItem,option,painter)

def _sizeFromOption(option):
    return QtGui.QApplication.style().sizeFromContents(QtGui.QStyle.CT_ItemViewItem,option,QtCore.QSize())
    
class SingleLineLayout:
    def __init__(self,text,options=[]):
        self.text = text
        self.options = options
    
    def paint(self,painter,option):
        option.text = self.text
        if "bold" in self.options:
            option.font.setWeight(QtGui.QFont.Bold)
        if "italic" in self.options:
            option.font.setStyle(QtGui.QFont.StyleItalic)
        _drawControl(option,painter)
        
    def sizeHint(self,option,font):
        option.text = self.text
        if "bold" in self.options:
            option.font.setWeight(QtGui.QFont.Bold)
        if "italic" in self.options:
            option.font.setStyle(QtGui.QFont.StyleItalic)
        return _sizeFromOption(option)
        
        
class DocumentLayout:
    def __init__(self,document):
        self.document = document
    
    def paint(self,painter,option):
        _drawControl(option,painter)
        painter.translate(option.rect.left(),option.rect.top())
        rect = QtCore.QRectF(0,0,option.rect.width(),option.rect.height())
        self.document.drawContents(painter,rect)
    
    def sizeHint(self,option,font):
        return self.document.size().toSize() # transforming QSizeF into QSize
        

class TwoColumnsLayout:
    space = 2
    
    def __init__(self,column1,column2):
        self.column1 = column1
        self.column2 = column2
        
    def paint(self,painter,option):
        _drawControl(option,painter)
        painter.translate(option.rect.left()+self.space,option.rect.top())
        rect = QtCore.QRectF(0,0,option.rect.width()-2*self.space,option.rect.height())
        boundingRect = painter.drawText(rect,Qt.AlignRight | Qt.TextSingleLine,self.column2)
        rect.setRight(boundingRect.left()-1)
        painter.drawText(rect,Qt.TextSingleLine,self.column1)
        
        
    def sizeHint(self,option,font):
        # Width doesn't matter
        return QtCore.QSize(1,QtGui.QFontMetrics(font).height())

class ContainerLayout:
    space = 2
    largeSize = 12
    smallSize = 10
    
    def __init__(self,container):
        assert isinstance(container,playlist.PlaylistElement)
        self.container = container
    
    def paint(self,painter,option):
        _drawControl(option,painter)
        
        # Get and format data
        if self.container.getPosition() is None:
            titleString = self.container.getTitle()
        else: titleString = "{0} - {1}".format(self.container.getPosition(),self.container.getTitle())
        
        artistString = ",".join(self.container.tags[tags.COMPOSER] + self.container.tags[tags.ARTIST])
        piecesString = "Stück" if self.container.getChildrenCount() == 1 else "Stücke"
        piecesString = "{0} {1}".format(self.container.getChildrenCount(),piecesString)
        genreString = ",".join(self.container.tags[tags.GENRE])
        dateString = ",".join(str(date) for date in self.container.tags[tags.DATE])
        lengthString = strutils.formatLength(self.container.getLength())
        
        coverSize = config.get("playlist","cover_size")
        cover = self.container.getCover(coverSize,cache=True)
        
        # Paint
        painter.translate(option.rect.left()+self.space,option.rect.top()+self.space)
        if cover is not None:
            imageRect = QtCore.QRect(0,0,min(option.rect.width(),coverSize),min(option.rect.height(),coverSize))
            painter.drawImage(imageRect,self.container.getCover(coverSize,cache=True),imageRect)
            painter.translate(coverSize+self.space,0)
            rect = QtCore.QRect(0,0,option.rect.width()-coverSize-3*self.space,option.rect.height()-2*self.space)
        else: rect = QtCore.QRect(0,0,option.rect.width()-2*self.space,option.rect.height()-2*self.space)
        
        font = QtGui.QFont()
        font.setBold(True)
        font.setPixelSize(self.largeSize)
        painter.setFont(font)
        self.drawSingleEntryLine(painter,titleString,rect)
        font.setItalic(True)
        painter.setFont(font)
        self.drawSingleEntryLine(painter,artistString,rect)
        font.setBold(False)
        font.setItalic(False)
        font.setPixelSize(self.smallSize)
        painter.setFont(font)
        self.drawDoubleEntryLine(painter,genreString,piecesString,rect)
        self.drawDoubleEntryLine(painter,dateString,lengthString,rect)
            
    def drawSingleEntryLine(self,painter,entry,rect):
        boundingRect = painter.drawText(rect,QtCore.Qt.TextSingleLine,entry)
        rect.setTop(rect.top()+painter.fontMetrics().height()+self.space)
        
    def drawDoubleEntryLine(self,painter,entry1,entry2,rect):
        boundingRect = painter.drawText(rect,Qt.TextSingleLine,entry1)
        topLeft = QtCore.QPoint(boundingRect.right()+self.space,rect.top())
        painter.drawText(QtCore.QRect(topLeft,rect.bottomRight()),Qt.AlignRight|Qt.TextSingleLine,entry2)
        rect.setTop(rect.top()+painter.fontMetrics().height()+self.space)
        
    def sizeHint(self,option,font):
        # Width doesn't matter, compute only the height
        height = 2*self.space # top and bottom space
        font.setBold(True)
        height = QtGui.QFontMetrics(font).height() + self.space
        font.setItalic(True)
        height = height + QtGui.QFontMetrics(font).height() + self.space
        font.setBold(False)
        font.setItalic(False)
        height = height + 2 * QtGui.QFontMetrics(font).height() + self.space # Last two rows
        
        coverSize = config.get("playlist","cover_size")
        cover = self.container.getCover(coverSize,cache=True)
        if cover is not None:
            return QtCore.QSize(coverSize,max(coverSize,height))
        else: return QtCore.QSize(0,height)
            
class Delegate(QtGui.QStyledItemDelegate):
    def __init__(self,parent,model,layouter,font):
        QtGui.QStyledItemDelegate.__init__(self,parent)
        self.model = model
        self.layouter = layouter
        self.font = font

    def paint(self,painter,option,index):
        node = self.model.data(index,Qt.DisplayRole)
        option = QtGui.QStyleOptionViewItemV4(option)
        layout = self.layouter.layout(node)
        painter.save()
        painter.setFont(self.font)
        if node.isFile() and self.model.isPlaying(node):
            painter.fillRect(option.rect,QtGui.QColor(110,149,229))
        layout.paint(painter,option)
        painter.restore()

    def sizeHint(self,option,index):
        node = self.model.data(index,Qt.DisplayRole)
        option = QtGui.QStyleOptionViewItemV4(option);
        layout = self.layouter.layout(node)
        return layout.sizeHint(option,self.font)