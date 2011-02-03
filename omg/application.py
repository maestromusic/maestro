# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import sys, os, random, logging, io

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg import constants
from omg.config import options

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
        import omg

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
        
        import omg.models.editor
        import omg.gui.editor
        gm = omg.models.editor.EditorModel()
        gw = omg.gui.editor.EditorWidget(gm)
        central.addTab(gw, "editor")
        
        import omg.filesystembrowser
        fb = omg.filesystembrowser.FileSystemBrowser()
        fbDock = QtGui.QDockWidget()
        fbDock.setWindowTitle("File browser")
        fbDock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        fbDock.setWidget(fb)
        self.addDockWidget(Qt.RightDockWidgetArea, fbDock)
        
        x = QtGui.QUndoView(gm.undoStack)
        xDock = QtGui.QDockWidget()
        xDock.setWindowTitle("test")
        xDock.setWidget(x)
        self.addDockWidget(Qt.RightDockWidgetArea, xDock)
        #=======================================================================
        # import omg.gui.tageditor
        # tagedit = omg.gui.tageditor.TagEditorWidget()
        # tagDock = QtGui.QDockWidget()
        # tagDock.setWindowTitle("Tag editor")
        # tagDock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        # tagDock.setWidget(tagedit)
        # self.addDockWidget(Qt.RightDockWidgetArea, tagDock)
        #=======================================================================
        
        #TODO gw.itemsSelected.connect(tagedit.setElements)
        
#        depotModel = omg.gopulate.models.GopulateTreeModel(None)
#        depotWidget = omg.gopulate.gui.GopulateTreeWidget()
#        depotWidget.setModel(depotModel)
#        depotDock = QtGui.QDockWidget()
#        depotDock.setWindowTitle("container depot")
#        depotDock.setWidget(depotWidget)
#        self.addDockWidget(Qt.BottomDockWidgetArea, depotDock) 
        
        self.setCentralWidget(central)
        control.synchronizePlaylist(playlist.getModel())
        
        self.statusBar()
        
        if options.gui.startTab == 'populate':
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
    
    
def run(opts, args):
    # Some Qt-classes need a running QApplication before they can be created
    app = QtGui.QApplication(sys.argv)

    # Switch first to the directory containing this file
    if os.path.dirname(__file__):
        os.chdir(os.path.dirname(__file__))
    # And then one directory above
    os.chdir("../")
    
    # Import and initialize modules
    from omg import config # Initialize config and logging
    config.init(opts)
    logging.getLogger("omg").debug("START")
    
    from omg import database
    database.connect()
    from omg import tags
    tags.init()
    from omg import distributor
    distributor.init()
    from omg import search
    search.init()
    
    # Create GUI
    global widget
    widget = OmgMainWindow()
    from omg import plugins
    plugins.loadPlugins()
    
    # Launch application
    returnValue = app.exec_()
    
    # Close operations
    from omg import config, plugins
    import omg.gopulate
    
    config.shelve['widget_position'] = (widget.x(),widget.y())
    config.shelve['widget_width'] = widget.width()
    config.shelve['widget_height'] = widget.height()
    omg.gopulate.terminate()
    plugins.teardown()
    config.shelve.close()
    logging.shutdown()
    sys.exit(returnValue)
