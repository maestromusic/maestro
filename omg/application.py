# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import sys, os, random, logging, io
import logging.config
from PyQt4 import QtCore, QtGui

# Global variables. Only for debugging! Later there may be more than one browser, playlist, etc.
widget = None
browser = None
playlist = None
controlWidget = None
names = ['Organize Music by Groups',
         'OMG is for Music Geeks',
         'Overpowered Music GUI',
         'Ordinary Musicplayers are Gay',
         'OH -- MY -- GOD',
         'Oh Maddin ... Grmpf',
         'Oh Michael ... Grmpf'  ]

optionsOverride = {}

def run():
    # Switch first to the directory containing this file
    if os.path.dirname(__file__):
        os.chdir(os.path.dirname(__file__))
    # And then one directory above
    os.chdir("../")
    
    # Initialize config and logging
    from omg import config
    config.init(optionsOverride)
    
    logging.getLogger("omg").debug("START")
    
    # Some Qt-classes need a running QApplication before they can be created
    app = QtGui.QApplication(sys.argv)

    # Import and initialize modules
    from omg import database
    database.connect()
    from omg import tags
    tags.updateIndexedTags()
    from omg import mpclient, search, control, constants
    search.init()
    from omg.gui import browser as browserModule
    from omg.gui import playlist as playlistModule

    from omg import plugins
    plugins.loadPlugins()
    
    # Create GUI
    global widget,browser,playlist,controlWidget
    widget = QtGui.QMainWindow()
    widget.setDockNestingEnabled(True)

    controlWidget = control.createWidget()
    controlDock = QtGui.QDockWidget()
    controlDock.setWindowTitle("Playback control")
    controlDock.setAllowedAreas(QtCore.Qt.TopDockWidgetArea | QtCore.Qt.BottomDockWidgetArea)
    controlDock.setWidget(controlWidget)
    widget.addDockWidget(QtCore.Qt.TopDockWidgetArea, controlDock)
    
    
    browser = browserModule.Browser()
    browserDock = QtGui.QDockWidget()
    browserDock.setWindowTitle("Element browser")
    browserDock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
    browserDock.setWidget(browser)
    widget.addDockWidget(QtCore.Qt.LeftDockWidgetArea, browserDock)
    
    playlist = playlistModule.Playlist()
    
    central = QtGui.QTabWidget()
    central.addTab(playlist,"playlist")
    
    import omg.gopulate
    import omg.gopulate.models
    import omg.gopulate.gui
    gm = omg.gopulate.models.GopulateTreeModel([ config.get("music","collection") ])
    gw = omg.gopulate.gui.GopulateWidget(gm)
    central.addTab(gw, "gopulate")
    
    import omg.filesystembrowser
    fb = omg.filesystembrowser.FileSystemBrowser()
    fbDock = QtGui.QDockWidget()
    fbDock.setWindowTitle("File browser")
    fbDock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
    fbDock.setWidget(fb)
    fb.currentDirectoryChanged.connect(gm.setCurrentDirectory)
    widget.addDockWidget(QtCore.Qt.RightDockWidgetArea, fbDock)
    
    widget.setCentralWidget(central)
    control.synchronizePlaylist(playlist.getModel())
    
    widget.resize(config.shelve['widget_width'],config.shelve['widget_height'])
    widget.setWindowTitle('OMG version {0} – {1}'.format(constants.VERSION, random.choice(names)))
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
    logging.shutdown()
    sys.exit(returnValue)

if __name__ == "__main__":
    run()