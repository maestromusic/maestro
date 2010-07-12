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

# Global variables. Only for debugging! Later there may be more than one browser, playlist, etc.
widget = None
browser = None
playlist = None
controlWidget = None

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
    from omg import config, mpclient, search, control, constants
    search.init()
    from omg.gui import browser as browserModule
    from omg.gui import playlist as playlistModule

    from omg import plugins
    plugins.loadPlugins()
    
    # Create GUI
    global widget,browser,playlist,controlWidget
    widget = QtGui.QWidget()
    layout = QtGui.QVBoxLayout()
    widget.setLayout(layout)

    controlWidget = control.createWidget(widget)
    layout.addWidget(controlWidget,0)
    
    splitter = QtGui.QSplitter(widget)
    layout.addWidget(splitter,1)
    
    browser = browserModule.Browser(widget)
    splitter.addWidget(browser)
    splitter.setStretchFactor(0,2)
    
    playlist = playlistModule.Playlist(widget)
    splitter.addWidget(playlist)
    splitter.setStretchFactor(1,5)
    
    control.synchronizePlaylist(playlist.getModel())
    
    widget.resize(config.shelve['widget_width'],config.shelve['widget_height'])
    widget.setWindowTitle('OMG {0}'.format(constants.VERSION))
    if config.shelve['widget_position'] is None: # Center the widget
        screen = QtGui.QDesktopWidget().screenGeometry()
        size =  widget.geometry()
        widget.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)
    else: widget.move(*config.shelve['widget_position'])
    widget.show()
    returnValue = app.exec_()
    
    # Close operations
    config.shelve['widget_position'] = (widget.x(),widget.y())
    config.shelve['widget_width'] = widget.width()
    config.shelve['widget_height'] = widget.height()
    plugins.teardown()
    config.shelve.close()
    sys.exit(returnValue)

if __name__ == "__main__":
    run()