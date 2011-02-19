# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation

from PyQt4 import QtGui, QtCore

from omg import tags

class NewTagDialog(QtGui.QDialog):

    def __init__(self, tagname, parent = None):
        QtGui.QDialog.__init__(self, parent)
        self.setWindowModality(QtCore.Qt.WindowModal)
        label = QtGui.QLabel(self.tr("The tag '{}' occured for the first time. Please enter its type:").format(tagname))
        self.combo = QtGui.QComboBox(self)
        self.combo.addItems([type.name for type in tags.TYPES])
        
        self.ignoreButton = QtGui.QPushButton(self.tr("Ignore this tag"))
        self.okButton = QtGui.QPushButton(self.tr("Ok"))
        
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
        return tags.ValueType.byName(self.combo.currentText())
    
    @staticmethod
    def queryTagType(name, parent = None):
        d = NewTagDialog(name, parent)
        if d.exec() == QtGui.QDialog.Accepted:
            return d.selectedType()
        return None
