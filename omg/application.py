#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import sys
from PyQt4 import QtCore, QtGui

# Import and initialize modules
from omg import database
database.connect()
from omg import tags
tags.updateIndexedTags()
from omg import config, browser, search
search.init()

# Create GUI
app = QtGui.QApplication(sys.argv)
gui = QtGui.QWidget()
layout = QtGui.QHBoxLayout()
gui.setLayout(layout)

browser = browser.Browser(None)
layout.addWidget(browser)

gui.resize(600, 410)
screen = QtGui.QDesktopWidget().screenGeometry()
size =  gui.geometry()
gui.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)
gui.show()
sys.exit(app.exec_())