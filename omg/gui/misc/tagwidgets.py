#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#
from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from omg import tags, db

class TagLabel(QtGui.QLabel):
    iconSize = QtCore.QSize(24,24)
    
    def __init__(self,tag=None,parent=None):
        QtGui.QLabel.__init__(self,parent)
        self.setTag(tag)

    def text(self):
        if self.tag is not None:
            return self.tag.translated()
        else: return ''
        
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


class TagLineEdit(QtGui.QLineEdit):
    # Dictionary mapping tags to all the values which have been entered in a TagLineEdit during this application. Will be used in the completer.
    insertedValues = {}
    
    def __init__(self,tag,parent=None):
        QtGui.QLineEdit.__init__(self,parent)
        self.editingFinished.connect(self._handleEditingFinished)
        self.tag = None # Create the variable
        self.setTag(tag)

    def setTag(self,tag):
        if tag != self.tag:
            self.tag = tag
            if tag in self.insertedValues:
                completionStrings = self.insertedValues[tag][:] # copy the list
            else: completionStrings = []

            if tag != tags.TITLE and tag.isIndexed():
                ext = [str(value) for value in db.allTagValues(tag) if str(value) not in completionStrings]
                completionStrings.extend(ext)

            if len(completionStrings) > 0:
                self.setCompleter(QtGui.QCompleter(completionStrings))

    def _handleEditingFinished(self):
        if self.tag.isValid(self.text()):
            # Add value to insertedValues (which will be shown in the completer)
            if self.tag not in self.insertedValues:
                self.insertedValues[self.tag] = []
            if self.text() not in self.insertedValues[self.tag]:
                # insert at the beginning, so that the most recent values will be at the top of the completer's list.
                self.insertedValues[self.tag].insert(0,self.text())
