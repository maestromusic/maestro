# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

from . import mainwindow, playerwidgets, profiles as profilesgui
from .. import player, utils, logging

translate = QtCore.QCoreApplication.translate

logger = logging.getLogger(__name__)

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

        if state is not None:
            backend = player.profileCategory.get(state) # may be None
        elif len(player.profileCategory.profiles) > 0:
            backend = player.profileCategory.profiles[0]
        else: backend = None
        topLayout = QtGui.QHBoxLayout()
        self.backendChooser = profilesgui.ProfileComboBox(player.profileCategory,
                                                          default=backend)
        topLayout.addWidget(self.backendChooser)
        
        policy = QtGui.QSizePolicy()
        policy.setHorizontalPolicy(QtGui.QSizePolicy.Fixed)
        standardIcon = QtGui.qApp.style().standardIcon
        self.previousButton = QtGui.QPushButton(standardIcon(QtGui.QStyle.SP_MediaSkipBackward),'',self)
        
        self.ppButton = PlayPauseButton(self)
        
        self.stopButton = QtGui.QPushButton(standardIcon(QtGui.QStyle.SP_MediaStop),'',self)
        self.nextButton = QtGui.QPushButton(standardIcon(QtGui.QStyle.SP_MediaSkipForward),'',self)
        self.ppButton.setIconSize(QtCore.QSize(10,16))
        self.stopButton.setIconSize(QtCore.QSize(10,16))
        self.previousButton.setIconSize(QtCore.QSize(16,16))
        self.nextButton.setIconSize(QtCore.QSize(16,16))
        self.volumeLabel = VolumeLabel(self)
        for w in (self.backendChooser, self.previousButton, self.ppButton,
                       self.stopButton, self.nextButton, self.volumeLabel):
            w.setSizePolicy(policy)
            
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
        self.seekLabel = QtGui.QLabel("", self)
        topLayout.addWidget(self.previousButton)
        topLayout.addWidget(self.ppButton)
        topLayout.addWidget(self.stopButton)
        topLayout.addWidget(self.nextButton)
        topLayout.addWidget(self.volumeLabel)
        bottomLayout.addWidget(self.seekSlider)
        bottomLayout.addWidget(self.seekLabel)
        mainLayout = QtGui.QVBoxLayout(widget)
        mainLayout.addLayout(topLayout)
        mainLayout.addLayout(bottomLayout)
        self.backendChooser.profileChosen.connect(self.setBackend)
        self.seekSlider.sliderMoved.connect(self.updateSeekLabel)
        
        self.backend = None
        self.setBackend(backend)
    
    def updateSeekLabel(self, value):
        self.seekLabel.setText("{}-{}".format(formatTime(value), formatTime(self.seekSlider.maximum())))
        
    def updateSlider(self, current):
        if not self.seekSlider.isSliderDown():
            if self.backend.current() is not None:
                total = self.backend.current().element.length
            else:
                total = 0
            if self.seekSlider.maximum() != total:
                self.seekSlider.setRange(0, int(total))
            self.seekSlider.setValue(current)
        self.updateSeekLabel(current)
    
    def updateCurrent(self, pos):
        current = self.backend.current()
        if current is not None:
            self.titleLabel.setText("{}: <i>{}</i>".format(self.tr("Current song"), current.getTitle()))
        else:
            self.titleLabel.setText(self.tr('no song selected'))
    
    def updateState(self, state):
        self.ppButton.setPlaying(state == player.PLAY)
        if state == player.STOP:
            self.seekSlider.setValue(0)
            self.seekLabel.setText("")
            self.seekSlider.setEnabled(False)
        else:
            self.seekSlider.setEnabled(True)
    
    def handleStop(self):
        self.backend.setState(player.STOP)
    
    def handleConnectionChange(self, state):
        for item in self.previousButton, self.ppButton, self.stopButton, \
                    self.nextButton, self.seekSlider, self.seekLabel, self.volumeLabel:
            item.setEnabled(state is player.CONNECTED)
        if state == player.CONNECTING:
            self.titleLabel.setText(self.tr("connecting..."))
        elif state == player.DISCONNECTED:
            self.titleLabel.setText(self.tr("unable to connect"))
        else:
            self.updateCurrent(self.backend.current())
            self.updateState(self.backend.state())
            self.volumeLabel.setVolume(self.backend.volume())
            
    def setBackend(self, backend):
        if self.backend is not None:
            self.backend.elapsedChanged.disconnect(self.updateSlider)
            self.backend.volumeChanged.disconnect(self.volumeLabel.setVolume)
            self.volumeLabel.volumeRequested.disconnect(self.backend.setVolume)
            self.backend.stateChanged.disconnect(self.updateState)
            self.backend.currentChanged.disconnect(self.updateCurrent)
            self.ppButton.stateChanged.disconnect(self.backend.setState)
            self.seekSlider.sliderMoved.disconnect(self.backend.setElapsed)
            self.previousButton.clicked.disconnect(self.backend.previousSong)
            self.nextButton.clicked.disconnect(self.backend.nextSong)
            self.backend.connectionStateChanged.disconnect(self.handleConnectionChange)
            self.backend.unregisterFrontend(self)
        if backend is None:
            self.titleLabel.setText(self.tr("No backend selected"))
            self.backend = None
            return
        self.backend = backend 
        self.backend.elapsedChanged.connect(self.updateSlider)
        self.backend.stateChanged.connect(self.updateState)
        self.backend.currentChanged.connect(self.updateCurrent)
        self.ppButton.stateChanged.connect(self.backend.setState)
        self.stopButton.clicked.connect(self.handleStop)
        self.seekSlider.sliderMoved.connect(self.backend.setElapsed)
        self.previousButton.clicked.connect(self.backend.previousSong)
        self.nextButton.clicked.connect(self.backend.nextSong)
        self.volumeLabel.volumeRequested.connect(self.backend.setVolume)
        self.backend.volumeChanged.connect(self.volumeLabel.setVolume)
        self.backend.registerFrontend(self)
        if self.backend.connectionState == player.CONNECTED:
            self.handleConnectionChange(player.CONNECTED)
        else:
            self.handleConnectionChange(player.DISCONNECTED)
        self.backend.connectionStateChanged.connect(self.handleConnectionChange)
        
    def saveState(self):
        return self.backend.name if self.backend is not None else None
    
    
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
    playIcon = QtGui.qApp.style().standardIcon(QtGui.QStyle.SP_MediaPlay)
    pauseIcon = QtGui.qApp.style().standardIcon(QtGui.QStyle.SP_MediaPause)
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
            
