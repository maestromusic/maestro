# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2013 Martin Altmayer, Michael Helmling
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

import logging

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt 

from ... import logging as omglogging
from ...gui import mainwindow, dockwidget
from . import resources

_signaller = None


def enable():
    global _signaller    
    _signaller = StreamSignaller()
    mainwindow.addWidgetData(mainwindow.WidgetData(
        id = "loggerdock",
        name = QtGui.QApplication.translate("LoggerDock","Logger"),
        icon = QtGui.QIcon(":/omg/plugins/loggerdock/loggerdock.png"),
        theClass = LoggerDock,
        central = False,
        dock = True,
        default = False,
        preferredDockArea = Qt.BottomDockWidgetArea))


def disable():
    mainwindow.removeWidgetData("loggerdock")


class StreamSignaller(QtCore.QObject):
    textReceived = QtCore.pyqtSignal(str)
    
    def write(self, msg):
        self.textReceived.emit(msg)
        
    def flush(self):
        pass


class LoggerDock(dockwidget.DockWidget):
    def __init__(self, parent=None, **args):
        super().__init__(parent, **args)
        
        layout = QtGui.QVBoxLayout()
        area = QtGui.QTextBrowser(self)
        dropdown = QtGui.QComboBox()
        dropdown.addItems(["Debug", "Info", "Warning", "Error", "Critical"])
        self.handler = logging.StreamHandler(_signaller)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.handler.setFormatter(formatter)
        omglogging.addHandler(self.handler)
        dropdown.activated[str].connect(
                                lambda levelStr : self.handler.setLevel(getattr(logging, levelStr.upper())))
        self.handler.setLevel(logging.DEBUG)
        layout.addWidget(dropdown)
        layout.addWidget(area)
        _signaller.textReceived.connect(area.insertPlainText)
        _signaller.textReceived.connect(lambda x : area.ensureCursorVisible())
        widget = QtGui.QWidget()
        widget.setLayout(layout)
        self.setWidget(widget)
        
        