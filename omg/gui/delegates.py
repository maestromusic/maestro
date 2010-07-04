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
from . import abstractdelegate, formatter

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
          
        f = formatter.Formatter(element)
        if element.isFile():
            if tags.ALBUM in element.tags and not element.isContainedInAlbum():
                # This is the complicated version: The element has an album but is not displayed within the album. So draw an album cover an display the album tags.
                coverSize = config.get("gui","small_cover_size")
                albums = element.getAlbums()
                if len(albums) > 0:
                    self.drawCover(coverSize,albums[0])
                self.addLine(f.titleWithPos(),f.length(),TITLE_STYLE)
                self.addLine(f.album(),"",ALBUM_STYLE)
            else:
                self.addLine(f.titleWithPos(),f.length())
            # Independent of the album problem above we list the artists which were not listed in parent containers.
            self.addLine(f.tag(tags.COMPOSER,True),f.tag(tags.CONDUCTOR,True))
            self.addLine(f.tag(tags.ARTIST,True),f.tag(tags.PERFORMER,True))
        else:
            coverSize = config.get("gui","large_cover_size")
            self.drawCover(coverSize,element)
            
            self.addLine(f.title(),"",TITLE_STYLE)
            self.addLine(f.album(),"",ALBUM_STYLE)
            self.addLine(f.tag(tags.COMPOSER,True),f.tag(tags.CONDUCTOR,True))
            self.addLine(f.tag(tags.ARTIST,True),f.tag(tags.PERFORMER,True))
            self.addLine(f.files(),f.length())
            self.addLine(f.tag(tags.GENRE),f.tag(tags.DATE))

    def getBackground(self,index):
        element = self.model.data(index)
        if self.model.isPlaying(element):
            return QtGui.QBrush(QtGui.QColor(110,149,229))
        else: return None