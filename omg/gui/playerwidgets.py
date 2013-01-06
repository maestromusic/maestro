# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import itertools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from .. import player

class BackendConfigDialog(QtGui.QDialog):
    
    def __init__(self, parent = None, currentProfile = None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(self.tr("Configure Player Backends"))
        self.profileChooser = QtGui.QComboBox(self)
        self.profiles = {}
        for i, name in enumerate(player.configuredBackends):
            self.profileChooser.addItem(name)
            self.profiles[name] = i
        self.profileChooser.currentIndexChanged[str].connect(self.setCurrentProfile)
        self.newButton = QtGui.QPushButton(self.tr("new"))
        self.newButton.clicked.connect(self.newProfile)
        self.deleteButton = QtGui.QPushButton(self.tr("remove"))
        self.deleteButton.clicked.connect(self.removeCurrentProfile)
        topLayout = QtGui.QHBoxLayout()
        topLayout.addWidget(self.profileChooser, stretch = 1)
        topLayout.addWidget(self.newButton)
        topLayout.addWidget(self.deleteButton)
        
        self.classChooser = QtGui.QComboBox(self)
        self.classes = {}
        for i, name in enumerate(player.backendClasses):
            self.classChooser.addItem(name)
            self.classes[name] = i
        self.classChooser.currentIndexChanged[str].connect(self.changeConfigureWidget)
        self.nameEdit = QtGui.QLineEdit(self)
        self.nameEdit.editingFinished.connect(self.renameCurrentLayout)
        self.nameEdit.setFocus()
        secondLayout = QtGui.QHBoxLayout()
        secondLayout.addWidget(QtGui.QLabel(self.tr("Profile name:")))
        secondLayout.addWidget(self.nameEdit)
        secondLayout.addWidget(QtGui.QLabel(self.tr("Backend:")))
        secondLayout.addWidget(self.classChooser)
        
        
        controlBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Close)

        
        controlBox.rejected.connect(self.ensureConfigIsStored)
        controlBox.rejected.connect(self.accept)
        mainLayout = QtGui.QVBoxLayout(self)
        mainLayout.addLayout(topLayout, stretch = 0)
        mainLayout.addLayout(secondLayout, stretch = 0)
        mainLayout.addWidget(controlBox, stretch = 1)
        self.mainLayout = mainLayout
        self.classConfigWidget = None
        self.setCurrentProfile(currentProfile)
    
    def renameCurrentLayout(self):
        text = self.nameEdit.text()
        if text == '':
            return
        if self.profileChooser.currentText() == text:
            return
        player.renameProfile(self.profileChooser.currentText(), text)
        self.profileChooser.setItemText(self.profileChooser.currentIndex(), text)
        self.storedProfile = text
    
    def removeCurrentProfile(self):
        name = self.profileChooser.currentText()
        self.profileChooser.removeItem(self.profileChooser.currentIndex())
        player.removeProfile(name)
        self.profiles = {}
        for i, name in enumerate(player.configuredBackends):
            self.profiles[name] = i
          
    def setCurrentProfile(self, name):
        self.nameEdit.setEnabled(bool(name))
        self.classChooser.setEnabled(bool(name))
        self.deleteButton.setEnabled(bool(name))
        if self.classConfigWidget is not None:
            self.ensureConfigIsStored()
            self.mainLayout.removeWidget(self.classConfigWidget)
            self.classConfigWidget.setVisible(False)
        if name:
            backend = player.configuredBackends[name]
            self.classChooser.setCurrentIndex(self.classes[backend])
            self.changeConfigureWidget(backend)            
            self.nameEdit.setText(name)
        self.storedProfile = name
    
    def ensureConfigIsStored(self):
        if self.classConfigWidget is not None:
            self.classConfigWidget.storeProfile(self.storedProfile)
    def changeConfigureWidget(self, backend):
        self.classConfigWidget = player.backendClasses[backend].configWidget(self.profileChooser.currentText())
        self.mainLayout.insertWidget(2, self.classConfigWidget)
        
    def newProfile(self):
        name= self.tr("newProfile")
        if name in self.profiles:
            for i in itertools.count():
                if name + str(i) not in self.profiles:
                    name = name + str(i)
                    break
        backend = next(iter(player.backendClasses))
        player.addProfile(name, backend)
        self.profiles[name] = len(self.profiles)
        self.profileChooser.addItem(name)
        self.profileChooser.setCurrentIndex(self.profileChooser.count()-1)
    