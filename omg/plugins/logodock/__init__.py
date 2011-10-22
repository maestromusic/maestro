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

"""This simple plugin adds a dock widget which displays OMG's logo. It played a major role during testing
OMG's widget system."""

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg import constants
from omg.gui import mainwindow


def enable():
    mainwindow.addWidgetData(mainwindow.WidgetData(
        "logodock",QtGui.QApplication.translate("LogoDock","Logo"),LogoDock,False,True,False,
        preferredDockArea=Qt.RightDockWidgetArea))


def disable():
    mainwindow.removeWidgetData("logodock")


class LogoDock(QtGui.QDockWidget):
    def __init__(self,parent=None,location=None):
        QtGui.QDockWidget.__init__(self,parent)
        label = QtGui.QLabel('<img src="images/omg.png" />')
        label.setAlignment(Qt.AlignCenter)
        self.setWidget(label)
