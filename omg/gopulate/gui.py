# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore, QtGui
import omg.models

class GopulateWidget(QtGui.QWidget):
    
    def __init__(self, model=None):
        QtGui.QWidget.__init__(self)
        self.tree = QtGui.QTreeView()
        self.tree.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.accept = QtGui.QPushButton('accept')
        layout = QtGui.QVBoxLayout(self)
        layout.addWidget(self.tree)
        layout.addWidget(self.accept)
        
        self.tree.setModel(model)
        self.tree.setHeaderHidden(True)
