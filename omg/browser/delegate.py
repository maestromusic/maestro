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
from . import layouter

class Delegate(QtGui.QStyledItemDelegate):
    def __init__(self,parent,model,layouter):
        QtGui.QStyledItemDelegate.__init__(self,parent)
        self.model = model
        self.layouter = layouter

    def paint(self,painter,option,index):
        node = self.model.data(index,Qt.DisplayRole)
        option = QtGui.QStyleOptionViewItemV4(option)
        document = self.layouter.layout(node)
        if isinstance(document,layouter.SingleLineLayout):
            option.text = document.text
            if document.bold:
                option.font.setWeight(QtGui.QFont.Bold)
            self._drawControl(option,painter)
        else:
            assert(isinstance(document,QtGui.QTextDocument))
            self._drawControl(option,painter)
            painter.save()
            painter.translate(option.rect.left(),option.rect.top())
            rect = QtCore.QRectF(0,0,option.rect.width(),option.rect.height())
            document.drawContents(painter,rect)
            painter.restore()

    def sizeHint(self,option,index):
        node = self.model.data(index,Qt.DisplayRole)
        option = QtGui.QStyleOptionViewItemV4(option);
        document = self.layouter.layout(node)
        if isinstance(document,layouter.SingleLineLayout):
            option.text = document.text
            if document.bold:
                option.font.setWeight(QtGui.QFont.Bold)
            return self._sizeFromOption(option)
        else: return document.size().toSize() # transforming QSizeF into QSize
        
    def _drawControl(self,option,painter):
        QtGui.QApplication.style().drawControl(QtGui.QStyle.CE_ItemViewItem,option,painter)
        
    def _sizeFromOption(self,option):
        return QtGui.QApplication.style().sizeFromContents(QtGui.QStyle.CT_ItemViewItem,option,QtCore.QSize())