# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""UndoView provides a DockWidget that displays the active, real and editor-UndoStack using three
QtGui.QUndoStacks."""

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ...gui import mainwindow
from ... import modify



# The next few (undocumented) functions are called by the plugin system
def enable():
    global _action
    mainwindow.addWidgetData(mainwindow.WidgetData(
        "undoview",QtGui.QApplication.translate("UndoView","UndoView"),UndoViewDock,
        False,True,False,preferredDockArea=Qt.RightDockWidgetArea))


def disable():
    mainwindow.removeWidgetData("undoview")


class UndoViewDock(QtGui.QDockWidget):
    """UndoViewDock displays the active, real and editor-UndoStack using three QtGui.QUndoStacks."""
    def __init__(self,parent=None,state=None,location=None):
        QtGui.QDockWidget.__init__(self,parent)
        self.setWindowTitle(self.tr("UndoView"))
        
        self.tabWidget = QtGui.QTabWidget(self)
        self.setWidget(self.tabWidget)
        
        activeView = QtGui.QUndoView(modify.stack)
        realView = QtGui.QUndoView(modify.stack.mainStack)
        editorView = QtGui.QUndoView(modify.stack.editorStack)
        
        self.tabWidget.addTab(activeView,self.tr("Active"))
        self.tabWidget.addTab(realView,self.tr("Real"))
        self.tabWidget.addTab(editorView,self.tr("Editor"))
        
        if state is not None and isinstance(state,int) and 0 <= state < self.tabWidget.count():
            self.tabWidget.setCurrentIndex(state)
        
    def saveState(self):
        return self.tabWidget.currentIndex()
