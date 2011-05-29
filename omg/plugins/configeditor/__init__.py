# -*- coding: utf-8 -*-
# Copyright 2011 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation

from PyQt4 import QtCore, QtGui
from omg import application, config
translate = QtGui.QApplication.translate

_action = None
def enable():
    global _action
    _action = QtGui.QAction(application.mainWindow)
    _action.setText(translate("ConfigEditorDialog","Preferences"))
    _action.triggered.connect(showDialog)
    options = config.optionObject
    #print(len(options))
    #print(list(options))

def mainWindowInit():
    application.mainWindow.menus['edit'].addAction(_action)

def disable():
    application.mainWindow.menus['edit'].removeAction(_action)
def showDialog():
    pd = PreferencesDialog(application.mainWindow)
    pd.show()

class ConfigEditorModel(QtCore.QAbstractItemModel):
    def __init__(self, section):
        self.root = section
    def index(self, row, column, parent):
        if not parent.isValid():
            parent = self.root
        else:
            parent = parent.internalPointer()
        child = list(parent._members.items())[row]
class PreferencesDialog(QtGui.QDialog):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setModal(False)
        self.tabWidget = QtGui.QTabWidget(self)
        self.tabWidget.setUsesScrollButtons(False)
        opt = config.optionObject
        for name in opt:
            self.tabWidget.addTab(ConfigSectionWidget(opt[name]), name)
        self.resize(self.tabWidget.sizeHint() + QtCore.QSize(10,10))