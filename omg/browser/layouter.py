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
from . import nodes
    
_stdCharFormat = QtGui.QTextCharFormat()
_stdCharFormat.setFontPointSize(11)
_titleCharFormat = QtGui.QTextCharFormat()
_titleCharFormat.setFontPointSize(11)
_titleCharFormat.setFontWeight(QtGui.QFont.Bold)

class SingleLineLayout:
    def __init__(self,text,bold = False):
        self.text = text
        self.bold = bold
        
        
class Layouter:
    def layout(self,node):
        if isinstance(node,nodes.RootNode):     # TODO Only debugging
            return SingleLineLayout("<Rootnode>")
        
        if isinstance(node,nodes.VariousNode):
            return SingleLineLayout("Verschiedene/Unbekannt")
            
        # First two special cases which allow to display the node in just one line
        if isinstance(node,nodes.ValueNode):
            return SingleLineLayout(node.value)
        # The ElementNode contains just the title-tag or no tags at all
        elif len(node.tags) == 0 or (len(node.tags) == 1 and tags.TITLE in node.tags):
            # Use bold font if the node is a container
            if node.position is not None:
                return SingleLineLayout("{0} - {1}".format(node.position,node.getTitle()),not node.isFile())
            else: return SingleLineLayout(node.getTitle(),not node.isFile())
                
        # Now comes the generic handling via QTextDocuments
        document = QtGui.QTextDocument()
        cursor = QtGui.QTextCursor(document)
        cursor.blockFormat().setNonBreakableLines(True) # Don't break lines
        #~ if hasattr(node,"mergedNode"):
            #~ for mergedNode in node.mergedNodes:
                #~ self._insertNode(cursor,mergedNode)
        self._insertNode(cursor,node)
        return document
    
    
    def _insertNode(self,cursor,node):
        if isinstance(node,nodes.ValueNode):
            cursor.insertText(node.value,_stdCharFormat)
            cursor.insertBlock()
            return
        # ElementNodes
        artistList = []
        for tag in tags.artistTags:
            if tag in node.tags:
                artistList.extend(node.tags[tag])
        
        if artistList:
            cursor.insertText(", ".join(artistList),_stdCharFormat)
            cursor.insertBlock()
        
        if not node.elements:
            if node.position is not None:
                cursor.insertText("{0} - {1}".format(node.position,node.getTitle()),_stdCharFormat)
            else: cursor.insertText(node.getTitle(),_stdCharFormat)
        elif tags.DATE in node.tags:
            dateString = "/".join(str(date.year) for date in node.tags[tags.DATE]) # Support multiple date tags
            cursor.insertText("{0} - {1}".format(dateString,node.getTitle()),_titleCharFormat)
        else: cursor.insertText(node.getTitle(),_titleCharFormat)
        
        # Ugly: Album containers have the album tag also as title, so we have to take care that it is not displayed twice.
        # whereas it should be displayed twice if node is a file (which then has the same name as its album).
        if tags.ALBUM in node.tags and (node.isFile() or ", ".join(node.tags[tags.ALBUM]) != node.getTitle()):
            cursor.insertBlock()
            cursor.insertText(", ".join(node.tags[tags.ALBUM]),_stdCharFormat)