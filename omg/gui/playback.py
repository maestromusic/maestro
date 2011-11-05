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

def formatTime(seconds):
    seconds = int(seconds)
    minutes = seconds // 60
    return "{:0>2d}:{:0>2d}".format(minutes, seconds % 60)

class PlaybackWidget(QtGui.QDockWidget):
    def __init__(self, parent = None, state = None, location = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('player controls'))
        widget = QtGui.QWidget()
        self.setWidget(widget)
        
        topLayout = QtGui.QHBoxLayout()
        
        self.backendChooser = player.BackendChooser(self)
        topLayout.addWidget(self.backendChooser)
        
        self.previousButton = QtGui.QPushButton(utils.getIcon("previous.png"),'',self)
        self.ppButton = PlayPauseButton(self)
        self.stopButton = QtGui.QPushButton(utils.getIcon("stop.png"),'',self)
        self.nextButton = QtGui.QPushButton(utils.getIcon("next.png"),'',self)
        
        self.titleLabel = QtGui.QLabel(self)
        topLayout.addStretch()
        topLayout.addWidget(self.titleLabel)
        topLayout.addStretch()
        self.seekSlider = QtGui.QSlider(Qt.Horizontal,self)
        self.seekSlider.setRange(0,1000)
        self.seekSlider.setTracking(False)
        
        bottomLayout = QtGui.QHBoxLayout()
        self.seekLabel = QtGui.QLabel("0-0", self)
        topLayout.addWidget(self.previousButton)
        topLayout.addWidget(self.ppButton)
        topLayout.addWidget(self.stopButton)
        topLayout.addWidget(self.nextButton)
        bottomLayout.addWidget(self.seekSlider)
        bottomLayout.addWidget(self.seekLabel)
        
        mainLayout = QtGui.QVBoxLayout(widget)
        mainLayout.addLayout(topLayout)
        mainLayout.addLayout(bottomLayout)
        self.setBackend(self.backendChooser.currentProfile())
        
        
    
    def updateSlider(self, current, total):
        if self.seekSlider.isSliderDown():
            return
        if self.seekSlider.maximum() != total:
            self.seekSlider.setRange(0, int(total))
        self.seekSlider.setValue(current)
        self.seekLabel.setText("{}-{}".format(formatTime(current), formatTime(total)))
    
    def updatePlaylist(self):
        self.playlistRoot = self.backend.currentPlaylist()
        
    def updateCurrent(self, pos):
        print('update current -- {}'.format(pos))
        if hasattr(self, "playlistRoot"):
            self.titleLabel.setTextFormat(Qt.AutoText)
            self.titleLabel.setText("Playing: <i>{}</i>".format(self.playlistRoot.fileAtOffset(pos).getTitle()))
    def setBackend(self, name):
        if hasattr(self, 'backend'):
            self.disconnect(self.backend) #TODO: disconnect signals
            self.backend.disconnect(self)
        
        if name is None:
            self.titleLabel.setText('no backend connected')
            return
        self.backend = player.instance(name)
        
        self.backend.elapsedChanged.connect(self.updateSlider)
        self.backend.stateChanged.connect(lambda state: self.ppButton.setPlaying(state == player.PLAY))
        self.backend.playlistChanged.connect(self.updatePlaylist)
        self.backend.currentSongChanged.connect(self.updateCurrent)
        self.ppButton.stateChanged.connect(self.backend.setState)
        self.stopButton.clicked.connect(lambda: self.backend.setState(player.STOP))
        self.seekSlider.sliderMoved.connect(self.backend.setElapsed)
        self.previousButton.clicked.connect(self.backend.previous)
        self.nextButton.clicked.connect(self.backend.next)
        self.update()
        
    def update(self):
        print(self.backend.state == player.PLAY)
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
    stateChanged = QtCore.pyqtSignal(int)
    
    def __init__(self,parent):
        """Initialize this button with the given parent. The button will be in pause-state."""
        QtGui.QPushButton.__init__(self,self.playIcon,'',parent)
        self.playing = False
        self.clicked.connect(lambda : self.pause.emit() if self.playing else self.play.emit() )
        self.pause.connect(lambda : self.stateChanged.emit(player.PAUSE))
        self.play.connect(lambda : self.stateChanged.emit(player.PLAY))

    def setPlaying(self,playing):
        """Set the state of this button to play if <playing> is true or pause otherwise."""
        if playing != self.playing:
            self.playing = playing
            self.setIcon(self.pauseIcon if playing else self.playIcon)