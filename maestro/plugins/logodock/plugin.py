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

"""This simple plugin adds a dock widget which displays Maestro's logo. It played a major role during testing
Maestro's widget system."""

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from maestro import utils, widgets


def enable():
    widgets.addClass(
        id = "logodock",
        name = QtWidgets.QApplication.translate("LogoDock", "Logo"),
        icon = QtGui.QIcon(":/maestro/logo.png"),
        theClass = LogoDock,
        areas = 'dock',
        preferredDockArea = 'right'
    )


def disable():
    widgets.removeClass("logodock")


class LogoDock(widgets.Widget):
    def __init__(self, state=None, **args):
        super().__init__(**args)
        layout = QtWidgets.QHBoxLayout(self)
        label = QtWidgets.QLabel()
        label.setPixmap(utils.images.pixmap(':/maestro/logo.png'))
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

    def initialize(self, state):
        # initialize is called when the LogoDock has been added to its dockwidget
        dock = self.containingWidget()
        # Do not show a title and icon in the title bar of this dock widget.
        dock.setWindowTitle('')
        dock.setWindowIcon(None)