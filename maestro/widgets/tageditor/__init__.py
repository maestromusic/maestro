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
translate = QtCore.QCoreApplication.translate


def init():
    from maestro import utils
    from maestro.widgets import WidgetClass
    from maestro.widgets.tageditor.tageditor import TagEditorWidget, TagEditorDialog

    WidgetClass(
        id='tageditor', theClass=TagEditorWidget, name=translate('Tageditor', 'Tag Editor'),
        icon=utils.images.icon('tageditor'),
        unique=True,
        areas='dock', preferredDockArea='right'
    ).register()
