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


class EditorDelegate(AbstractDelegate):
    """Delegate for the editor."""
    options = configuration.copyOptions(AbstractDelegate.options)
    options['showPaths'].value = True
    options['showMajor'].value = True
        
    blackFormat = QtGui.QTextCharFormat()
    blackFormat.setFontPointSize(8)
    redFormat = QtGui.QTextCharFormat()
    redFormat.setFontPointSize(8)
    redFormat.setForeground(QtGui.QBrush(QtGui.QColor(255,0,0)))
    
    removeParentFlags = True
            
    def layout(self,index,availableWidth):
        element = self.model.data(index)
        
        # Prepare data
        if element.tags is None:
            element.loadTags()
        if element.flags is None:
            element.loadFlags()

        # In DB
        if not element.isInDB():
            self.addLeft(ColorBarItem(QtGui.QColor("yellow"),10))
            
        # Cover
        if element.hasCover():
            coverSize = self.config.options['coverSize'].value
            self.addLeft(CoverItem(element.getCover(coverSize),coverSize))
        
        # Flag-Icons
        flagIcons,flagsWithoutIcon = self.getFlags(element)
        if self.config.options['showFlagIcons'].value and len(flagIcons) > 0:
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
#            doc = QtGui.QTextDocument()
#            cursor = QtGui.QTextCursor(doc)
#            cursor.insertTable(max(len(leftTexts),len(rightTexts)),2)
#            for leftText,rightText in itertools.zip_longest(leftTexts,rightTexts,fillvalue=''):
#                cursor.insertText(leftText)
#                cursor.movePosition(QtGui.QTextCursor.NextCell)
#                cursor.insertText(rightText)
#                cursor.movePosition(QtGui.QTextCursor.NextCell)
#            self.addCenter(RichTextItem(doc))
            self.newRow()
            
        # Flags without icon
        if len(flagsWithoutIcon) > 0:
            self.addCenter(TextItem(', '.join(flagsWithoutIcon)))
            
    def prepareTags(self,element):
        theTags = self.getTags(element)
        leftTexts = []
        rightTexts = []
        for dataPiece in self.config.leftData:
            if dataPiece.tag is not None:
                tag = dataPiece.tag
                if tag in theTags:
                    leftTexts.append(self.prepareTagValues(element,theTags,tag))
                    del theTags[tag]
        for dataPiece in self.config.rightData:
            if dataPiece.tag is not None:
                tag = dataPiece.tag
                if tag in theTags:
                    rightTexts.append(self.prepareTagValues(element,theTags,tag,alignRight=True))
                    del theTags[tag]
        for tag in theTags:
            if tag != tags.TITLE:
                leftTexts.append(self.prepareTagValues(element,theTags,tag,addTagName=True))
            
        return leftTexts,rightTexts
    
    def prepareTagValues(self,element,theTags,tag,addTagName=False,alignRight=False):
        separator = ' - ' if tag == tags.TITLE or tag == tags.ALBUM else ', '
#        if hasattr(element,'missingTags') and tag in element.missingTags \
#                and any(v in element.missingTags[tag] for v in theTags[tag]):
#            doc = QtGui.QTextDocument()
#            doc.setDocumentMargin(0)
#            cursor = QtGui.QTextCursor(doc)
#            if alignRight:
#                format = QtGui.QTextBlockFormat()
#                format.setAlignment(Qt.AlignRight)
#                cursor.setBlockFormat(format)
#            if addTagName:
#                cursor.insertText('{}: '.format(tag.translated()),self.blackFormat)
#            for i,value in enumerate(theTags[tag]):
#                if value in element.missingTags[tag]:
#                    cursor.insertText(str(value),self.redFormat)
#                else: cursor.insertText(str(value),self.blackFormat)
#                if i != len(theTags[tag]) - 1:
#                    cursor.insertText(separator)
#            return doc
#        else: 
        strings = [str(v) for v in theTags[tag]]
        if addTagName:
            return '{}: {}'.format(tag.translated(),separator.join(strings))
        else: return separator.join(strings)
    
    def getTags(self,element):
        theTags = element.tags.copy()
        parent = element.parent

        while parent is not None and not isinstance(parent,models.RootNode):
            # Be careful to iterate over the parent's tags because theTags might change
            for tag in parent.tags:
                if tag not in theTags:
#                    for value in parent.tags[tag]:
#                        self.addMissing(parent,tag,value)
                    continue
                if hasattr(parent,'missingTags') and tag in parent.missingTags:
                    missing = parent.missingTags[tag]
                else: missing = []
                for value in parent.tags[tag]:
                    if tag in theTags and value in theTags[tag]: # tag may be removed from theTags
                        if value not in missing:
                            theTags[tag].remove(value)
#                    else:
#                        self.addMissing(parent,tag,value)            
            parent = parent.parent
            
        return theTags
    
#    def addMissing(self,element,tag,value):
#        if not hasattr(element,'missingTags'):
#            element.missingTags = tags.Storage()
#        if tag not in element.missingTags:
#            element.missingTags[tag] = [value]
#        elif value not in element.missingTags[tag]:
#            element.missingTags[tag].append(value)
            
    def getFlags(self,element):
        """Return two lists containing the flags of *element*: The first list contains the icons of the flags
        that have one, the second list contains the names of those flags that do not have an icon.
        
        If the ''removeParentFlags'' option is True, flags that are set in an ancestor are removed.
        """
        if self.removeParentFlags:
            flags = list(element.flags) # copy!
            parent = element.parent
            while parent is not None:
                if isinstance(parent,models.Element):
                    for flag in parent.flags:
                        if flag in flags:
                            flags.remove(flag)
                parent = parent.parent
        else:
            flags = element.flags
        return [flag.icon for flag in flags if flag.icon is not None],\
               [flag.name for flag in flags if flag.icon is None]
    
    @staticmethod
    def getDefaultDataPieces():
        left = [configuration.DataPiece(tags.get(name)) for name in ['album','composer','artist','performer']]
        right = [configuration.DataPiece(tags.get(name)) for name in ['date','genre','conductor']]
        return left,right


EditorDelegate.defaultConfig = configuration.DelegateConfiguration(
                                                translate("Delegates","Editor"),EditorDelegate,builtin=True)
configuration.addDelegateConfiguration(EditorDelegate.defaultConfig)
