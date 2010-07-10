#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtCore,QtGui

from omg import strutils, tags, config, covers, models
from omg.models import playlist,browser
from . import abstractdelegate, formatter

# Styles used in the delegates
STD_STYLE = abstractdelegate.STD_STYLE
PL_TITLE_STYLE = abstractdelegate.DelegateStyle(13,True,False)
PL_ALBUM_STYLE = abstractdelegate.DelegateStyle(13,True,True)
PL_EXTERNAL_FILE_STYLE = abstractdelegate.DelegateStyle(11,False,True)
BR_TITLE_STYLE = abstractdelegate.DelegateStyle(11,True,False)
BR_ALBUM_STYLE = abstractdelegate.DelegateStyle(11,True,True)

class PlaylistDelegate(abstractdelegate.AbstractDelegate):
    """ItemDelegate used in the playlists"""
    def __init__(self,parent,model):
        abstractdelegate.AbstractDelegate.__init__(self,parent)
        self.model = model
    
    def layout(self,index):
        element = self.model.data(index)
        if isinstance(element,playlist.ExternalFile):
            self.addLine(element.getPath(),"",PL_EXTERNAL_FILE_STYLE)
            return
          
        f = formatter.Formatter(element)
        if element.isFile():
            
            # First find out whether the file has a cover (usually not...)
            if element.hasCover():
                self.drawCover(config.get("gui","small_cover_size"),element)
            
            if tags.ALBUM in element.tags and not element.isContainedInAlbum():
                # This is the complicated version: The element has an album but is not displayed within the album. So draw an album cover and display the album tags.
                if not element.hasCover(): # Do not draw a second cover (see above)
                    albumIds = element.getAlbumIds()
                    for albumId in albumIds:
                        cover = covers.getCover(albumId,config.get("gui","small_cover_size"))
                        if cover is not None:
                            self.drawCover(config.get("gui","small_cover_size"),None,cover)
                            break # Draw only one cover even if there are several albums
                self.addLine(f.titleWithPos(),f.length(),PL_TITLE_STYLE,STD_STYLE)
                self.addLine(f.album(),"",PL_ALBUM_STYLE)
            else:
                self.addLine(f.titleWithPos(),f.length())
            # Independent of the album problem above we list the artists which were not listed in parent containers.
            self.addLine(f.tag(tags.get("composer"),True),f.tag(tags.get("conductor"),True))
            self.addLine(f.tag(tags.get("artist"),True),f.tag(tags.get("performer"),True))
        else:
            coverSize = config.get("gui","large_cover_size")
            self.drawCover(coverSize,element)
            
            self.addLine(f.title(),"",PL_TITLE_STYLE)
            self.addLine(f.album(),"",PL_ALBUM_STYLE)
            self.addLine(f.tag(tags.get("composer"),True),f.tag(tags.get("conductor"),True))
            self.addLine(f.tag(tags.get("artist"),True),f.tag(tags.get("performer"),True))
            self.addLine(f.files(),f.length())
            self.addLine(f.tag(tags.get("genre")),f.tag(tags.DATE))

    def getBackground(self,index):
        element = self.model.data(index)
        if self.model.isPlaying(element):
            return QtGui.QBrush(QtGui.QColor(110,149,229))
        else: return None
        

class BrowserDelegate(abstractdelegate.AbstractDelegate):
    def __init__(self,parent,model):
        abstractdelegate.AbstractDelegate.__init__(self,parent)
        self.model = model
    
    def layout(self,index):
        node = self.model.data(index)
        
        if isinstance(node,browser.ValueNode):
            self.addLine(node.value,"")
        elif isinstance(node,browser.VariousNode):
            self.addLine("Unbekannt/Verschiedene","")
        elif isinstance(node,models.Element):
            element = node
            f = formatter.Formatter(element)
            if element.isFile():
                # First find out whether the file has a cover (usually not...)
                if element.hasCover():
                    self.drawCover(config.get("gui","browser_cover_size"),element)
                
                if tags.ALBUM in element.tags and not element.isContainedInAlbum():
                    # This is the complicated version: The element has an album but is not displayed within the album. So draw an album cover and display the album tags.
                    if not element.hasCover(): # Do not draw a second cover (see above)
                        albumIds = element.getAlbumIds()
                        for albumId in albumIds:
                            cover = covers.getCover(albumId,config.get("gui","browser_cover_size"))
                            if cover is not None:
                                self.drawCover(config.get("gui","browser_cover_size"),None,cover)
                                break # Draw only one cover even if there are several albums
                    self.addLine(f.title(),"",BR_TITLE_STYLE)
                    self.addLine(f.album(),"",BR_ALBUM_STYLE)
                else:
                    self.addLine(f.title(),"")
                # Independent of the album problem above we list the artists which were not listed in parent containers.
                self.addLine(f.tag(tags.get("composer"),True),"")
                self.addLine(f.tag(tags.get("artist"),True),"")
            else:
                coverSize = config.get("gui","browser_cover_size")
                self.drawCover(coverSize,element)
                
                self.addLine(f.title(),"",BR_TITLE_STYLE)
                self.addLine(f.album(),"",BR_ALBUM_STYLE)
                self.addLine(f.tag(tags.get("composer"),True),"")
                self.addLine(f.tag(tags.get("artist"),True),"")