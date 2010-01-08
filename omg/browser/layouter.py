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
_stdCharFormat.setFontPointSize(10)
_titleCharFormat = QtGui.QTextCharFormat()
_titleCharFormat.setFontPointSize(10)
_titleCharFormat.setFontWeight(QtGui.QFont.Bold)


class ComplexLayouter:
    def __init__(self):
        if _artistTags is None:
            _initTags()
            
    def layout(self,element):
        document = QtGui.QTextDocument()
        cursor = QtGui.QTextCursor(document)
        
        cursor.blockFormat().setNonBreakableLines(True) # Don't break lines)
        
        cursor.insertText(element.getTitle())
        #~ # Construct the artist line
        #~ artistList = []
        #~ for tag in _artistTags:
            #~ artistList.extend([artist for artist in element.tags[tag]])
        #~ 
        #~ if artistList:
            #~ cursor.insertText(", ".join(artistList),_stdCharFormat)
            #~ cursor.insertBlock()
        #~ 
        #~ if isinstance(element,browsermodels.ContainerNode):
            #~ cursor.insertText(element.getTitle(),_titleCharFormat)
        #~ else: cursor.insertText(element.getTitle(),_stdCharFormat)
        #~ 
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