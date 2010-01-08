#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtGui
from omg import config,tags
from . import models

_artistTags = None

def _initTags():
    global _artistTags
    _artistTags = [tags.get(tagname) for tagname in config.get("browser","artist_tags").split(',')]
    
_stdCharFormat = QtGui.QTextCharFormat()
_stdCharFormat.setFontPointSize(11)
_titleCharFormat = QtGui.QTextCharFormat()
_titleCharFormat.setFontPointSize(11)
_titleCharFormat.setFontWeight(QtGui.QFont.Bold)


class ComplexLayouter:
    def __init__(self):
        if _artistTags is None:
            _initTags()
            
    def layout(self,element):
        document = QtGui.QTextDocument()
        cursor = QtGui.QTextCursor(document)
        
        cursor.blockFormat().setNonBreakableLines(True) # Don't break lines)
        
        # Construct the artist line
        artistList = []
        for tag in _artistTags:
            if tag in element.tags:
                artistList.extend(element.tags[tag])
        
        if artistList:
            cursor.insertText(", ".join(artistList),_stdCharFormat)
            cursor.insertBlock()
        
        if element.isFile():
            cursor.insertText(element.getTitle(),_stdCharFormat)
        elif tags.DATE in element.tags:
            dateString = "/".join(str(date.year) for date in element.tags[tags.DATE]) # Support multiple date tags
            cursor.insertText("{0} - {1}".format(dateString,element.getTitle()),_titleCharFormat)
        else: cursor.insertText(element.getTitle(),_titleCharFormat)
        
        #~ if isinstance(element,browsermodels.FileNode) and element.tags[tags.ALBUM]:
            #~ cursor.insertBlock()
            #~ cursor.insertText(element.tags[tags.ALBUM][0],_stdCharFormat)
            
        return document
        
        
class SingleLineLayout():
    def layout(self,element):
        document = QtGui.QTextDocument()
        cursor = QtGui.QTextCursor(document)
        
        cursor.blockFormat().setNonBreakableLines(True) # Don't break lines)
        
        # Construct the artist-part
        artistList = []
        for tag in _artistTags:
            artistList.extend([artist for artist in element.tags[tag]])
        
        if artistList:
            cursor.insertText(",".join(artistList),_stdCharFormat)
            cursor.insertText(": ")
            
        cursor.insertText(element.getTitle(),_titleCharFormat)
        
        #~ if element.tags[tags.ALBUM]:
            #~ cursor.insertBlock()
            #~ cursor.insertText(element.tags[tags.ALBUM][0],_stdCharFormat)