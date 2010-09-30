# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation

from PyQt4 import QtGui, QtCore

from omg.database import tables

class NewTagDialog(QtGui.QDialog):

    def __init__(self, tagname, parent = None):
        QtGui.QDialog.__init__(self, parent)
        self.setWindowModality(QtCore.Qt.WindowModal)
        label = QtGui.QLabel("The tag '{}' occured for the first time. Please enter its type:".format(tagname))
        self.combo = QtGui.QComboBox(self)
        self.combo.addItems(tables.validTagTypes)
        
        self.ignoreButton = QtGui.QPushButton("ignore this tag")
        self.okButton = QtGui.QPushButton("ok")
        
        layout = QtGui.QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self.combo)
        buttonLayout = QtGui.QHBoxLayout()
        buttonLayout.addStretch()
        buttonLayout.addWidget(self.ignoreButton)
        buttonLayout.addWidget(self.okButton)
        layout.addLayout(buttonLayout)
        
        self.ignoreButton.clicked.connect(self.reject)
        self.okButton.clicked.connect(self.accept)
        
    def selectedType(self):
        return self.combo.currentText()
    
    @staticmethod
    def queryTagType(name, parent = None):
        d = NewTagDialog(name, parent)
        if d.exec() == QtGui.QDialog.Accepted:
            return d.selectedType()
        return None