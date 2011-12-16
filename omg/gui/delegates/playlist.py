# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ... import tags, config, models
from . import *

translate = QtCore.QCoreApplication.translate


class PlaylistDelegate(AbstractDelegate):
    """Delegate for the playlist."""
    
    options = configuration.copyOptions(AbstractDelegate.options)
    
    def background(self, index):
        if index == self.model.currentModelIndex:
            return QtGui.QBrush(QtGui.QColor(110,149,229))
        elif index in self.model.currentParentsModelIndices:
            return QtGui.QBrush(QtGui.QColor(140,179,255))    
        
    def layout(self,index,availableWidth):
        element = self.model.data(index)
        
        # Prepare data
        if element.tags is None:
            element.loadTags()
        if element.flags is None:
            element.loadFlags()
            
        # Cover
        if element.hasCover():
            coverSize = self.config.options['coverSize'].value
            self.addLeft(CoverItem(element.getCover(coverSize),coverSize))
        
        # Flag-Icons
        if self.config.options['showFlagIcons'].value:
            flagIcons = self.getFlagIcons(element)
            if len(flagIcons) > 0:
                self.addRight(IconBarItem(flagIcons,columns=2 if len(flagIcons) > 2 else 1))

        # Title and Major
        titleItem = TextItem(element.getTitle(prependPosition=self.config.options['showPositions'].value,
                                                usePath=not self.config.options['showPaths'].value),
                             BOLD_STYLE if element.isContainer() else STD_STYLE)
        
        if self.config.options['showMajor'].value and element.isContainer() and element.major:
            self.addCenter(ColorBarItem(QtGui.QColor(255,0,0),5,titleItem.sizeHint(self)[1]))
        self.addCenter(titleItem)
        
        self.newRow()
        
        # Path
        if self.config.options['showPaths'].value and element.isFile():
            self.addCenter(TextItem(element.path,ITALIC_STYLE))
            self.newRow()
            
        # Tags
        leftTexts,rightTexts = self.prepareTags(element)
        if len(leftTexts) > 0 or len(rightTexts) > 0:
            self.addCenter(MultiTextItem(leftTexts,rightTexts))
            self.newRow()
            
    def prepareTags(self,element):
        leftTexts = []
        rightTexts = []
        for dataPiece in self.config.leftData:
            if dataPiece.tag is not None:
                tag = dataPiece.tag
                values = self.getTagValues(tag,element)
                if len(values) > 0:
                    separator = ' - ' if tag == tags.TITLE or tag == tags.ALBUM else ', '
                    leftTexts.append(separator.join(str(v) for v in values))
        for dataPiece in self.config.rightData:
            if dataPiece.tag is not None:
                tag = dataPiece.tag
                values = self.getTagValues(tag,element)
                if len(values) > 0:
                    separator = ' - ' if tag == tags.TITLE or tag == tags.ALBUM else ', '
                    rightTexts.append(separator.join(str(v) for v in values))
            
        return leftTexts,rightTexts
    
    def prepareTagValues(self,element,theTags,tag,addTagName=False,alignRight=False):
        separator = ' - ' if tag == tags.TITLE or tag == tags.ALBUM else ', '
        strings = [str(v) for v in theTags[tag]]
        if addTagName:
            return '{}: {}'.format(tag.translated(),separator.join(strings))
        else: return separator.join(strings)

    def getTagValues(self,tagType,element):
        """Return all values of the tag *tagType* in *element* excluding values that appear in parent nodes.
        Values from ValueNode-ancestors will also be removed."""
        if tagType not in element.tags:
            return []
        values = list(element.tags[tagType]) # copy!
        
        parent = element
        while len(values) > 0:
            parent = parent.parent
            if isinstance(parent,models.RootNode):
                break
        
            if parent.tags is None:
                parent.loadTags()
            if tagType in parent.tags:
                parentValues = parent.tags[tagType]
            else: parentValues = []
            
            for value in parentValues:
                if value in values:
                    values.remove(value)
        
        return values
    
    def getFlagIcons(self,element):
        """Return flag icons that should be displayed for *element*. All flags contained in at least one
        parent node will be removed from the result."""
        flags = [flag for flag in element.flags if flag.icon is not None]
        parent = element.parent
        while parent is not None:
            if isinstance(parent,models.RootNode):
                break
            if parent.flags is None:
                parent.loadFlags()
            for flag in parent.flags:
                if flag.icon is not None and flag in flags:
                    flags.remove(flag)
            parent = parent.parent
        return [flag.icon for flag in flags]
    
    @staticmethod
    def getDefaultDataPieces():
        left = [configuration.DataPiece(tags.get(name)) for name in ['album','composer','artist','performer']]
        right = [configuration.DataPiece(tags.get(name)) for name in ['date','genre','conductor']]
        return left,right


PlaylistDelegate.defaultConfig = configuration.DelegateConfiguration(
                                            translate("Delegates","Playlist"),PlaylistDelegate,builtin=True)
configuration.addDelegateConfiguration(PlaylistDelegate.defaultConfig)
