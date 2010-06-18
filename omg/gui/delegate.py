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
    def __init__(self,column1,column2):
        self.column1 = column1
        self.column2 = column2
        

    def paint(self,painter,option):
        _drawControl(option,painter)
        painter.translate(option.rect.left(),option.rect.top())
        rect = QtCore.QRectF(0,0,option.rect.width(),option.rect.height())
        boundingRect = painter.drawText(rect,Qt.AlignRight | Qt.TextSingleLine,self.column2)
        rect.setRight(boundingRect.left()-1)
        painter.drawText(rect,Qt.TextSingleLine,self.column1)
        
        
    def sizeHint(self,option,font):
        rect = QtCore.QRectF(0,0,option.rect.width(),option.rect.height())
        fontMetrics = QtGui.QFontMetrics(font)
        boundingRect = fontMetrics.boundingRect(self.column1).united(fontMetrics.boundingRect(self.column2))
        boundingRect.setRight(boundingRect.right()+1)# Gap between columns
        return QtCore.QSize(boundingRect.width(),boundingRect.height())
        
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
        layout.paint(painter,option)
        painter.restore()

    def sizeHint(self,option,index):
        node = self.model.data(index,Qt.DisplayRole)
        option = QtGui.QStyleOptionViewItemV4(option);
        layout = self.layouter.layout(node)
        return layout.sizeHint(option,self.font)