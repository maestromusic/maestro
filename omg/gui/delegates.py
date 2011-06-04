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
import os.path

from .. import tags, covers, models, constants, config
from ..models import browser
from . import abstractdelegate, formatter

# Styles used in the delegates
STD_STYLE = abstractdelegate.STD_STYLE
BR_SPECIAL_NODE_STYLE = abstractdelegate.DelegateStyle(11,False,True)
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
          
        f = formatter.Formatter(element)
        if element.isFile():
            # First find out whether the file has a cover (usually not...)
            if element.hasCover():
                self.drawCover(options.gui.small_cover_size,element)
            
            if tags.ALBUM in element.tags and not element.isContainedInAlbum():
                # This is the complicated version: The element has an album but is not displayed within the album. So draw an album cover and display the album tags.
                if element.isInDB() and not element.hasCover(): # Do not draw a second cover (see above)
                    albumIds = element.getAlbumIds()
                    for albumId in albumIds:
                        cover = covers.getCover(albumId, options.gui.small_cover_size)
                        if cover is not None:
                            self.drawCover(options.gui.small_cover_size,None,cover)
                            break # Draw only one cover even if there are several albums
                self.addLine(f.titleWithPos(),f.length(),PL_TITLE_STYLE,STD_STYLE)
                self.addLine(f.album(),"",PL_ALBUM_STYLE)
            else:
                self.addLine(f.titleWithPos(),f.length())
            # Independent of the album problem above we list the artists which were not listed in parent containers.
            self.addLine(f.tag(tags.get("composer"),True),f.tag(tags.get("conductor"),True))
            self.addLine(f.tag(tags.get("artist"),True),f.tag(tags.get("performer"),True))
        else:
            coverSize = options.gui.large_cover_size
            self.drawCover(coverSize,element)
            
            self.addLine(f.titleWithPos(),"",PL_TITLE_STYLE)
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
            self.addLine(node.getDisplayValue(),"")
        elif isinstance(node,browser.VariousNode):
            self.addLine(self.tr("Unknown/Various"),style1=BR_SPECIAL_NODE_STYLE)
        elif isinstance(node,browser.HiddenValuesNode):
            self.addLine(self.tr("Hidden"),style1=BR_SPECIAL_NODE_STYLE)
        elif isinstance(node,browser.LoadingNode):
            self.addLine(self.tr("Loading..."),style1=BR_SPECIAL_NODE_STYLE)
        elif isinstance(node,models.Element):
            element = node
            if element.tags is None:
                element.loadTags()
            f = formatter.Formatter(element)
            if element.isFile():
                # First find out whether the file has a cover (usually not...)
                if element.hasCover():
                    self.drawCover(config.options.gui.browser_cover_size,element)
                
                self.addLine(f.title(),"")
#                if tags.ALBUM in element.tags and not element.isContainedInAlbum():
#                    # This is the complicated version: The element has an album but is not displayed within the album. So draw an album cover and display the album tags.
#                    if not element.hasCover(): # Do not draw a second cover (see above)
#                        albumIds = element.getAlbumIds()
#                        for albumId in albumIds:
#                            cover = covers.getCover(albumId, options.gui.browser_cover_size)
#                            if cover is not None:
#                                self.drawCover(options.gui.browser_cover_size, None, cover)
#                                break # Draw only one cover even if there are several albums
#                    self.addLine(f.title(),"",BR_TITLE_STYLE)
#                    self.addLine(f.album(),"",BR_ALBUM_STYLE)
#                else:
#                    self.addLine(f.title(),"")

                # Independent of the album problem above we list the artists which were not listed in parent containers.
                self.addLine(f.tag(tags.get("composer"),True,self._getTags),"")
                self.addLine(f.tag(tags.get("artist"),True,self._getTags),"")
            else:
                coverSize = config.options.gui.browser_cover_size
                self.drawCover(coverSize,element)
                
                self.addLine(f.title(),f.tag(tags.get("date")),BR_TITLE_STYLE)
                self.addLine(f.album(),"",BR_ALBUM_STYLE)
                self.addLine(f.tag(tags.get("composer"),True,self._getTags),"")
                self.addLine(f.tag(tags.get("artist"),True,self._getTags),"")

    def _getTags(self,node,tag):
        """Return a list with the tag-values of the given tag of <node>. This function is submitted to Formatter.tag."""
        if isinstance(node,models.Element):
            return node.tags[tag] if tag in node.tags else []
        elif isinstance(node,browser.ValueNode) and tag in node.valueIds:
            return [node.value]
        else: return []
        

