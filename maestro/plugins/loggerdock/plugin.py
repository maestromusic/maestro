# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2013-2015 Martin Altmayer, Michael Helmling
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

from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtCore import Qt

from maestro import logging as maestrologging, widgets

_signaller = None


def enable():
    global _signaller    
    _signaller = StreamSignaller()
    widgets.addClass(
        id = "loggerdock",
        name = QtWidgets.QApplication.translate("LoggerDock", "Logger"),
        icon = QtGui.QIcon(":/maestro/plugins/loggerdock/loggerdock.png"),
        theClass = LoggerDock,
        preferredDockArea = 'bottom'
    )


def disable():
    widgets.removeClass("loggerdock")


class StreamSignaller(QtCore.QObject):
    def __init__(self):
        super().__init__()
        self.doSignalling = True
        QtWidgets.qApp.aboutToQuit.connect(self.stopSignalling)
    textReceived = QtCore.pyqtSignal(str)

    def stopSignalling(self):
        self.doSignalling = False

    def write(self, msg):
        if self.doSignalling:
            self.textReceived.emit(msg)
        
    def flush(self):
        pass


class LoggerDock(widgets.Widget):
    def __init__(self, state=None, **args):
        super().__init__(**args)
        layout = QtWidgets.QVBoxLayout(self)
        
        self.textBrowser = QtGui.QTextBrowser(self)
        dropdown = QtWidgets.QComboBox()
        dropdown.addItems(["Debug", "Info", "Warning", "Error", "Critical"])
        self.handler = logging.StreamHandler(_signaller)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.handler.setFormatter(formatter)
        maestrologging.addHandler(self.handler)
        dropdown.activated[str].connect(
                                lambda levelStr : self.handler.setLevel(getattr(logging, levelStr.upper())))
        self.handler.setLevel(logging.DEBUG)
        layout.addWidget(dropdown)
        layout.addWidget(self.textBrowser)
        _signaller.textReceived.connect(self.updateArea)

    def updateArea(self, newText):
        self.textBrowser.insertPlainText(newText)
        self.textBrowser.ensureCursorVisible()

        