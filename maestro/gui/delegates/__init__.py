# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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

import math

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt

from maestro.gui.delegates.abstractdelegate import *
from maestro import utils
from maestro.core import tags, levels
from maestro.core.nodes import RootNode, Wrapper, TextNode
from maestro.gui.delegates import profiles

translate = QtCore.QCoreApplication.translate


def init():
    from maestro.gui.delegates import abstractdelegate, profiles
    abstractdelegate.init()
    profiles.init()
    from maestro.gui.delegates import browser, editor
    browser.init()
    editor.init()


class StandardDelegate(AbstractDelegate):
    """While still abstract, this class implements almost all of the features used by the usual delegates in
    Maestro. In fact, subclasses like BrowserDelegate and EditorDelegate mainly provide different default
    values for these options."""
    
    def layout(self,index,availableWidth):
        node = index.model().data(index)
        if isinstance(node, TextNode):
            if node.wordWrap:
                self.addCenter(MultiTextItem([node.text],[]))
            else: self.addCenter(TextItem(node.text))
        if not isinstance(node, Wrapper):
            return
        
        wrapper = node
        element = wrapper.element
       
        # These can only be computed when we know whether fitting the fitInTitleRowData did work
        leftTexts,rightTexts = None,None
        
        flagIcons = self.prepareFlags(wrapper)[0]
                
        # Ancestors
        if self.profile.options['showAllAncestors'] or self.profile.options['showMajorAncestors']:
            ancestorsInTree = [w.element.id for w in wrapper.getParents() if isinstance(w,Wrapper)]
            ancestors = []
            ancestorIds = []
            self.appendAncestors(element, ancestors, ancestorIds, ancestorsInTree,
                                 onlyMajor=not self.profile.options['showAllAncestors'])
            
            for ancestor in reversed(ancestors):
                if element.id in ancestor.contents: # direct parent
                    pos = ancestor.contents.positionOf(element.id)
                    text = translate("Delegates","#{} in {}").format(pos,ancestor.getTitle())
                else: text = translate("Delegates","In {}").format(ancestor.getTitle())
                self.addCenter(TextItem(text,ITALIC_STYLE))
                self.newRow()
            
        # Cover
        coverSize = self.profile.options['coverSize']
        cover = element.getCover(coverSize)
        if cover is not None:
            self.addLeft(ImageItem(cover))
            availableWidth -= coverSize + self.hSpace
        
        # Title and type
        preTitleItem = self.getPreTitleItem(wrapper)
        if preTitleItem is not None:
            self.addCenter(preTitleItem)
        urlWarningItem = self.getUrlWarningItem(wrapper)
        titleItem = TextItem(wrapper.getTitle(prependPosition=self.profile.options['showPositions'],
                                           usePath=False),
                             STD_STYLE if isinstance(wrapper.parent, Wrapper) else BOLD_STYLE,
                             minHeight=IconBarItem.iconSize if len(flagIcons) > 0 else 0)
        
        if not element.isInDb():
            self.addCenter(ColorBarItem(QtGui.QColor(255,255,0), 5, titleItem.sizeHint(self)[1]))
        if urlWarningItem is not None:
            self.addCenter(urlWarningItem)
        if self.profile.options['showType'] and element.isContainer():
            pixmap = element.type.pixmap(size=16)
            if pixmap is not None:
                self.addCenter(ImageItem(pixmap))
        self.addCenter(titleItem)
        
        # showInTitleRow
        fitInTitleRowData = self.profile.options['fitInTitleRowData']
        if fitInTitleRowData is not None:
            fitInTitleRowText = self.getData(fitInTitleRowData,wrapper)
        else: fitInTitleRowText = None
        fittedTextInTitleRow = False
                
        # Flags
        # Here starts the mess...depending on the available space we want to put flags and if possible
        # even the fitInTitleRowTag into the title row.
        if len(flagIcons) > 0 and self.profile.options['showFlagIcons']:
            flagIconsItem = IconBarItem(flagIcons)
            titleLength = sum(item.sizeHint(self)[0] for item,align in self.center[0])
            maxFlagsInTitleRow = flagIconsItem.maxColumnsIn(availableWidth - titleLength - self.hSpace)
            if maxFlagsInTitleRow >= len(flagIcons):
                # Yeah, all flags fit into the title row
                self.addCenter(flagIconsItem,align=Qt.AlignRight)
                # Now we even try to fit the fitInTitleRowText
                if fitInTitleRowText is not None:
                    remainingWidth = availableWidth - titleLength \
                                     - flagIconsItem.sizeHint(self)[0] - 2* self.hSpace
                    if self.getFontMetrics().width(fitInTitleRowText) <= remainingWidth:
                        self.addCenter(TextItem(fitInTitleRowText),align=Qt.AlignRight)
                        fittedTextInTitleRow = True
                self.newRow()
            else:
                self.newRow() # We'll put the flags either into right region or into a new row
                
                # Now we have an optimization problem: We want to minimize the rows, but the less rows
                # we allow, the more columns we need. More columns means less space for tags in the
                # center region and thus potentially a lot rows.
                
                # In any case we are not going to fit the fitInTitleRowTag, so we can compute the texts:
                leftTexts,rightTexts = self.prepareColumns(wrapper)

                # First we compute a lower bound of the rows used by the tags
                rowsForSure = max(len(leftTexts), len(rightTexts))
                
                if rowsForSure == 0:
                    # No tags
                    if 2*maxFlagsInTitleRow >= len(flagIcons):
                        flagIconsItem.rows = 2
                        self.addRight(flagIconsItem)
                    else: self.addCenter(flagIconsItem,align=Qt.AlignRight)
                else:
                    # Do not use too many columns
                    maxFlagsInTitleRow = min(2,maxFlagsInTitleRow)
                    if maxFlagsInTitleRow == 0:
                        # Put all flags on the right side of the tags
                        flagIconsItem.columns = 1 if len(flagIcons) <= rowsForSure else 2
                        self.addCenter(flagIconsItem,align=Qt.AlignRight)
                    elif maxFlagsInTitleRow == 2:
                        # Also use the title row
                        flagIconsItem.columns = 1 if len(flagIcons) <= rowsForSure+1 else 2
                        self.addRight(flagIconsItem)
                    else:
                        # What's better? To use the title row (1 column) or not (2 columns)?
                        # Compare the number of additional rows we would need.
                        # Actually >= holds always, but in case of equality the first option is better
                        # (less columns).
                        if len(flagIcons)-1 <= math.ceil(len(flagIcons) / 2):
                            flagIconsItem.columns = 1
                            self.addRight(flagIconsItem)
                        else:
                            flagIconsItem.columns = 2
                            self.addCenter(flagIconsItem,align=Qt.AlignRight)
        else: 
            # This means len(flagIcons) == 0
            # Try to fit fitInTitleRowText
            if fitInTitleRowText is not None:
                titleLength = titleItem.sizeHint(self)[0]
                if (self.getFontMetrics().width(fitInTitleRowText)
                            <= availableWidth - titleLength - self.hSpace):
                    self.addCenter(TextItem(fitInTitleRowText),align=Qt.AlignRight)
                    fittedTextInTitleRow = True
            self.newRow()
        
        # Tags
        if leftTexts is None: # Tags may have been computed already above 
            leftTexts,rightTexts = self.prepareColumns(
                                    wrapper,exclude=[fitInTitleRowData] if fittedTextInTitleRow else [])

        if len(leftTexts) > 0 or len(rightTexts) > 0:
            self.addCenter(MultiTextItem(leftTexts,rightTexts))
            #if len(leftTexts) > 0:
             #   titleItem.style = BOLD_STYLE
        
        # Path
        self.addPath(element)
        
    def addPath(self, element):
        """Add the path of *element* to the DelegateItems. Subclasses may overwrite this method to use e.g.
        two items for an old and a new path.""" 
        if self.profile.options['showPaths'] and element.isFile():
            self.newRow()
            self.addCenter(TextItem(element.url.path if hasattr(element.url, 'path') else str(element.url),
                           ITALIC_STYLE))
        
    def appendAncestors(self, element, ancestors, ancestorIds, filter, onlyMajor):
        """Recursively add all ancestors of *element* to the list *ancestors* and their ids to the list
        *ancestorIds*. Do not add elements if their id is already contained in *ancestorIds* or if their
        id is in the list *filter*. If *onlyMajor* is True, add only major containers.
        """
        for id in element.parents:
            if id in ancestorIds or id in filter: 
                # Do not search for ancestors recursively because we did so already.
                # (this is clear if id in ancestorIds, otherwise we did so when painting the corresponding
                # wrapper in the current tree structure)
                continue
            try:
                ancestor = element.level.fetch(id)
            except levels.ElementGetError: # this may happen if the parent has just been deleted
                continue
            if not onlyMajor or ancestor.type.major:
                ancestorIds.append(id)
                ancestors.append(ancestor)
            # Search for ancestors recursively even if the current ancestor is not major. It might have
            # a major parent.
            self.appendAncestors(ancestor, ancestors, ancestorIds, filter, onlyMajor)
    
    def prepareColumns(self,wrapper,exclude=[]):
        """Collect the texts displayed in both columns based on the configured datapieces. Exclude datapieces
        contained in *exclude* (this is used if a datapiece is displayed in the title row)."""
        leftTexts = []
        rightTexts = []
        appendRemainingTags = self.profile.options['appendRemainingTags']
        if appendRemainingTags:
            seenTags = [tags.TITLE]
        for texts,dataPieces in ((leftTexts,self.profile.leftData),(rightTexts,self.profile.rightData)):
            if appendRemainingTags:
                seenTags.extend(data.tag for data in dataPieces if data.tag is not None)
            for data in dataPieces:
                if data not in exclude:
                    text = self.getData(data,wrapper)
                    if len(text) > 0:
                        texts.append(text)
        
        if appendRemainingTags:
            remainingTagValues = {tag: self.getFormattedTagValues(tag,wrapper)
                                    for tag in wrapper.element.tags if tag not in seenTags}
            leftTexts.extend('{}: {}'.format(tag.title,values)
                                    for tag,values in remainingTagValues.items() if values != '')
            
        return leftTexts,rightTexts

    def getData(self,dataPiece,wrapper):
        """Return the data for the given datapiece and wrapper as a string. Return an empty string if no
        data is available."""
        if dataPiece.tag is not None:
            return self.getFormattedTagValues(dataPiece.tag,wrapper)
        else:
            if dataPiece.data == "filetype":
                ext = wrapper.getExtension()
                # Do not display extensions in each file if they are the same for the whole container
                if isinstance(wrapper.parent, Wrapper) and wrapper.parent.getExtension() == ext:
                    return ''
                else: return ext
            elif dataPiece.data == "length":
                length = wrapper.getLength()
                if length is not None:
                    return utils.strings.formatLength(length)
                else: return ''
            elif dataPiece.data == "filecount":
                if wrapper.isFile():
                    return '' # Do not display a '1' at every file
                else: return translate("AbstractDelegate","%n piece(s)", n=wrapper.fileCount())
            elif dataPiece.data == "filecount+length":
                fileCount = self.getData(profiles.DataPiece("filecount"),wrapper)
                length = self.getData(profiles.DataPiece("length"),wrapper)
                return _join(', ',[fileCount,length])

    def getFormattedTagValues(self,tagType,wrapper):
        """Return all values of the tag *tagType* in *element*, excluding values that appear in parent nodes,
        nicely formatted as a string. Return an empty strings if *element* does not have values of that tag.
        """
        values = self.getTagValues(tagType,wrapper)
        separator = ' - ' if tagType == tags.TITLE or tagType == tags.ALBUM else ', '
        if tagType.type == tags.TYPE_DATE:
            values = map(str,values)
        return separator.join(values)
        
    def getTagValues(self,tagType,wrapper):
        """Return all values of the tag *tagType* in *element* excluding values that appear in parent nodes.
        Values from TagNode-ancestors will also be removed."""
        if tagType not in wrapper.element.tags:
            return []
        values = list(wrapper.element.tags[tagType]) # copy!
        
        from maestro.widgets import browser
        parent = wrapper
        while len(values) > 0:
            parent = parent.parent
            if isinstance(parent,Wrapper):
                if tagType in parent.element.tags:
                    parentValues = parent.element.tags[tagType]
                else: parentValues = []
            elif isinstance(parent,RootNode):
                break
            elif isinstance(parent, browser.nodes.TagNode):
                parentValues = parent.getValues()
            else:
                parentValues = []
            
            for value in parentValues:
                if value in values:
                    values.remove(value)
        
        return values
        
    def prepareFlags(self,wrapper):
        """Return two lists containing the flags of *element*: The first list contains the icons of the flags
        that have one, the second list contains the names of those flags that do not have an icon.
        
        If the ''removeParentFlags'' option is True, flags that are set in an ancestor are removed.
        """
        if self.profile.options['removeParentFlags']:
            flags = list(wrapper.element.flags) # copy!
            parent = wrapper.parent
            while parent is not None:
                if isinstance(parent,Wrapper):
                    for flag in parent.element.flags:
                        if flag in flags:
                            flags.remove(flag)
                parent = parent.parent
        else:
            flags = wrapper.element.flags
        return [flag.icon for flag in flags if flag.icon is not None],\
               [flag.name for flag in flags if flag.icon is None]
               
    def getPreTitleItem(self,wrapper):
        """Return a DelegateItem that should be placed in front of the title (which is not always in the
        first line. This is used by PlaylistDelegate to add a small triangle in front of the currently
        playing element."""
        return None
    
    def getUrlWarningItem(self, wrapper):
        """An optional string to place before the title for unusual URL types.
        
        The default is to display nothing for "file" URLs and the scheme (bold and red) for any
        other scheme.
        """
        element = wrapper.element
        if element.isFile() and element.url.scheme != "file":
            return TextItem(element.url.scheme, DelegateStyle(bold=True, color=Qt.red))
            
            
def _join(sep, strings):
    """Join *strings* using *sep* but removing empty strings."""
    return sep.join(s for s in strings if len(s) > 0)