def tagIcon(tag):
    """Given a tag, return the path of an appropriate icon, or None if none exists."""
    
    path = os.path.join(constants.IMAGES, "icons", "tag_{}.png".format(tag.name))
    if os.path.exists(path):
            return path
    return None

  
class GopulateDelegate(QtGui.QStyledItemDelegate):
    """A delegate useful for databaes manipulation. Shows lots of information."""
    
    hMargin = 2
    vMargin = 1
    vItemSpace = 4
    hItemSpace = 4
    
    def __init__(self, parent = None):
        QtGui.QStyledItemDelegate.__init__(self,parent)
        self.iconSize = options.gui.iconsize
        self.iconRect = QtCore.QRect(0, 0, self.iconSize, self.iconSize)
        self.font = QtGui.QFont()
        self.fileNameFont = QtGui.QFont()
        self.fileNameFont.setPointSize(7)
        
        self.titleFont = QtGui.QFont()
        self.titleFont.setItalic(True)
        
        self.albumFont = QtGui.QFont()
        self.albumFont.setBold(True)
        self.albumFont.setItalic(True)
        
        self.positionFont = QtGui.QFont()
        self.positionFont.setBold(True)
    
    def formatTagValues(self, values):
        return " • ".join((str(x) for x in values))
    
    def paint(self,painter,option,index):
        """Reimplemented function from QStyledItemDelegate"""
        if not isinstance(index.internalPointer(), models.Element):
            return QtGui.QStyledItemDelegate.paint(self, painter, option, index)
        else:
            return self.layout(painter, option, index)
        
    def layout(self, painter, option, index):
        """This is the central function of the delegate for painting and size calculation.
        
        If painter is None, only the size hint is calculated and returned. Otherwise, everything
        is painted with the given painter object."""
        
        elem = index.internalPointer()
        self.elem = elem
        
        # —————— initialize painter ——————
        if painter:
            painter.save()
            QtGui.QApplication.style().drawControl(QtGui.QStyle.CE_ItemViewItem,option,painter)
            option = QtGui.QStyleOptionViewItemV4(option)
            rect = QtCore.QRect(0,0,option.rect.width()-2*self.hMargin,option.rect.height()-2*self.vMargin)
            # Paint data
            painter.translate(option.rect.left()+self.hMargin,option.rect.top()+self.vMargin)
            
