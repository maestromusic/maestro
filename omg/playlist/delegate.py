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

class Delegate(QtGui.QStyledItemDelegate):
    def __init__(self,parent,model):
        QtGui.QStyledItemDelegate.__init__(self,parent)
        self.model = model
        
    def paint(self,painter,option,index):
        node = self.model.data(index,Qt.DisplayRole)
        option = QtGui.QStyleOptionViewItemV4(option)
        option.text = self.model.getColumns()[index.column()].getData(node)
        self._drawControl(option,painter)

    def sizeHint(self,option,index):
        node = self.model.data(index,Qt.DisplayRole)
        option = QtGui.QStyleOptionViewItemV4(option)
        option.text = self.model.getColumns()[index.column()].getData(node)
        return self._sizeFromOption(option)
        
    def _drawControl(self,option,painter):
        option.widget.style().drawControl(QtGui.QStyle.CE_ItemViewItem,option,painter)
        
    def _sizeFromOption(self,option):
        return option.widget.style().sizeFromContents(QtGui.QStyle.CT_ItemViewItem,option,QtCore.QSize())