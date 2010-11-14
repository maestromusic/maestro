#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#
from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from omg import tags

class TagLabel(QtGui.QLabel):
    iconSize = QtCore.QSize(24,24)
    
    def __init__(self,tag=None,parent=None):
        QtGui.QLabel.__init__(self,parent)
        self.setTag(tag)

    def setText(self,text):
        if text == '':
            self.setTag(None)
        else: self.setTag(tags.fromTranslation(text))
        
    def getTag(self,tag):
        return self.tag
        
    def setTag(self,tag):
        self.tag = tag
        if tag is None:
            self.clear()
        else:
            if tag.iconPath() is not None:
                QtGui.QLabel.setText(self,'<img src="{}" widht="{}" height="{}"> {}'
                                    .format(tag.iconPath(),self.iconSize.width(),self.iconSize.height(),tag.translated()))
            else: QtGui.QLabel.setText(self,tag.translated())


class TagTypeBox(QtGui.QComboBox):
    def __init__(self,defaultTag = None,parent=None):
        QtGui.QComboBox.__init__(self,parent)
        self.setEditable(True)
        self.setInsertPolicy(QtGui.QComboBox.NoInsert)
        if defaultTag is None:
            self.setEditText('')
        
        for tag in tags.tagList:
            if tag.iconPath() is not None:
                self.addItem(QtGui.QIcon(tag.iconPath()),tag.translated())
            else: self.addItem(tag.translated())
            if tag == defaultTag:
                self.setCurrentIndex(self.count()-1)
                
    def getTag(self):
        text = self.currentText().strip()
        if text[0] == text[-1] and text[0] in ['"',"'"]: # Don't translate if the text is quoted
            return tags.get(text[1:-1])
        else: return tags.fromTranslation(text)
