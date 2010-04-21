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
from omg import database
database.connect()
from omg import tags
tags.updateIndexedTags()
from omg import config, browser, search
search.init()

initialSearchString = 'h-Moll Sonate'
    
if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    browser = browser.Browser(None)
    browser.resize(299, 409)
    screen = QtGui.QDesktopWidget().screenGeometry()
    size =  browser.geometry()
    browser.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)

    #browser.searchBox.setText(initialSearchString)
    browser.show()
    sys.exit(app.exec_())