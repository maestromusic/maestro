# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

translate = QtCore.QCoreApplication.translate

from . import mainwindow
from .. import player, utils

class PlaybackWidget(QtGui.QDockWidget):
    def __init__(self, parent = None, state = None, location = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('player controls'))
        widget = QtGui.QWidget()
        self.setWidget(widget)
        
        layout = QtGui.QHBoxLayout(widget)
        
        self.backendChooser = QtGui.QComboBox()
        for name, pl in player.players.items():
            self.backendChooser.addItem(name, pl)
        layout.addWidget(self.backendChooser)
        
        self.previousButton = QtGui.QPushButton(utils.getIcon("previous.png"),'',self)
        self.ppButton = PlayPauseButton(self)
        self.stopButton = QtGui.QPushButton(utils.getIcon("stop.png"),'',self)
        self.nextButton = QtGui.QPushButton(utils.getIcon("next.png"),'',self)
        
        self.seekSlider = QtGui.QSlider(Qt.Horizontal,self)
        self.seekSlider.setRange(0,1000)
        self.seekSlider.setTracking(False)
        
        layout.addWidget(self.previousButton)
        layout.addWidget(self.ppButton)
        layout.addWidget(self.stopButton)
        layout.addWidget(self.nextButton)
        layout.addWidget(self.seekSlider)
        
        self.setBackend(self.backendChooser.itemData(0))
    
    def setBackend(self, backend):
        if hasattr(self, 'backend'):
            pass #TODO: disconnect signals
        self.backend = backend
        self.backend.elapsedChanged.connect(self.seekSlider.setValue)
        self.backend.stateChanged.connect(lambda state: self.ppButton.setPlaying(state == player.PLAY))
        
    def update(self):
        self.ppButton.setPlaying(self.backend.state == player.PLAY)
        self.seekSlider.setValue(int(self.backend.elapsed))
        
data = mainwindow.WidgetData(id = "playback",
                             name = translate("Playback","playback"),
                             theClass = PlaybackWidget,
                             central = False,
                             dock = True,
                             default = True,
                             unique = False,
                             preferredDockArea = Qt.TopDockWidgetArea)
mainwindow.addWidgetData(data)

class PlayPauseButton(QtGui.QPushButton):
    """Special button with two states. Depending on the state different signals (play and pause)
    are emitted when the button is clicked and the button shows different icons."""
    
    # Signals and icons used for the two states
    play = QtCore.pyqtSignal()
    pause = QtCore.pyqtSignal()
    playIcon = utils.getIcon("play.png")
    pauseIcon = utils.getIcon("pause.png")
    
    def __init__(self,parent):
        """Initialize this button with the given parent. The button will be in pause-state."""
        QtGui.QPushButton.__init__(self,self.playIcon,'',parent)
        self.playing = False
        self.clicked.connect(lambda : self.pause.emit() if self.playing else self.play.emit() )

    def setPlaying(self,playing):
        """Set the state of this button to play if <playing> is true or pause otherwise."""
        if playing != self.playing:
            self.playing = playing
            self.setIcon(self.pauseIcon if playing else self.playIcon)