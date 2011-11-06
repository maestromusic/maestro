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
from .. import player, utils, logging
logger = logging.getLogger("omg.player")

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
        self.backendChooser.backendChanged.connect(self.setBackend)
        
        
    
    def updateSlider(self, current, total):
        if self.seekSlider.isSliderDown():
            return
        if self.seekSlider.maximum() != total:
            self.seekSlider.setRange(0, int(total))
        self.seekSlider.setValue(current)
        self.seekLabel.setText("{}-{}".format(formatTime(current), formatTime(total)))
    
    def updatePlaylist(self):
        self.playlistRoot = self.backend.currentPlaylist()
        self.updateCurrent(self.backend.currentSong)
        
    def updateCurrent(self, pos):
        if hasattr(self, "playlistRoot"):
            self.titleLabel.setTextFormat(Qt.AutoText)
            self.titleLabel.setText("Playing: <i>{}</i>".format(self.playlistRoot.fileAtOffset(pos).getTitle()))
    
    def updateState(self, state):
        self.ppButton.setPlaying(state == player.PLAY)
    
    def handleStop(self):
        QtCore.QMetaObject.invokeMethod(self.backend, "setState", Qt.QueuedConnection, QtCore.Q_ARG(int, player.STOP))
        #self.backend.setState(player.STOP)
    
    def handleConnectionChange(self, state):
        for item in self.previousButton, self.ppButton, self.stopButton, self.nextButton, self.seekSlider, self.seekLabel:
            item.setEnabled(state == player.CONNECTED)
        if state == player.CONNECTING:
            self.titleLabel.setText(self.tr("connecting..."))
        elif state == player.DISCONNECTED:
            self.titleLabel.setText(self.tr("unable to connect"))
    def setBackend(self, name):
        if hasattr(self, 'backend'):
            self.backend.elapsedChanged.disconnect(self.updateSlider)
            self.backend.stateChanged.disconnect(self.updateState)
            self.backend.playlistChanged.disconnect(self.updatePlaylist)
            self.backend.currentSongChanged.disconnect(self.updateCurrent)
            self.ppButton.stateChanged.disconnect(self.backend.setState)
            self.seekSlider.sliderMoved.disconnect(self.backend.setElapsed)
            self.previousButton.clicked.disconnect(self.backend.previous)
            self.nextButton.clicked.disconnect(self.backend.next)
            self.backend.connectionStateChanged.disconnect(self.handleConnectionChange)
        if name is None:
            self.titleLabel.setText('no backend connected')
            return
        self.backend = player.instance(name)
        self.backend.elapsedChanged.connect(self.updateSlider, Qt.QueuedConnection)
        self.backend.stateChanged.connect(self.updateState, Qt.QueuedConnection)
        self.backend.playlistChanged.connect(self.updatePlaylist, Qt.QueuedConnection)
        self.backend.currentSongChanged.connect(self.updateCurrent, Qt.QueuedConnection)
        self.ppButton.stateChanged.connect(self.backend.setState)
        self.stopButton.clicked.connect(self.handleStop)
        self.seekSlider.sliderMoved.connect(self.backend.setElapsed,Qt.QueuedConnection)
        self.previousButton.clicked.connect(self.backend.previous,Qt.QueuedConnection)
        self.nextButton.clicked.connect(self.backend.next,Qt.QueuedConnection)
        if self.backend.connected:
            self.handleConnectionChange(player.CONNECTED)
            logger.debug('1')
            self.updatePlaylist()
            logger.debug('2')
            self.update()
            logger.debug('3')
        else:
            self.handleConnectionChange(player.DISCONNECTED)
        self.backend.connectionStateChanged.connect(self.handleConnectionChange)
        
        
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