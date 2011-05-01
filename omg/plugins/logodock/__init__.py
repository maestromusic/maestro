# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""This simple plugin adds a dock widget which displays OMG's logo. It played a major role during testing OMG's widget system."""

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg import constants
from omg.gui import mainwindow


def enable():
    mainwindow.addWidgetData(mainwindow.WidgetData(
        "logodock",QtGui.QApplication.translate("LogoDock","Logo"),LogoDock,False,False,
        preferredDockArea=Qt.RightDockWidgetArea))


def disable():
    mainwindow.removeWidgetData("logodock")


class LogoDock(QtGui.QDockWidget):
    def __init__(self,parent=None):
        QtGui.QDockWidget.__init__(self,parent)
        label = QtGui.QLabel('<img src="images/omg.png" />')
        label.setAlignment(Qt.AlignCenter)
        self.setWidget(label)
