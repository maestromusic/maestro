# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import sys, os, random, logging, io
from omg import constants
from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

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

# Default options and options from the config file will be overwritten by the options in optionOverride (this is necessary for command-line arguments). The dictionary should map section names to dictionaries containing the options in the section. Remember to add a default option to config._defaultOptions for anything that may appear in optionsOverride.
optionsOverride = {}

class OmgMainWindow(QtGui.QMainWindow):
    
    def initMenus(self):
        self.menus = {}
        self.menus['extras'] = self.menuBar().addMenu("&Extras")
        self.menus['help'] = self.menuBar().addMenu("&Help")
        
        self.aboutAction = QtGui.QAction(self)
        self.aboutAction.setText("&About")
        self.aboutAction.triggered.connect(self.showAboutDialog)
        self.menus['help'].addAction(self.aboutAction)
    
    def __init__(self, parent = None):
        QtGui.QMainWindow.__init__(self, parent)
        self.setDockNestingEnabled(True)
        self.setWindowTitle('OMG version {0} – {1}'.format(constants.VERSION, random.choice(names)))
        self.initMenus()
        
        from omg.gui import browser as browserModule
        from omg.gui import playlist as playlistModule
        from omg import control, config

        global browser,playlist,controlWidget
    
    
        controlWidget = control.createWidget()
        controlDock = QtGui.QDockWidget()
        controlDock.setWindowTitle("Playback control")
        controlDock.setAllowedAreas(Qt.TopDockWidgetArea | Qt.BottomDockWidgetArea)
        controlDock.setWidget(controlWidget)
        self.addDockWidget(Qt.TopDockWidgetArea, controlDock)
        
        browser = browserModule.Browser()
        browserDock = QtGui.QDockWidget()
        browserDock.setWindowTitle("Element browser")
        browserDock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        browserDock.setWidget(browser)
        self.addDockWidget(Qt.LeftDockWidgetArea, browserDock)
        
        playlist = playlistModule.Playlist()
        
        central = QtGui.QTabWidget()
        central.addTab(playlist,"playlist")
        
        import omg.gopulate.models
        import omg.gopulate.gui
        gm = omg.gopulate.models.GopulateTreeModel(config.get("music","collection"))
        gw = omg.gopulate.gui.GopulateWidget(gm)
        central.addTab(gw, "gopulate")
        
        import omg.filesystembrowser
        fb = omg.filesystembrowser.FileSystemBrowser()
        fbDock = QtGui.QDockWidget()
        fbDock.setWindowTitle("File browser")
        fbDock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        fbDock.setWidget(fb)
        fb.currentDirectoryChanged.connect(gm.setCurrentDirectory)
        fb.searchDirectoryChanged.connect(gm.setSearchDirectory)
        self.addDockWidget(Qt.RightDockWidgetArea, fbDock)
        
        self.setCentralWidget(central)
        control.synchronizePlaylist(playlist.getModel())
        
        if config.get('gui','startTab') == 'populate':
            central.setCurrentWidget(gw)
        
        self.resize(config.shelve['widget_width'],config.shelve['widget_height'])
        
        if config.shelve['widget_position'] is None: # Center the self
            screen = QtGui.QDesktopWidget().screenGeometry()
            size =  self.geometry()
            self.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)
        else: self.move(*config.shelve['widget_position'])
        self.show()
    
    def showAboutDialog(self):
        QtGui.QMessageBox.information(self,
                                      'OMG',
                                      'This is OMG version {0}\n{1}'.format(constants.VERSION, random.choice(names)),
                                      )
def initModules():
    # Switch first to the directory containing this file
    if os.path.dirname(__file__):
        os.chdir(os.path.dirname(__file__))
    # And then one directory above
    os.chdir("../")
    
    # Initialize config and logging
    from omg import config
    config.init(optionsOverride)
    
    logging.getLogger("omg").debug("START")
    from omg import database
    database.connect()
    from omg import tags
    tags.init()
    from omg import search
    search.init()

    
    
def run():
    
    # Some Qt-classes need a running QApplication before they can be created
    app = QtGui.QApplication(sys.argv)
    # Import and initialize modules    
    initModules()
    
    # Create GUI
    global widget
    widget = OmgMainWindow()
    from omg import plugins
    plugins.loadPlugins()
    # launch application
    returnValue = app.exec_()
    
    # Close operations
    from omg import config, plugins
    
    config.shelve['widget_position'] = (widget.x(),widget.y())
    config.shelve['widget_width'] = widget.width()
    config.shelve['widget_height'] = widget.height()
    plugins.teardown()
    config.shelve.close()
    logging.shutdown()
    sys.exit(returnValue)

if __name__ == "__main__":
    run()