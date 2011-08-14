# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""The DBAnalyzer displays statistics about the database, finds errors in it and allows the user to correct them. It is provided as central widget, dialog (in the extras menu) and standalone application (bin/dbanalyzer)."""

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
    def __init__(self,parent=None,state=None):
        QtGui.QDockWidget.__init__(self,parent)
        self.setWindowTitle(self.tr("UndoView"))
        
        tabWidget = QtGui.QTabWidget()
        self.setWidget(tabWidget)
        
        activeView = QtGui.QUndoView(modify.stack)
        realView = QtGui.QUndoView(modify.stack.mainStack)
        editorView = QtGui.QUndoView(modify.stack.editorStack)
        
        tabWidget.addTab(activeView,self.tr("Active"))
        tabWidget.addTab(realView,self.tr("Real"))
        tabWidget.addTab(editorView,self.tr("Editor"))
