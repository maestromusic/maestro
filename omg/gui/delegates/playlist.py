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
            flagIcons = self.prepareFlags(element)[0]
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
            
        # Columns
        leftTexts,rightTexts = self.prepareColumns(element)
        if len(leftTexts) > 0 or len(rightTexts) > 0:
            self.addCenter(MultiTextItem(leftTexts,rightTexts))
            self.newRow()
            
    
    @staticmethod
    def getDefaultDataPieces():
        left = [configuration.DataPiece(tags.get(name)) for name in ['album','composer','artist','performer']]
        right = [configuration.DataPiece(tags.get(name)) for name in ['date','genre','conductor']]
        return left,right


PlaylistDelegate.defaultConfig = configuration.DelegateConfiguration(
                                            translate("Delegates","Playlist"),PlaylistDelegate,builtin=True)
configuration.addDelegateConfiguration(PlaylistDelegate.defaultConfig)