#            if not elem.isInDB():
#                painter.setOpacity(0.6) # visualize non-db items by transparency
            
        else:
                width = 0
                height = 0

        # ——————— calculate space for position number and color marker ———————
        if elem.getPosition() is not None:
            positionSize = QtGui.QFontMetrics(self.positionFont).size(Qt.TextSingleLine, str(elem.getPosition()))
            tagRenderStartX = positionSize.width() + 2*self.hItemSpace
        else: # no space for position needed if it is None, only a small margin for the color indicator
            tagRenderStartX = 2*self.hItemSpace
        if painter:
            rect.setLeft(rect.left() + tagRenderStartX)

        # ——————— paint/calculate the title ———————

        if tags.TITLE in elem.tags:
            titleToDraw = self.formatTagValues(elem.tags[tags.TITLE])
        else:
            titleToDraw = "<notitle>"
        if elem.isInDB() and options.misc.show_ids:
            titleToDraw += " [{}]".format(elem.id) # print container ID for debugging purposes
        
        if elem.isContainer():
            font = self.albumFont
        else:
            font = self.titleFont
        if painter:
            painter.setFont(font)
            boundingRect = painter.drawText(rect, Qt.TextSingleLine, titleToDraw)
            rect.translate(0, boundingRect.height() + self.vItemSpace)
            painter.setFont(self.font)
        else:
            fSize = QtGui.QFontMetrics(font).size(Qt.TextSingleLine, titleToDraw)
            width = max(width, fSize.width())
            height += fSize.height() + self.vItemSpace
        
        # ——————— now, paint/calculate all other tags ———————
        for t in (t for t in tags.tagList if t in elem.tags):
            data = elem.tags[t]
            if t == tags.TITLE or (t == tags.ALBUM and elem.isAlbum()):
                continue
            if isinstance(elem.parent, models.Element) and t in elem.parent.tags and data == elem.parent.tags[t]:
                continue
            
            iconPath = tagIcon(t)
            if iconPath:
                if painter:
                    img = QtGui.QImage(iconPath)
                    painter.drawImage(rect.topLeft(), img.scaled(self.iconRect.size()))
                    rect.setLeft(rect.left()+ self.iconSize + self.vItemSpace)
                else:
                    widthSoFar = self.iconSize + self.hItemSpace
            else:
                if painter:
                    boundingRect = painter.drawText(rect, Qt.TextSingleLine, "{}: ".format(t.name))
                    rect.setLeft(rect.left() + boundingRect.width() + self.hItemSpace)
                else:
                    fSize = QtGui.QFontMetrics(self.font).size(Qt.TextSingleLine, "{}: ".format(t.name))
                    widthSoFar = fSize.width() + self.hItemSpace
            if painter:
                painter.drawText(rect, Qt.TextSingleLine, self.formatTagValues(data))
                rect.translate(0, self.iconSize + self.vItemSpace)
                rect.setLeft(tagRenderStartX)
            else:
                fSize = QtGui.QFontMetrics(self.font).size(Qt.TextSingleLine, self.formatTagValues(data))
                width = max(width, fSize.width() + widthSoFar + self.hItemSpace)
                height += self.iconSize + self.vItemSpace
        
        # ——————— paint filename, if file ———————
        if elem.isFile():
            if painter:
                painter.setFont(self.fileNameFont)
                boundingRect = painter.drawText(rect, Qt.TextSingleLine, elem.getPath())
                rect.translate(0, boundingRect.height() + self.vItemSpace)
            else:
                fSize = QtGui.QFontMetrics(self.font).size(Qt.TextSingleLine, relPath(elem.getPath()))
                width = max(width, fSize.width())
                height += fSize.height()
        # ——————— paint the element position and color marker ————————
        if painter:
            if elem.outOfSync():
                painter.setPen(Qt.red)
            if not elem.isInDB():
                painter.fillRect(0, 0, tagRenderStartX, rect.height(), Qt.yellow)
            if elem.getPosition() is not None:
                painter.setFont(self.positionFont)
                rect.setLeft(int((tagRenderStartX-positionSize.width())/2))
                rect.setTop(int((rect.height() -positionSize.height())/2))        
                painter.drawText(rect, Qt.TextSingleLine, str(elem.getPosition()))
            else:
                if elem.outOfSync():
                    painter.fillRect(0, 0, tagRenderStartX, rect.height()//4, Qt.red)
            painter.setPen(Qt.black)
            painter.restore()
        else:
            return QtCore.QSize(width + tagRenderStartX + 2*self.hMargin, height+2*self.vMargin)
    
    def sizeHint(self, option, index):
        """Reimplemented function from QStyledItemDelegate"""
        
        if not isinstance(index.internalPointer(), models.Element):
            return QtGui.QStyledItemDelegate.sizeHint(self, option, index)
        else:
            size = self.layout(None, option, index)
            return size
