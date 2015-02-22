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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ... import utils
from ...gui import mainwindow


def enable():
    mainwindow.addWidgetClass(mainwindow.WidgetClass(
        id = "logodock",
        name = QtGui.QApplication.translate("LogoDock", "Logo"),
        icon = QtGui.QIcon(":/maestro/plugins/logodock/omg.png"),
        theClass = LogoDock,
        areas = 'dock',
        preferredDockArea = 'right'))


def disable():
    mainwindow.removeWidgetClass("logodock")


class LogoDock(mainwindow.Widget):
    def __init__(self, state=None, **args):
        super().__init__(**args)
        layout = QtGui.QHBoxLayout(self)
        label = QtGui.QLabel()
        label.setPixmap(QtGui.QPixmap(':/maestro/omg.png'))
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

    def initialize(self, state):
        # initialize is called when the LogoDock has been added to its dockwidget
        dock = self.containingWidget()
        # Do not show a title and icon in the title bar of this dock widget.
        dock.setWindowTitle('')
        dock.setWindowIcon(None)