class VolumeLabel(QtGui.QLabel):
    """Special label displaying an icon that visualizes the current volume setting and
    emits signals when clicked (which means mute/unmute) or mouse-scrolled (to change
    volume)."""
   
    volumeRequested = QtCore.pyqtSignal(int)
    
    mutedIcon = utils.getPixmap('volume_muted.png')
    lowIcon = utils.getPixmap('volume_low.png')
    mediumIcon = utils.getPixmap('volume_medium.png')
    highIcon = utils.getPixmap('volume_high.png')
    
    def __init__(self,parent=None):
        """Initialize this label with the given parent."""
        QtGui.QLabel.__init__(self, parent)
        self.volume = -1
        self.lastVolume = 0
        self.setVolume(0)
        self.emitTimer = QtCore.QTimer(self)
        self.emitTimer.setSingleShot(True)
        self.emitTimer.timeout.connect(self._emit)
        self.changeRequest = None
   
    def setVolume(self, volume):
        """Display the appropriate icon for the given volume."""
        if volume != self.volume:
            self.setVisible(volume != -1)
            self.setPixmap(self.volumeIcon(volume))
            if volume == 0:
                self.lastVolume = self.volume
            self.volume = volume
            self.setToolTip(self.tr('{}%').format(volume))
        
    @staticmethod
    def volumeIcon(volume):
        """Maps the given volume to the appropriate icon."""
        if volume == 0:
            return VolumeLabel.mutedIcon
        elif volume <= 33:
            return VolumeLabel.lowIcon
        elif volume <= 66:
            return VolumeLabel.mediumIcon
        return VolumeLabel.highIcon
       
    def mousePressEvent(self, event):
        if self.volume == 0:
            self.volumeRequested.emit(self.lastVolume)
        else:
            self.volumeRequested.emit(0)
        event.accept()
    
    def _emit(self):
        if self.changeRequest is not None:
            self.volumeRequested.emit(self.changeRequest)
            self.changeRequest = None
            
    def wheelEvent(self, event):
        volume = self.changeRequest if self.changeRequest is not None else self.volume
        req = volume + event.delta()//20
        if req > 100:
            req = 100
        if req < 0:
            req = 0
        self.changeRequest = req
        self.emitTimer.start(25)