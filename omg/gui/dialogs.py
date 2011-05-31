# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from omg import tags, utils


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


class FancyTabbedPopup(QtGui.QFrame):
    def __init__(self,parent = None):
        QtGui.QFrame.__init__(self,parent)
        
        # Create components
        self.setLayout(QtGui.QVBoxLayout())
        self.tabWidget = QtGui.QTabWidget(self)
        self.tabWidget.setDocumentMode(True)
        self.layout().addWidget(self.tabWidget)
        
        closeButton = QtGui.QToolButton()
        closeButton.setIcon(utils.getIcon('close_button.png'))
        closeButton.setStyleSheet(
            "QToolButton { border: None } QToolButton:hover { border: 1px solid white; }")
        closeButton.clicked.connect(self.close)
        self.tabWidget.setCornerWidget(closeButton)
        
        # Fancy desing code
        self.setAutoFillBackground(True)
        self.setFrameStyle(QtGui.QFrame.Box | QtGui.QFrame.Plain);
        self.setLineWidth(1);
        p = self.palette()
        p.setColor(QtGui.QPalette.Window,p.window().color().lighter(105))
        # Unbelievably this is used for the border...
        p.setColor(QtGui.QPalette.WindowText, Qt.darkGray)
        self.setPalette(p)
        
        # Therefore we also have to change the palette of tabWidget so that the font is rendered normally.
        p = self.tabWidget.palette()
        p.setBrush(QtGui.QPalette.WindowText,self.parent().palette().windowText())
        self.tabWidget.setPalette(p)
        
        effect = QtGui.QGraphicsDropShadowEffect()
        effect.setOffset(0,0)
        effect.setBlurRadius(20)
        self.setGraphicsEffect(effect)
        