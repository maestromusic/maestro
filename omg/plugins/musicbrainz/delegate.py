# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtGui

from ...gui.delegates.abstractdelegate import *
from ...gui.delegates import StandardDelegate
from ...gui.delegates.profiles import DelegateProfile

from .elements import MBNode, Medium, Recording
from .xmlapi import AliasEntity

class MusicBrainzDelegate(StandardDelegate):

    def __init__(self, view):
        profile = DelegateProfile("musicbrainz")
        profile.leftData = ["artist", "barcode"]
        profile.rightData = ["date", "country"]
        profile.options['appendRemainingTags'] = True
        super().__init__(view, profile)
        
        ignoreColor = QtGui.qApp.palette().color(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText)
        self.ignoreBold = DelegateStyle(1, True, False, ignoreColor)
        self.ignoreItalic = DelegateStyle(1, False, True, ignoreColor)
        self.ignoreNormal = DelegateStyle(1, False, False, ignoreColor)
        self.tracknoStyle = DelegateStyle(1, True, False, Qt.darkGreen)
        self.aliasStyle = DelegateStyle(1, False, False, Qt.blue)
         
    def layout(self, index, availableWidth):
        node = self.model.data(index)
        if not isinstance(node, MBNode):
            return
        element = node.element        
        
        if element.ignore:
            bold = self.ignoreBold
            italic = self.ignoreItalic
            normal = self.ignoreNormal
        else:
            bold, italic, normal = BOLD_STYLE, ITALIC_STYLE, STD_STYLE
        # Title and type
        titleItem = TextItem(node.title(), bold)
        self.addCenter(titleItem)
        self.newRow()
        if isinstance(element, Recording) and hasattr(element, "tracknumber"):
            tracknoItem = TextItem("Track Nr. {}".format(element.tracknumber), self.tracknoStyle)
            self.addCenter(tracknoItem)
            self.newRow()
        typeText = element.__class__.__name__
        if isinstance(element, Medium):
            typeText += " (Disc IDs: {})".format("/".join(map(str, element.discids)))
        if element.mbid is not None:
            typeText += " (MBID: {})".format(element.mbid) 
        typeItem = TextItem(typeText, italic)
        self.addCenter(typeItem)
        self.newRow()
        leftTexts,rightTexts = self.prepareColumns(node)

        if len(leftTexts) > 0 or len(rightTexts) > 0:
            self.addCenter(MultiTextItem(leftTexts,rightTexts), normal)


    def prepareColumns(self, node):
        leftTexts = []
        rightTexts = []
        seenTags = ["title"]
        for texts, tags in ((leftTexts,self.profile.leftData),(rightTexts,self.profile.rightData)):
            seenTags.extend(tags)
            for tag in tags:
                if tag in node.element.tags:
                    text = '{}: {}'.format(tag, ", ".join(map(str, node.element.tags[tag])))
                    if len(text) > 0:
                        texts.append(text)
        

        remainingTagValues = {tag: ", ".join(map(str, node.element.tags[tag]))
                                for tag in node.element.tags if tag not in seenTags}
        leftTexts.extend('{}: {}'.format(tag, values)
                                for tag, values in remainingTagValues.items())
        return leftTexts,rightTexts