# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2015 Martin Altmayer, Michael Helmling
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
from maestro.widgets.editor.gui import EditorTreeView
translate = QtCore.QCoreApplication.translate


def init():
    from maestro import utils
    from maestro.widgets import WidgetClass
    from maestro.gui import treeactions
    from maestro.widgets.editor.gui import EditorTreeView, EditorWidget
    from maestro.widgets.editor.delegate import EditorDelegate
    for identifier in 'editTags', 'remove', 'merge', 'flatten', 'clearTree', 'commit':
        EditorTreeView.addActionDefinition(identifier)
    treeactions.SetElementTypeAction.addSubmenu(EditorTreeView.actionConf.root)
    treeactions.ChangePositionAction.addSubmenu(EditorTreeView.actionConf.root)
    WidgetClass(
        id='editor', theClass=EditorWidget, name=translate('Editor', 'editor'),
        icon=utils.images.icon('accessories-text-editor'),
        preferredDockArea='right'
    ).register()
    from maestro.gui.delegates import profiles
    EditorDelegate.profileType = profiles.createProfileType(
        name='editor', title=translate('Delegates', 'Editor'),
        leftData=['t:album', 't:composer', 't:artist', 't:performer'],
        rightData=['t:date', 't:genre', 't:conductor'],
        overwrite=dict(showPaths=True, showType=True,
                       appendRemainingTags=True, showAllAncestors=True)
    )
    from maestro.widgets.editor import albumguesser
    albumguesser.init()
