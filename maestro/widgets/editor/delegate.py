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

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from maestro.gui.delegates import profiles, StandardDelegate
from maestro.core import tags, levels

translate = QtCore.QCoreApplication.translate


class EditorDelegate(StandardDelegate):
    """Delegate for the editor."""
    
    def createEditor(self, parent, option, index):
        wrapper = index.model().data(index)
        if wrapper is not None:
            return EditorLineEdit(wrapper.element, parent)
        
    def setModelData(self, editor, model, index):
        element = editor.element
        newTitle = editor.text()
        diff = None
        if tags.TITLE not in element.tags:
            if newTitle != '':
                diff = tags.TagDifference(additions=[(tags.TITLE, newTitle)])
        else:
            oldTitle = element.tags[tags.TITLE][0]
            if newTitle == '':
                diff = tags.TagDifference(removals=[(tags.TITLE, oldTitle)])
            elif newTitle != oldTitle:
                diff = tags.TagDifference(replacements=[(tags.TITLE, oldTitle, newTitle)])
                
        if diff is not None:
            levels.editor.changeTags({element: diff})


class EditorLineEdit(QtWidgets.QLineEdit):
    def __init__(self, element, parent):
        title = element.tags[tags.TITLE][0] if tags.TITLE in element.tags else ''
        super().__init__(title, parent)
        self.element = element
        self.setAutoFillBackground(True)
