# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg import config, constants

class MainWindow(QtGui.QMainWindow):
    def initMenus(self):
        self.menus = {}
        self.menus['extras'] = self.menuBar().addMenu(self.tr("&Extras"))
        self.menus['help'] = self.menuBar().addMenu(self.tr("&Help"))
        
        self.aboutAction = QtGui.QAction(self)
        self.aboutAction.setText(self.tr("&About"))
        self.aboutAction.triggered.connect(self.showAboutDialog)
        self.menus['help'].addAction(self.aboutAction)

    def __init__(self,parent=None):
        QtGui.QMainWindow.__init__(self, parent)
        self.setDockNestingEnabled(True)
        self.setWindowTitle('OMG version {0}'.format(constants.VERSION))
        self.initMenus()
        self.statusBar()
        
        #~ from omg.gui import browser as browserModule
        #~ from omg.gui import playlist as playlistModule
        #~ from omg import control, config
        #~ import omg
#~ 
        #~ global browser,playlist,controlWidget
    #~ 
    #~ 
        #~ controlWidget = control.createWidget()
        #~ controlDock = QtGui.QDockWidget()
        #~ controlDock.setWindowTitle(self.tr("Playback control"))
        #~ controlDock.setAllowedAreas(Qt.TopDockWidgetArea | Qt.BottomDockWidgetArea)
        #~ controlDock.setWidget(controlWidget)
        #~ self.addDockWidget(Qt.TopDockWidgetArea, controlDock)
        #~ 
        #~ browser = browserModule.Browser()        
        #~ browserDock = QtGui.QDockWidget()
        #~ browserDock.setWindowTitle(self.tr("Element browser"))
        #~ browserDock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        #~ browserDock.setWidget(browser)
        #~ self.addDockWidget(Qt.LeftDockWidgetArea, browserDock)
        #~ 
        #~ playlist = playlistModule.Playlist()
        #~ 
        #~ central = QtGui.QTabWidget()
        #~ central.addTab(playlist,self.tr("Playlist"))
        #~ 
        #~ import omg.models.editor
        #~ import omg.gui.editor
        #~ gm = omg.models.editor.EditorModel()
        #~ gw = omg.gui.editor.EditorWidget(gm)
        #~ central.addTab(gw,self.tr("Editor"))
        #~ 
        #~ import omg.filesystembrowser
        #~ fb = omg.filesystembrowser.FileSystemBrowser()
        #~ fbDock = QtGui.QDockWidget()
        #~ fbDock.setWindowTitle(self.tr("File browser"))
        #~ fbDock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        #~ fbDock.setWidget(fb)
        #~ self.addDockWidget(Qt.RightDockWidgetArea, fbDock)
        #~ 
        #~ x = QtGui.QUndoView(gm.undoStack)
        #~ xDock = QtGui.QDockWidget()
        #~ xDock.setWindowTitle("test")
        #~ xDock.setWidget(x)
        #~ self.addDockWidget(Qt.RightDockWidgetArea, xDock)

        #~ self.setCentralWidget(central)
        #~ control.synchronizePlaylist(playlist.getModel())
        #~ 
        #~ 
        #~ if options.gui.startTab == 'populate':
            #~ central.setCurrentWidget(gw)

        # Resize and move the widget to the size and position it had when the program was closed
        self.resize(config.storage.gui.widget_width,config.storage.gui.widget_height)
        if config.storage.gui.widget_position is None: # Center the window
            screen = QtGui.QDesktopWidget().screenGeometry()
            size = self.geometry()
            self.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)
        else: self.move(*config.storage.gui.widget_position)

    def shutdown(self):
        config.storage.gui.widget_position = (self.x(),self.y())
        config.storage.gui.widget_width = self.width()
        config.storage.gui.widget_height = self.height()

    def showAboutDialog(self):
        QtGui.QMessageBox.information(self,"OMG",
            self.tr("This is OMG version {} by Martin Altmayer and Michael Helmling.").format(constants.VERSION))
