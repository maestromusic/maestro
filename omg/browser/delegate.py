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
from omg import tags
from omg.browser import models

counter = 0

class Delegate(QtGui.QStyledItemDelegate):
    def __init__(self,parent,model,layouter):
        QtGui.QStyledItemDelegate.__init__(self,parent)
        self.model = model
        self.layouter = layouter
    
    def paintValueNode(self,painter,option,node):
        option.text = node.value
        self._drawControl(option,painter)
        
    def paintElementNode(self,painter,option,node):
        self._drawControl(option,painter)
        painter.save()
        painter.translate(option.rect.left(),option.rect.top())
        rect = QtCore.QRectF(0,0,option.rect.width(),option.rect.height())
        self.layouter.layout(node).drawContents(painter,rect)
        painter.restore()
    
    def paintGroupNode(self,painter,option,node):
        option.text = node.value
        option.font.setStyle(QtGui.QFont.StyleItalic)
        painter.save()
        painter.setPen(QtGui.QPen(QtGui.QColor(0xEE,0xEE,0xEE)))
        painter.setBrush(QtGui.QBrush(QtGui.QColor(0xF4,0xF4,0xF4)))
        painter.drawRect(option.rect)
        painter.restore()
        self._drawControl(option,painter)
    
    def valueNodeSize(self,option,node):
        option.text = node.value
        return self._sizeFromOption(option)
        
    def elementNodeSize(self,option,node):
        return self.layouter.layout(node).size().toSize() # transforming QSizeF into QSize
        
    def groupNodeSize(self,option,node):
        option.text = node.value
        option.font.setStyle(QtGui.QFont.StyleItalic)
        return self._sizeFromOption(option)
        
    def paint(self,painter,option,index):
        global counter
        counter = counter + 1
        print("paint {0}".format(counter))
        node = self.model.data(index,Qt.DisplayRole)
        option = QtGui.QStyleOptionViewItemV4(option)
        
        if isinstance(node,models.ElementNode):
            self.paintElementNode(painter,option,node)
        elif isinstance(node,models.ValueNode):
            self.paintValueNode(painter,option,node)
        elif isinstance(node,models.GroupNode):
            self.paintGroupNode(painter,option,node)
        else: raise Exception("Unknown node type: {0}".format(node.getClass()))
            
    def sizeHint(self,option,index):
        node = self.model.data(index,Qt.DisplayRole)
        option = QtGui.QStyleOptionViewItemV4(option);
        
        if isinstance(node,models.ElementNode):
            return self.elementNodeSize(option,node)
        elif isinstance(node,models.ValueNode):
            return self.valueNodeSize(option,node)
        elif isinstance(node,models.GroupNode):
            return self.groupNodeSize(option,node)
        else: raise Exception("Unknown node type: {0}".format(node.getClass()))
        
    def _drawControl(self,option,painter):
        option.widget.style().drawControl(QtGui.QStyle.CE_ItemViewItem,option,painter)
        
    def _sizeFromOption(self,option):
        return option.widget.style().sizeFromContents(QtGui.QStyle.CT_ItemViewItem,option,QtCore.QSize())
        