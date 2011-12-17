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
from . import StandardDelegate, configuration, TextItem, ITALIC_STYLE
from ...models import browser as browsermodel

translate = QtCore.QCoreApplication.translate


class BrowserDelegate(StandardDelegate):
    """Delegate used in the Browser. Does some effort to put flag icons at the optimal place using free space
    in the title row and trying not to increase the overall number of rows.
    """
    options = configuration.copyOptions(StandardDelegate.options)
    options["fitInTitleRowData"].value = configuration.DataPiece(tags.get("date")) if tags.exists("date") else None
    options["showSortValues"] = configuration.DelegateOption("showSortValues",
                            translate("Delegates","Display sort values instead of real values"),"bool",False)
 
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
            super().layout(index,availableWidth)
            
    @staticmethod
    def getDefaultDataPieces():
        left = [configuration.DataPiece(tags.get(name)) for name in ['composer','artist','performer']]
        right = [configuration.DataPiece(tags.get(name)) for name in ['date','conductor']]
        return left,right


BrowserDelegate.defaultConfig = configuration.DelegateConfiguration(
                                            translate("Delegates","Browser"),BrowserDelegate,builtin=True)
configuration.addDelegateConfiguration(BrowserDelegate.defaultConfig)
