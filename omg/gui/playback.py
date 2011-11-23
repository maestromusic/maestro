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

from . import mainwindow, playerwidgets
from .. import player, utils, logging
logger = logging.getLogger("omg.playback")

def formatTime(seconds):
    seconds = int(seconds)
    minutes = seconds // 60
    return "{:0>2d}:{:0>2d}".format(minutes, seconds % 60)

class PlaybackWidget(QtGui.QDockWidget):
    """The PlaybackWidgets provides playback controls -- play/pause, stop, nex/previous song,
    seek inside the song, set volume, display title."""
    def __init__(self, parent = None, state = None, location = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('playback controls'))
        widget = QtGui.QWidget()
        self.setWidget(widget)
        
        topLayout = QtGui.QHBoxLayout()
        self.backendChooser = playerwidgets.BackendChooser(self)
        topLayout.addWidget(self.backendChooser)
        
        policy = QtGui.QSizePolicy()
        policy.setHorizontalPolicy(QtGui.QSizePolicy.Fixed)
        self.previousButton = QtGui.QPushButton(utils.getIcon("previous.png"),'',self)
        self.ppButton = PlayPauseButton(self)
        self.stopButton = QtGui.QPushButton(utils.getIcon("stop.png"),'',self)
        self.nextButton = QtGui.QPushButton(utils.getIcon("next.png"),'',self)
        
        for w in (self.backendChooser, self.previousButton, self.ppButton,
                       self.stopButton, self.nextButton):
            w.setSizePolicy(policy)
        #    widget.setSizePolicy(policy)
        self.titleLabel = QtGui.QLabel(self)
        self.titleLabel.setTextFormat(Qt.AutoText)
        self.titleLabel.setWordWrap(True)
        #topLayout.addStretch()
        topLayout.addWidget(self.titleLabel)
        #topLayout.addStretch()
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
        self.backendChooser.backendChanged.connect(self.setBackend)
        if not self.backendChooser.setCurrentProfile(state):
            self.setBackend(self.backendChooser.currentProfile())
    
    def updateSlider(self, current, total):
        if self.seekSlider.isSliderDown():
            return
        if self.seekSlider.maximum() != total:
            self.seekSlider.setRange(0, int(total))
        self.seekSlider.setValue(current)
        self.seekLabel.setText("{}-{}".format(formatTime(current), formatTime(total)))
    
    def updateCurrent(self, pos):
        current = self.backend.playlist.current
        if current is not None:
            self.titleLabel.setText("<i>{}</i>".format(current.getTitle()))
        else:
            self.titleLabel.setText(self.tr('no song selected'))
    
    def updateState(self, state):
        self.ppButton.setPlaying(state == player.PLAY)
    
    def handleStop(self):
        self.backend.setState(player.STOP)
    
    def handleConnectionChange(self, state):
        for item in self.previousButton, self.ppButton, self.stopButton, self.nextButton, self.seekSlider, self.seekLabel:
            item.setEnabled(state == player.CONNECTED)
        if state == player.CONNECTING:
            self.titleLabel.setText(self.tr("connecting..."))
        elif state == player.DISCONNECTED:
            self.titleLabel.setText(self.tr("unable to connect"))
        else:
            self.updateCurrent(self.backend.currentSong)
            self.updateState(self.backend.state)
            
    def setBackend(self, name):
        logger.debug("setBackend {}".format(name))
        if hasattr(self, 'backend'):
            self.backend.elapsedChanged.disconnect(self.updateSlider)
            self.backend.stateChanged.disconnect(self.updateState)
            self.backend.currentSongChanged.disconnect(self.updateCurrent)
            self.ppButton.stateChanged.disconnect(self.backend.setState)
            self.seekSlider.sliderMoved.disconnect(self.backend.setElapsed)
            self.previousButton.clicked.disconnect(self.backend.previousSong)
            self.nextButton.clicked.disconnect(self.backend.nextSong)
            self.backend.connectionStateChanged.disconnect(self.handleConnectionChange)
            self.backend.unregisterFrontend(self)
        if name is None:
            self.titleLabel.setText(self.tr('no backend selected'))
            return
        backend = player.instance(name)
        if backend is None:
            self.titleLabel.setText(self.tr('could not set playback profile {} because its '
                                            'backend class is not available. Did you forget ' 
                                            'to enable a plugin?').format(name))
            return
        self.backend = backend 
        self.backend.elapsedChanged.connect(self.updateSlider)
        self.backend.stateChanged.connect(self.updateState)
        self.backend.currentSongChanged.connect(self.updateCurrent)
        self.ppButton.stateChanged.connect(self.backend.setState)
        self.stopButton.clicked.connect(self.handleStop)
        self.seekSlider.sliderMoved.connect(self.backend.setElapsed)
        self.previousButton.clicked.connect(self.backend.previousSong)
        self.nextButton.clicked.connect(self.backend.nextSong)
        self.backend.registerFrontend(self)
        if self.backend.connectionState == player.CONNECTED:
            self.handleConnectionChange(player.CONNECTED)
        else:
            self.handleConnectionChange(player.DISCONNECTED)
        self.backend.connectionStateChanged.connect(self.handleConnectionChange)
        
    
    def saveState(self):
        return self.backendChooser.currentProfile()
    
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