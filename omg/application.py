#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import sys, os
from PyQt4 import QtCore, QtGui

def run():
    # Switch first to the directory containing this file
    if os.path.dirname(__file__):
        os.chdir(os.path.dirname(__file__))
    # And then one directory above
    os.chdir("../")
    
    # Some Qt-classes need a running QApplication before they can be created
    app = QtGui.QApplication(sys.argv)

    # Import and initialize modules
    from omg import database
    database.connect()
    from omg import tags
    tags.updateIndexedTags()
    from omg import config, mpclient, search, control, browser, gui
    search.init()
    from gui import playlist

    # Create GUI
    widget = QtGui.QWidget()
    layout = QtGui.QVBoxLayout()
    widget.setLayout(layout)

    controlWidget = control.createWidget(widget)
    layout.addWidget(controlWidget,0)
    
    splitter = QtGui.QSplitter(widget)
    layout.addWidget(splitter,1)
    
    browser = browser.Browser(widget)
    splitter.addWidget(browser)
    splitter.setStretchFactor(0,2)
    
    playlist = playlist.Playlist(widget)
    splitter.addWidget(playlist)
    splitter.setStretchFactor(1,5)

    #browser.nodeDoubleClicked.connect(playlist.addNode)
    control.synchronizePlaylist(playlist.getModel())
    
    widget.resize(800, 600)
    screen = QtGui.QDesktopWidget().screenGeometry()
    size =  widget.geometry()
    widget.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)
    widget.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run()