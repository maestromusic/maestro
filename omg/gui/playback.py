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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import mainwindow
from .profiles import ProfileComboBox
from .. import player, utils, logging

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

def formatTime(seconds):
    seconds = int(seconds)
    minutes = seconds // 60
    return "{:0>2d}:{:0>2d}".format(minutes, seconds % 60)


class PlaybackWidget(QtGui.QDockWidget):
    """A dock widget providing playback controls for the selected player backend.
    """
    
    def __init__(self, parent=None, state=None, location=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('playback controls'))
        widget = QtGui.QWidget()
        self.setWidget(widget)

        if state is not None:
            backend = player.profileCategory.get(state) # may be None
        elif len(player.profileCategory.profiles) > 0:
            backend = player.profileCategory.profiles[0]
        else:
            backend = None
        topLayout = QtGui.QHBoxLayout()
        self.backendChooser = ProfileComboBox(player.profileCategory, default=backend)
        topLayout.addWidget(self.backendChooser)
        
        
        standardIcon = QtGui.qApp.style().standardIcon
        self.previousButton = QtGui.QPushButton(standardIcon(QtGui.QStyle.SP_MediaSkipBackward), '', self)
        self.ppButton = PlayPauseButton(self)
        self.stopButton = QtGui.QPushButton(standardIcon(QtGui.QStyle.SP_MediaStop), '', self)
        self.nextButton = QtGui.QPushButton(standardIcon(QtGui.QStyle.SP_MediaSkipForward), '', self)
        self.ppButton.setIconSize(QtCore.QSize(10,16))
        self.stopButton.setIconSize(QtCore.QSize(10,16))
        self.previousButton.setIconSize(QtCore.QSize(16,16))
        self.nextButton.setIconSize(QtCore.QSize(16,16))
        self.volumeLabel = VolumeLabel(self)
        policy = QtGui.QSizePolicy()
        policy.setHorizontalPolicy(QtGui.QSizePolicy.Fixed)
        for w in (self.backendChooser, self.previousButton, self.ppButton,
                       self.stopButton, self.nextButton, self.volumeLabel):
            w.setSizePolicy(policy)
            
        self.titleLabel = QtGui.QLabel(self)
        self.titleLabel.setTextFormat(Qt.AutoText)
        self.titleLabel.setWordWrap(True)
        topLayout.addWidget(self.titleLabel)
        self.seekSlider = PlaybackSlider(Qt.Horizontal, self)
        self.seekSlider.setRange(0, 1000)
        
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
        """Display elapsed and total time on the seek label."""
        self.seekLabel.setText("{}-{}".format(formatTime(value),
                                              formatTime(self.seekSlider.maximum())))
        
    def updateSlider(self, current):
        """Update the slider when the elapsed time has changed."""
        if not self.seekSlider.isSliderDown():
            if self.backend.current() is not None:
                total = self.backend.current().element.length
            else:
                total = 0
            if self.seekSlider.maximum() != total:
                self.seekSlider.setRange(0, int(total))
            self.seekSlider.setValue(current)
        self.updateSeekLabel(current)
    
    def updateTitleLabel(self, pos):
        """Display the title of the currently playing song or "stopped" on the title label."""
        current = self.backend.current()
        if current is not None:
            self.titleLabel.setText("<i>{}</i>".format(current.getTitle()))
        else:
            self.titleLabel.setText(self.tr('stopped'))
    
    def handleStateChange(self, state):
        """Update labels, buttons etc. when the playback state has changed."""
        self.ppButton.setPlaying(state == player.PLAY)
        if state == player.STOP:
            self.seekSlider.setValue(0)
            self.seekLabel.setText("")
            self.seekSlider.setEnabled(False)
        else:
            self.seekSlider.setEnabled(True)
    
    def handleConnectionChange(self, state):
        """Update GUI elements when the connection state has changed."""
        for item in self.previousButton, self.ppButton, self.stopButton, \
                    self.nextButton, self.seekSlider, self.seekLabel, self.volumeLabel:
            item.setEnabled(state is player.CONNECTED)
        if state == player.CONNECTING:
            self.titleLabel.setText(self.tr("connecting..."))
        elif state == player.DISCONNECTED:
            self.titleLabel.setText(self.tr("unable to connect"))
        else:
            self.updateTitleLabel(self.backend.current())
            self.handleStateChange(self.backend.state())
            self.volumeLabel.setVolume(self.backend.volume())
    
    def handlePlaylistChange(self, *args):
        """Enable or disable play and stop buttons when the playlist becomes empty / is filled."""
        playlistEmpty = len(self.backend.playlist.root.contents) == 0
        self.ppButton.setEnabled(not playlistEmpty)
        self.stopButton.setEnabled(not playlistEmpty)
    
    signals = [ ("self.backend.elapsedChanged", "self.updateSlider"),
                ("self.backend.volumeChanged", "self.volumeLabel.setVolume"),
                ("self.backend.stateChanged", "self.handleStateChange"),
                ("self.backend.currentChanged", "self.updateTitleLabel"),
                ("self.backend.connectionStateChanged", "self.handleConnectionChange"),
                ("self.backend.playlist.rowsInserted", "self.handlePlaylistChange"),
                ("self.backend.playlist.rowsRemoved", "self.handlePlaylistChange"),
                ("self.volumeLabel.volumeRequested", "self.backend.setVolume"),
                ("self.ppButton.stateChanged", "self.backend.setState"),
                ("self.stopButton.clicked", "self.backend.stop"),
                ("self.seekSlider.sliderMoved", "self.backend.setElapsed"),
                ("self.previousButton.clicked", "self.backend.previousSong"),
                ("self.nextButton.clicked", "self.backend.nextSong")]
    
    def setBackend(self, backend):
        """Set or change the player backend of this playback widget.
        
        *backend* may be None; in that case most of the GUI elements will be disabled.
        """
        if self.backend is not None:
            for source, sink in PlaybackWidget.signals:
                eval(source).disconnect(eval(sink))
            self.backend.unregisterFrontend(self)
        if backend is None:
            self.titleLabel.setText(self.tr("No backend selected"))
            self.backend = None
            return
        self.backend = backend
        for source, sink in PlaybackWidget.signals:
            eval(source).connect(eval(sink))
        self.backend.registerFrontend(self)
        if self.backend.connectionState == player.CONNECTED:
            self.handleConnectionChange(player.CONNECTED)
        else:
            self.handleConnectionChange(player.DISCONNECTED)
        self.handlePlaylistChange()
        self.backend.connectionStateChanged.connect(self.handleConnectionChange)
        
    def saveState(self):
        return self.backend.name if self.backend is not None else None
    
    
data = mainwindow.WidgetData(id="playback",
                             name=translate("Playback","playback"),
                             theClass=PlaybackWidget,
                             central=False,
                             dock=True,
                             default=True,
                             unique=False,
                             preferredDockArea=Qt.TopDockWidgetArea)
mainwindow.addWidgetData(data)


class PlaybackSlider(QtGui.QSlider):
    
    def mouseReleaseEvent(self, event):
        if not self.isSliderDown():
            val = QtGui.QStyle.sliderValueFromPosition(self.minimum(),
                    self.maximum(), event.x(), self.width())
            self.sliderMoved.emit(val)
        return super().mouseReleaseEvent(event)
        
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
    
    def __init__(self, parent=None):
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
