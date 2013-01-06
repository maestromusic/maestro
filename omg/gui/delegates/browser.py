# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore

from ...core import tags, covers
from ...core.nodes import Wrapper
from . import profiles, StandardDelegate, TextItem, ITALIC_STYLE
from ...models import browser as browsermodel

translate = QtCore.QCoreApplication.translate


class BrowserDelegate(StandardDelegate):
    """Delegate used in the Browser. Does some effort to put flag icons at the optimal place using free space
    in the title row and trying not to increase the overall number of rows.
    """

    profileType = profiles.createProfileType(
            name       = 'browser',
            title      = translate("Delegates","Browser"),
            leftData   = ['t:composer','t:artist','t:performer'],
            rightData  = ['t:date','t:conductor'],
            overwrite  = {"fitInTitleRowData": profiles.DataPiece(tags.get("date"))
                                         if tags.isInDb("date") else None},
            addOptions = [profiles.DelegateOption("showSortValues",
                         translate("Delegates","Display sort values instead of real values"),"bool",False)]
    )
    
    def __init__(self,view,profile):
        super().__init__(view,profile)
        # Don't worry, addCacheSize won't add sizes twice
        covers.addCacheSize(self.profile.options['coverSize'])
    
    def layout(self,index,availableWidth):
        node = self.model.data(index)
        
        if isinstance(node,browsermodel.ValueNode):
            valueList = node.sortValues if self.profile.options['showSortValues'] else node.values
            for value in valueList:
                self.addCenter(TextItem(value))
                self.newRow()
        elif isinstance(node,browsermodel.VariousNode):
            self.addCenter(TextItem(self.tr("Unknown/Various"),ITALIC_STYLE))
        elif isinstance(node,browsermodel.HiddenValuesNode):
            self.addCenter(TextItem(self.tr("Hidden"),ITALIC_STYLE))
        elif isinstance(node,browsermodel.LoadingNode):
            self.addCenter(TextItem(self.tr("Loading..."),ITALIC_STYLE))
        else:
            super().layout(index,availableWidth)
    
    def _handleProfileChanged(self,profile):
        """React to the configuration dispatcher."""
        super()._handleProfileChanged(profile)
        if profile == self.profile:
            covers.addCacheSize(profile.options['coverSize'])
            