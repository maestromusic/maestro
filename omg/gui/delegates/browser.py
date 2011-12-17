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
from ...models import browser as browsermodel


translate = QtCore.QCoreApplication.translate


class BrowserDelegate(AbstractDelegate):
    """Delegate used in the Browser. Does some effort to put flag icons at the optimal place using free space
    in the title row and trying not to increase the overall number of rows.
    """
    options = configuration.copyOptions(AbstractDelegate.options)
    options["fitInTitleRowTag"] = configuration.DelegateOption(    
                                "fitInTitleRowTag",
                                translate("Delegates","This tag is put into the title "
                                                      "row if it fits (mostly used for date tags)"),"tag",
                                tags.get("date") if tags.exists("date") else None)
    options["showSortValues"] = configuration.DelegateOption("showSortValues",
                            translate("Delegates","Display sort values instead of real values"),"bool",False)

    def __init__(self,view,delegateConfig):
        super().__init__(view,delegateConfig)
        
    def layout(self,index,availableWidth):
        node = self.model.data(index)
        
        if isinstance(node,browsermodel.ValueNode):
            valueList = node.sortValues if self.config.options['showSortValues'].value else node.values
            for value in valueList:
                self.addCenter(TextItem(value))
                self.newRow()
        elif isinstance(node,browsermodel.VariousNode):
            self.addCenter(TextItem(self.tr("Unknown/Various"),ITALIC_STYLE))
        elif isinstance(node,browsermodel.HiddenValuesNode):
            self.addCenter(TextItem(self.tr("Hidden"),ITALIC_STYLE))
        elif isinstance(node,browsermodel.LoadingNode):
            self.addCenter(TextItem(self.tr("Loading..."),ITALIC_STYLE))
        elif isinstance(node,models.Element):
            # Prepare data
            if node.tags is None:
                node.loadTags()
            # These can only be computed when we know whether fitting the fitInTitleRowTag did work
            leftTexts,rightTexts = None,None
            
            if node.flags is None:
                node.loadFlags()
            flagIcons = self.prepareFlags(node)[0]
            
            if node.isContainer() and node.major is None:
                node.major = db.isMajor(node.id)
            
            # Cover
            if node.hasCover():
                coverSize = self.config.options['coverSize'].value
                self.addLeft(CoverItem(node.getCover(coverSize),coverSize))
                availableWidth -= coverSize + self.hSpace
            
            # Title and Major
            titleItem = TextItem(node.getTitle(prependPosition=self.config.options['showPositions'].value,
                                               usePath=False),
                                 BOLD_STYLE if node.isContainer() else STD_STYLE,
                                 minHeight=IconBarItem.iconSize if len(flagIcons) > 0 else 0)
            
            if self.config.options['showMajor'].value and isinstance(node,models.Container) and node.major:
                self.addCenter(ColorBarItem(QtGui.QColor(255,0,0),5,titleItem.sizeHint(self)[1]))
            self.addCenter(titleItem)
            
            # FitInTitleRowTag
            fitInTitleRowTag = self.config.options['fitInTitleRowTag'].value
            if fitInTitleRowTag is not None and fitInTitleRowTag in node.tags:
                fitInTitleRowText = ', '.join(str(v) for v in self.getTagValues(fitInTitleRowTag,node))
            else: fitInTitleRowText = None
            fittedTextInTitleRow = False
                    
            # Flags
            # Here starts the mess...depending on the available space we want to put flags and if possible
            # even the fitInTitleRowTag into the title row.
            if len(flagIcons) > 0 and self.config.options['showFlagIcons'].value:
                flagIconsItem = IconBarItem(flagIcons)
                titleLength = sum(item.sizeHint(self)[0] for item,align in self.center[0])
                maxFlagsInTitleRow = flagIconsItem.maxColumnsIn(availableWidth - titleLength - self.hSpace)
                if maxFlagsInTitleRow >= len(flagIcons):
                    # Yeah, all flags fit into the title row
                    self.addCenter(flagIconsItem,align=RIGHT)
                    # Now we even try to fit the fitInTitleRowTag
                    if fitInTitleRowText is not None:
                        remainingWidth = availableWidth - titleLength \
                                         - flagIconsItem.sizeHint(self)[0] - 2* self.hSpace
                        if self.getFontMetrics().width(fitInTitleRowText) <= remainingWidth:
                            self.addCenter(TextItem(fitInTitleRowText),align=RIGHT)
                            fittedTextInTitleRow = True
                    self.newRow()
                else:
                    self.newRow() # We'll put the flags either into right region or into a new row
                    
                    # Now we have an optimization problem: We want to minimize the rows, but the less rows
                    # we allow, the more columns we need. More columns means less space for tags in the
                    # center region and thus potentially a lot rows.
                    
                    # In any case we are not going to fit the fitInTitleRowTag, so we can compute the texts:
                    leftTexts,rightTexts = self.prepareColumns(node)

                    # First we compute a lower bound of the rows used by the tags
                    rowsForSure = max(len(leftTexts),len(rightTexts))
                    
                    if rowsForSure == 0:
                        # No tags
                        if 2*maxFlagsInTitleRow >= len(flagIcons):
                            flagIconsItem.rows = 2
                            self.addRight(flagIconsItem)
                        else: self.addCenter(flagIconsItem,align=RIGHT)
                    else:
                        # Do not use too many columns
                        maxFlagsInTitleRow = min(2,maxFlagsInTitleRow)
                        if maxFlagsInTitleRow == 0:
                            # Put all flags on the right side of the tags
                            flagIconsItem.columns = 1 if len(flagIcons) <= rowsForSure else 2
                            self.addCenter(flagIconsItem,align=RIGHT)
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
                                self.addCenter(flagIconsItem,align=RIGHT)
            else: 
                # This means len(flagIcons) == 0
                # Try to fit fitInTitleRowText
                if fitInTitleRowText is not None:
                    titleLength = titleItem.sizeHint(self)[0]
                    if (self.getFontMetrics().width(fitInTitleRowText)
                                <= availableWidth - titleLength - self.hSpace):
                        self.addCenter(TextItem(fitInTitleRowText),align=RIGHT)
                        fittedTextInTitleRow = True
                self.newRow()
            
            # Tags
            if leftTexts is None: # Tags may have been computed already above 
                leftTexts,rightTexts = self.prepareColumns(
                                        node,excludeTags=[fitInTitleRowTag] if fittedTextInTitleRow else [])

            if len(leftTexts) > 0 or len(rightTexts) > 0:
                self.addCenter(MultiTextItem(leftTexts,rightTexts))
            
            # Path
            if self.config.options['showPaths'].value and node.isFile():
                if node.path is None:
                    node.path = db.path(node.id)
                self.addCenter(TextItem(node.path,ITALIC_STYLE))
                self.newRow()


    @staticmethod
    def getDefaultDataPieces():
        left = [configuration.DataPiece(tags.get(name)) for name in ['composer','artist','performer']]
        right = [configuration.DataPiece(tags.get(name)) for name in ['date','conductor']]
        return left,right


BrowserDelegate.defaultConfig = configuration.DelegateConfiguration(
                                            translate("Delegates","Browser"),BrowserDelegate,builtin=True)
configuration.addDelegateConfiguration(BrowserDelegate.defaultConfig)
