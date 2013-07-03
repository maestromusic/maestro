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

from . import mainwindow, dialogs, profiles as profilesgui, dockwidget
from .. import player, utils, logging

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)


def formatTime(seconds):
    seconds = int(seconds)
    minutes = seconds // 60
    return "{:0>2d}:{:0>2d}".format(minutes, seconds % 60)


class PlaybackWidget(dockwidget.DockWidget):
    """A dock widget providing playback controls for the selected player backend.
    """
    def __init__(self, parent=None, state=None, **args):
        super().__init__(parent, **args)
        widget = QtGui.QWidget()
        self.setWidget(widget)

        if state is not None:
            backend = player.profileCategory.get(state) # may be None
        elif len(player.profileCategory.profiles()) > 0:
            backend = player.profileCategory.profiles()[0]
        else: backend = None
        
        topLayout = QtGui.QHBoxLayout()    
        self.titleLabel = QtGui.QLabel(self)
        self.titleLabel.setTextFormat(Qt.AutoText)
        self.titleLabel.setWordWrap(True)
        topLayout.addWidget(self.titleLabel)   
        
        toolBar = QtGui.QToolBar()
        toolBar.setIconSize(QtCore.QSize(16, 16))
        standardIcon = QtGui.qApp.style().standardIcon
        self.previousButton = QtGui.QToolButton()
        self.previousButton.setIcon(standardIcon(QtGui.QStyle.SP_MediaSkipBackward))
        self.ppButton = PlayPauseButton(self)
        self.stopButton = QtGui.QToolButton()
        self.stopButton.setIcon(standardIcon(QtGui.QStyle.SP_MediaStop))
        self.nextButton = QtGui.QToolButton()
        self.nextButton.setIcon(standardIcon(QtGui.QStyle.SP_MediaSkipForward))
        self.volumeButton = VolumeButton()
        toolBar.addWidget(self.previousButton)
        toolBar.addWidget(self.ppButton)
        toolBar.addWidget(self.stopButton)
        toolBar.addWidget(self.nextButton)
        topLayout.addWidget(toolBar)
        # Keep the volume button outside the toolbar to allow for a slightly bigger icon
        topLayout.addWidget(self.volumeButton)
            
        bottomLayout = QtGui.QHBoxLayout()
        self.seekLabel = QtGui.QLabel("", self)
        self.seekSlider = PlaybackSlider(Qt.Horizontal, self)
        self.seekSlider.setRange(0, 1000)
        bottomLayout.addWidget(self.seekSlider)
        bottomLayout.addWidget(self.seekLabel)
        mainLayout = QtGui.QVBoxLayout(widget)
        mainLayout.addLayout(topLayout)
        mainLayout.addLayout(bottomLayout)
        self.seekSlider.sliderMoved.connect(self.updateSeekLabel)
        
        self.backend = None
        self.setBackend(backend)
        
    def createOptionDialog(self, parent):
        return OptionDialog(parent, self)
    
    def updateSeekLabel(self, value):
        """Display elapsed and total time on the seek label."""
        if self.current is None:
            text = ""
        elif self.current.element.length > 0:
            text = "{}-{}".format(formatTime(value), formatTime(self.seekSlider.maximum()))
        else:
            text = formatTime(value)
            self.seekSlider.setEnabled(False)
        self.seekLabel.setText(text)
        
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
        self.current = self.backend.current()
        if self.current is not None:
            self.titleLabel.setText("<i>{}</i>".format(self.current.getTitle()))
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
                    self.nextButton, self.seekSlider, self.seekLabel, self.volumeButton:
            item.setEnabled(state is player.CONNECTED)
        if state == player.CONNECTING:
            self.titleLabel.setText(self.tr("connecting..."))
        elif state == player.DISCONNECTED:
            self.titleLabel.setText(self.tr("unable to connect"))
        else:
            self.updateTitleLabel(self.backend.current())
            self.handleStateChange(self.backend.state())
            self.volumeButton.setVolume(self.backend.volume())
    
    def handlePlaylistChange(self, *args):
        """Enable or disable play and stop buttons when the playlist becomes empty / is filled."""
        playlistEmpty = len(self.backend.playlist.root.contents) == 0
        self.ppButton.setEnabled(not playlistEmpty)
        self.stopButton.setEnabled(not playlistEmpty)
    
    signals = [ ("self.backend.elapsedChanged", "self.updateSlider"),
                ("self.backend.volumeChanged", "self.volumeButton.setVolume"),
                ("self.backend.stateChanged", "self.handleStateChange"),
                ("self.backend.currentChanged", "self.updateTitleLabel"),
                ("self.backend.connectionStateChanged", "self.handleConnectionChange"),
                ("self.backend.playlist.rowsInserted", "self.handlePlaylistChange"),
                ("self.backend.playlist.rowsRemoved", "self.handlePlaylistChange"),
                ("self.volumeButton.volumeChanged", "self.backend.setVolume"),
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
        
    def saveState(self):
        return self.backend.name if self.backend is not None else None
    
    
data = mainwindow.WidgetData(id="playback",
                             name=translate("Playback","playback"),
                             icon=utils.getIcon('widgets/playback.png'),
                             theClass=PlaybackWidget,
                             central=False,
                             preferredDockArea=Qt.TopDockWidgetArea)
mainwindow.addWidgetData(data)


class PlaybackSlider(QtGui.QSlider):
    def mouseReleaseEvent(self, event):
        if not self.isSliderDown():
            val = QtGui.QStyle.sliderValueFromPosition(self.minimum(),
                    self.maximum(), event.x(), self.width())
            self.sliderMoved.emit(val)
        return super().mouseReleaseEvent(event)


class PlayPauseButton(QtGui.QToolButton):
    """Special button with two states. Depending on the state different signals (play and pause)
    are emitted when the button is clicked and the button shows different icons."""
    
    # Signals and icons used for the two states
    play = QtCore.pyqtSignal()
    pause = QtCore.pyqtSignal()
    playIcon = QtGui.qApp.style().standardIcon(QtGui.QStyle.SP_MediaPlay)
    pauseIcon = QtGui.qApp.style().standardIcon(QtGui.QStyle.SP_MediaPause)
    stateChanged = QtCore.pyqtSignal(int)
    
    def __init__(self, parent=None):
        """Initialize this button with the given parent. The button will be in pause-state."""
        super().__init__(parent)
        self.setIcon(self.playIcon)
        self.playing = False
        self.clicked.connect(lambda : self.pause.emit() if self.playing else self.play.emit() )
        self.pause.connect(lambda : self.stateChanged.emit(player.PAUSE))
        self.play.connect(lambda : self.stateChanged.emit(player.PLAY))

    def setPlaying(self,playing):
        """Set the state of this button to play if <playing> is true or pause otherwise."""
        if playing != self.playing:
            self.playing = playing
            self.setIcon(self.pauseIcon if playing else self.playIcon)
        
    
class VolumeButton(QtGui.QToolButton):
    """Button displaying an icon that visualizes the current volume. When clicked it opens a popup menu
    that allows to change the volume. Alternatively the volume can be changed using the mouse-wheel.
    The middle mouse button can be used to mute/unmute.
    """
    # Inspired by the VolumePopupButton from Amarok 2.7.1
    volumeChanged = QtCore.pyqtSignal(int)
    
    mutedIcon = utils.getIcon('volume_muted.png')
    lowIcon = utils.getIcon('volume_low.png')
    mediumIcon = utils.getIcon('volume_medium.png')
    highIcon = utils.getIcon('volume_high.png')
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIconSize(QtCore.QSize(24, 24))
        self.setContentsMargins(0,0,0,0)
        self.setAutoRaise(True)
        
        self.popup = QtGui.QWidget()
        layout = QtGui.QVBoxLayout(self.popup)
        layout.setContentsMargins(1,1,1,1)
        layout.setSpacing(0)
        self.volumeLabel = QtGui.QLabel()
        # Make sure the menu is wide enough to hold all possible values
        self.volumeLabel.setText(self.tr("{}%").format(100))
        self.volumeLabel.setMinimumWidth(self.volumeLabel.sizeHint().width())
        self.volumeLabel.setAlignment(Qt.AlignHCenter)
        layout.addWidget(self.volumeLabel, 0, Qt.AlignHCenter)
        
        self.volumeSlider = VolumeSlider()
        self.volumeSlider.setFixedHeight(170)
        self.volumeSlider.valueChanged.connect(self.setVolume)
        layout.addWidget(self.volumeSlider, 0, Qt.AlignHCenter)
        
        muteButton = QtGui.QToolButton()
        muteButton.setIcon(self.mutedIcon)
        muteButton.setIconSize(QtCore.QSize(20, 20))
        muteButton.clicked.connect(self.toggleMute)
        layout.addWidget(muteButton, 0, Qt.AlignHCenter)
        
        self.menu = QtGui.QMenu()
        action = QtGui.QWidgetAction(self)
        action.setDefaultWidget(self.popup)
        self.menu.addAction(action)
        
        # When the mouse-wheel is scrolled, the volume is changed only after a short delay.
        self._emitTimer = QtCore.QTimer(self)
        self._emitTimer.setSingleShot(True)
        self._emitTimer.timeout.connect(self._emit)
        self._newVolume = None
        
        self.volume = -1
        self.lastVolume = 0
        self.setVolume(0)
        
    def setVolume(self, volume):
        """Set the volume of this widget and emit volumeChanged."""
        if volume != self.volume:
            self.setEnabled(volume != -1)
            self.setIcon(self.volumeIcon(volume))
            if volume == 0:
                self.lastVolume = self.volume
            self.volume = volume
            text = self.tr('{}%').format(volume) if volume >= 0 else ''
            self.volumeLabel.setText(text)
            self.setToolTip(text)
            self.volumeSlider.setValue(volume)
            if volume != -1:
                self.volumeChanged.emit(volume)

    @staticmethod
    def volumeIcon(volume):
        """Maps the given volume to the appropriate icon."""
        if volume == 0:
            return VolumeButton.mutedIcon
        elif volume <= 33:
            return VolumeButton.lowIcon
        elif volume <= 66:
            return VolumeButton.mediumIcon
        return VolumeButton.highIcon
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.menu.isVisible():
                self.menu.hide()
            else:
                self.menu.exec_(self.mapToGlobal(QtCore.QPoint(0, self.height())))
            event.accept()
        elif event.button() == Qt.MidButton:
            self.toggleMute()
            event.accept()
        super().mouseReleaseEvent(event)
    
    def wheelEvent(self, event):
        # When the mouse-wheel is scrolled, the volume is changed only after a short delay.
        # _newVolume is used to store the requested value between several successive wheel-events.  
        volume = self._newVolume if self._newVolume is not None else self.volume
        req = volume + event.delta() // 20
        if req > 100:
            req = 100
        if req < 0:
            req = 0
        self._newVolume = req
        self._emitTimer.start(25)
    
    def _emit(self):
        if self._newVolume is not None:
            self.setVolume(self._newVolume)
            self._newVolume = None
            
    def toggleMute(self):
        """Toggle volume between 0 and the last volume before muting."""
        if self.volume == 0:
            self.setVolume(self.lastVolume)
        else: self.setVolume(0)
        

class VolumeSlider(QtGui.QSlider):
    """Special slider used in the menu of VolumeButton."""
    def __init__(self, parent=None):
        super().__init__(Qt.Vertical, parent)
        self.setMinimum(0)
        self.setMaximum(100)
        
    def contextMenuEvent(self, event):
        menu = QtGui.QMenu()
        for v in [100, 80, 60, 40, 20, 0]:
            menu.addAction(self.tr("{}%").format(v)).setData(v)
        action = menu.exec_(self.mapToGlobal(event.pos()))
        if action is not None:
            self.setValue(action.data())


class OptionDialog(dialogs.FancyPopup):
    """Dialog for the option button in the playlist's (dock widget) title bar.""" 
    def __init__(self, parent, playback):
        super().__init__(parent)
        layout = QtGui.QFormLayout(self)
        backendChooser = profilesgui.ProfileComboBox(player.profileCategory, default=playback.backend)
        backendChooser.profileChosen.connect(playback.setBackend)
        layout.addRow(self.tr("Backend:"), backendChooser)
        