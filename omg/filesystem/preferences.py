# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2013 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from .. import filesystem, config

class FilesystemSettings(QtGui.QWidget):
    
    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        
        layout = QtGui.QVBoxLayout()
        self.recheckButton = QtGui.QPushButton(self.tr("Force recheck of all files"))
        self.recheckButton.clicked.connect(self._handleRecheckButton)
        self.enableBox = QtGui.QCheckBox(self.tr("Enable file system monitoring"))
        self.enableBox.toggled.connect(self.recheckButton.setEnabled)
        self.enableBox.toggled.connect(self._handleEnableBox)
        self.idMethodBox = QtGui.QComboBox()
        self.idMethodBox.addItem("AcoustID fingerprint")
        self.idMethodBox.addItem("Raw PCM Hash")
        if config.options.filesystem.id_method == "ffmpeg":
            self.idMethodBox.setCurrentIndex(1)
        self.idMethodBox.currentIndexChanged.connect(self._handleIdMethodChange)
        self.scanIntervalBox = QtGui.QSpinBox()
        self.scanIntervalBox.setMinimum(0)
        self.scanIntervalBox.setMaximum(24*3600)
        self.scanIntervalLabel = QtGui.QLabel()
        self.scanIntervalText = self.tr("Rescan filesystem every {} seconds (set to 0 to disable scans).")
        self.scanDisabledText = self.tr("No periodic rescans.")
        self.scanIntervalBox.valueChanged[int].connect(self._handleIntervalChanged)
        self.scanIntervalBox.setValue(config.options.filesystem.scan_interval)
        self.enableBox.setChecked(filesystem.enabled)
            
        layout.addWidget(self.enableBox)
        intervalLayout = QtGui.QHBoxLayout()
        intervalLayout.addWidget(self.scanIntervalBox)
        intervalLayout.addWidget(self.scanIntervalLabel)
        
        idMethodLayout = QtGui.QHBoxLayout()
        idMethodLayout.addWidget(self.idMethodBox)
        idMethodLabel = QtGui.QLabel(self.tr("select file identification method (needs restart to take effect"))
        idMethodLayout.addWidget(idMethodLabel)
        layout.addLayout(idMethodLayout)
        layout.addLayout(intervalLayout)
        layout.addWidget(self.recheckButton)
        layout.addStretch()        
        self.setLayout(layout)
    
    def _handleEnableBox(self, state):
        if state:
            config.options.filesystem.disable = False
            filesystem.init()
        else:
            filesystem.shutdown()
            config.options.filesystem.disable = True
    
    def _handleIdMethodChange(self, index):
        if index == 0:
            config.options.filesystem.id_method = "acoustid"
        else:
            config.options.filesystem.id_method = "ffmpeg"
    
    def _handleRecheckButton(self):
        if filesystem.enabled:
            QtCore.QMetaObject.invokeMethod(filesystem.synchronizer,
                                            "recheck", Qt.QueuedConnection,
                                            QtCore.Q_ARG("QString", ""))
    
    def _handleIntervalChanged(self, val):
        if val == 0:
            self.scanIntervalLabel.setText(self.scanDisabledText)
        else:
            self.scanIntervalLabel.setText(self.scanIntervalText.format(val))
        config.options.filesystem.scan_interval = val
        if filesystem.enabled:
            timer = filesystem.synchronizer.eventThread.timer
            timer.stop()
            if val != 0:
                timer.setInterval(val*1000)
                timer.start()