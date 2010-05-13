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
    os.chdir(os.path.dirname(__file__)+"/../")
    # Some Qt-classes need a running QApplication before they can be created
    app = QtGui.QApplication(sys.argv)

    # Import and initialize modules
    from omg import database
    database.connect()
    from omg import tags
    tags.updateIndexedTags()
    from omg import config, mpclient, search, control, browser, playlist
    search.init()

    # Create GUI
    gui = QtGui.QWidget()
    layout = QtGui.QVBoxLayout()
    gui.setLayout(layout)

    controlWidget = control.createWidget(gui)
    layout.addWidget(controlWidget,0)
    
    bottomLayout = QtGui.QHBoxLayout()
    layout.addLayout(bottomLayout,1)
    
    browser = browser.Browser(gui)
    bottomLayout.addWidget(browser,2)

    playlist = playlist.Playlist(gui)
    bottomLayout.addWidget(playlist,5)

    #browser.nodeDoubleClicked.connect(playlist.addNode)
    playlist.getModel().connectToSyncPlaylist(control.playlist)
    
    control.startSynchronization()
    
    gui.resize(800, 600)
    screen = QtGui.QDesktopWidget().screenGeometry()
    size =  gui.geometry()
    gui.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)
    gui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run()