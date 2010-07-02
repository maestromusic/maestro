#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtCore,QtGui

from omg.models.playlist import ExternalFile
from omg import strutils, tags, config
from . import abstractdelegate

STD_STYLE = abstractdelegate.DelegateStyle(11,False,False)
TITLE_STYLE = abstractdelegate.DelegateStyle(13,True,False)
ALBUM_STYLE = abstractdelegate.DelegateStyle(13,True,True)
EXTERNAL_FILE_STYLE = abstractdelegate.DelegateStyle(11,False,True)

class PlaylistDelegate(abstractdelegate.AbstractDelegate):
    def __init__(self,parent,model):
        abstractdelegate.AbstractDelegate.__init__(self,parent)
        self.model = model
    
    def layout(self,index):
        element = self.model.data(index)
        if isinstance(element,ExternalFile):
            self.addLine(element.getPath(),"",EXTERNAL_FILE_STYLE)
            return
        if element.isFile():
            if element.getPosition() is None:
                titleString = element.getTitle()
            else: titleString = "{0} - {1}".format(element.getPosition(),element.getTitle())
            self.addLine(titleString,strutils.formatLength(element.getLength()))
        else:
            # Get and format data
            if element.getPosition() is None:
                titleString = element.getTitle()
            else: titleString = "{0} - {1}".format(element.getPosition(),element.getTitle())
            
            if tags.ALBUM in element.tags and element.tags[tags.TITLE] != element.tags[tags.ALBUM]:
                albumString = " - ".join(element.tags[tags.ALBUM])
            else: albumString = None
            piecesString = "Stück" if element.getChildrenCount() == 1 else "Stücke"
            piecesString = "{0} {1}".format(element.getFileCount(),piecesString)
            genreString = ",".join(element.tags[tags.GENRE])
            dateString = ",".join(str(date) for date in element.tags[tags.DATE])
            lengthString = strutils.formatLength(element.getLength())
            
            coverSize = config.get("playlist","cover_size")
            self.drawCover(coverSize,element)
            
            self.addLine(titleString,"",TITLE_STYLE)
            if albumString is not None:
                self.addLine(albumString,"",ALBUM_STYLE)
            self.addLine(", ".join(element.tags[tags.COMPOSER]),", ".join(element.tags[tags.CONDUCTOR]))
            self.addLine(", ".join(element.tags[tags.ARTIST]),", ".join(element.tags[tags.PERFORMER]))
            self.addLine(piecesString,lengthString)
            self.addLine(", ".join(element.tags[tags.GENRE]),
                         ", ".join(strutils.formatDate(date) for date in element.tags[tags.DATE]))

    def getBackground(self,index):
        element = self.model.data(index)
        if self.model.isPlaying(element):
            return QtGui.QBrush(QtGui.QColor(110,149,229))
        else: return None