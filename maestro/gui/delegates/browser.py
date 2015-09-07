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

from PyQt5 import QtCore

from maestro.core import tags, covers
from maestro.gui.delegates import profiles, StandardDelegate, TextItem, STD_STYLE, ITALIC_STYLE,\
    BOLD_STYLE

translate = QtCore.QCoreApplication.translate


def init():
    BrowserDelegate.profileType = profiles.createProfileType(
        name='browser',
        title=translate("Delegates","Browser"),
        leftData=['t:composer', 't:artist', 't:performer'],
        rightData=['t:date', 't:conductor'],
        overwrite={"fitInTitleRowData": profiles.DataPiece(tags.get("date"))
                                        if tags.isInDb("date") else None},
        addOptions=[
            profiles.DelegateOption("showSortValues",
                translate("Delegates", "Display sort values instead of real values"),"bool",False)
        ]
    )


class BrowserDelegate(StandardDelegate):
    """Delegate used in the Browser. Does some effort to put flag icons at the optimal place using free space
    in the title row and trying not to increase the overall number of rows.
    """
    
    def __init__(self, view, profile):
        super().__init__(view, profile)
        # Don't worry, addCacheSize won't add sizes twice
        covers.addCacheSize(self.profile.options['coverSize'])
    
    def layout(self, index, availableWidth):
        node = index.model().data(index)
        from maestro.widgets import browser
        
        if isinstance(node, browser.nodes.TagNode):
            valueList = node.sortValues if self.profile.options['showSortValues'] else node.values
            for value, matching in valueList:
                self.addCenter(TextItem(value, style=BOLD_STYLE if matching else STD_STYLE))
                self.newRow()
        elif isinstance(node, browser.nodes.VariousNode):
            self.addCenter(TextItem(self.tr("Unknown/Various"), ITALIC_STYLE))
        elif isinstance(node, browser.nodes.HiddenValuesNode):
            self.addCenter(TextItem(self.tr("Hidden"), ITALIC_STYLE))
        elif isinstance(node, browser.nodes.LoadingNode):
            self.addCenter(TextItem(self.tr("Loading..."), ITALIC_STYLE))
        else:
            super().layout(index, availableWidth)
    
    def _handleProfileChanged(self, profile):
        """React to the configuration dispatcher."""
        super()._handleProfileChanged(profile)
        if profile == self.profile:
            covers.addCacheSize(profile.options['coverSize'])
