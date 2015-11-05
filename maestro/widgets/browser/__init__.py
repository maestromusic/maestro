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
from maestro.widgets.browser.browser import BrowserTreeView


def init():
    from maestro import utils
    from maestro.gui import treeactions
    from maestro.widgets import WidgetClass
    from maestro.widgets.browser import delegate
    from maestro.widgets.browser.browser import Browser, BrowserTreeView
    from maestro.widgets.browser.coverbrowser import CoverBrowser
    from maestro.widgets.browser.covertable import CoverTable
    translate = QtCore.QCoreApplication.translate
    delegate.init()
    WidgetClass(
        id='browser', theClass=Browser, name=translate('Browser', 'Browser'),
        areas='dock', preferredDockArea='left'
    ).register()

    WidgetClass(
        id='coverbrowser', theClass=CoverBrowser, name=translate('CoverBrowser', 'Cover Browser'),
        icon=utils.images.icon('widgets/coverbrowser.png')
    ).register()

    coverbrowser.addDisplayClass('table', CoverTable)

    import maestro.widgets.browser.actions
    maestro.widgets.browser.actions.init()

    for identifier in ('hideTagValues', 'tagValue', 'editTags', 'changeURLs', 'delete', 'merge',
                       'completeContainer', 'collapseAll', 'expandAll', 'appendToPL', 'replacePL'):
        BrowserTreeView.addActionDefinition(identifier)
    treeactions.SetElementTypeAction.addSubmenu(BrowserTreeView.actionConf.root)
    treeactions.ChangePositionAction.addSubmenu(BrowserTreeView.actionConf.root)
