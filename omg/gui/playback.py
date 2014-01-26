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

from PyQt4 import QtCore, QtGui, QtSvg
from PyQt4.QtCore import Qt

from . import mainwindow, dialogs, dockwidget
from .preferences import profiles as profilesgui
from .. import player, utils, logging, strutils
from ..core import levels

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)
renderer = QtSvg.QSvgRenderer(":omg/playback.svg")

ICON_SIZE = 16

def renderPixmap(name, width, height):
    """Load the object with the given name from playback.svg and render it into a pixmap of the given
    dimensions. Return that pixmap."""
    pixmap = QtGui.QPixmap(width, height)
    pixmap.fill(Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    renderer.render(painter, name)
    painter.end()
    return pixmap


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
        self.titleLabel.setSizePolicy(QtGui.QSizePolicy.Ignored, QtGui.QSizePolicy.Ignored)
        self.titleLabel.linkActivated.connect(lambda: self.backend.connectBackend())
        topLayout.addWidget(self.titleLabel)   
        
        self.skipBackwardButton = QtGui.QToolButton()
        self.skipBackwardButton.setIcon(QtGui.QIcon(renderPixmap("media_skip_backward", ICON_SIZE, 10)))
        self.ppButton = PlayPauseButton(self)
        self.stopButton = QtGui.QToolButton()
        self.stopButton.setIcon(QtGui.QIcon(renderPixmap("media_playback_stop", ICON_SIZE, ICON_SIZE)))
        self.skipForwardButton = QtGui.QToolButton()
        self.skipForwardButton.setIcon(QtGui.QIcon(renderPixmap("media_skip_forward", ICON_SIZE, 10)))
        self.volumeButton = VolumeButton()
        
        for button in (self.skipBackwardButton, self.ppButton, self.stopButton,
                       self.skipForwardButton, self.volumeButton):
            button.setAutoRaise(True)
            topLayout.addWidget(button)
            
        bottomLayout = QtGui.QHBoxLayout()
        self.seekLabel = QtGui.QLabel("", self)
        self.seekSlider = SeekSlider(self)
        bottomLayout.addWidget(self.seekSlider)
        bottomLayout.addWidget(self.seekLabel)
        mainLayout = QtGui.QVBoxLayout(widget)
        mainLayout.addLayout(topLayout)
        mainLayout.addLayout(bottomLayout)
        self.seekSlider.sliderMoved.connect(self.updateSeekLabel)
        
        self.backend = None
        self.setBackend(backend)
        
        levels.real.connect(self.handleLevelChange)
        
    def createOptionDialog(self, parent):
        return OptionDialog(parent, self)
    
    def updateSeekLabel(self, value):
        """Display elapsed and total time on the seek label."""
        current = self.backend.current()
        if current is None:
            text = ""
        elif current.element.length > 0:
            text = "{} - {}".format(strutils.formatLength(value),
                                  strutils.formatLength(self.seekSlider.maximum()))
        else:
            text = strutils.formatLength(value)
            self.seekSlider.setEnabled(False)
        self.seekLabel.setText(text)
        
    def updateSlider(self, elapsed):
        """Update the slider when the elapsed time has changed."""
        if not self.seekSlider.isSliderDown():
            if self.backend.current() is not None:
                total = self.backend.current().element.length
            else:
                total = 0
            if self.seekSlider.maximum() != total:
                self.seekSlider.setRange(0, int(total))
            self.seekSlider.setValue(elapsed)
        self.updateSeekLabel(elapsed)
    
    def updateTitleLabel(self):
        """Display the title of the currently playing song."""
        if self.backend.connectionState == player.CONNECTED:
            current = self.backend.current()
            if current is not None:
                self.titleLabel.setText(current.getTitle())
            else: self.titleLabel.setText('')
    
    
    def handleStateChange(self, state):
        """Update labels, buttons etc. when the playback state has changed."""
        self.ppButton.setPlaying(state == player.PLAY)
        if state == player.STOP:
            self.updateSlider(0)
            self.seekSlider.setEnabled(False)
        else:
            self.seekSlider.setEnabled(True)
    
    def handleConnectionChange(self, state):
        """Update GUI elements when the connection state has changed."""
        for item in self.skipBackwardButton, self.ppButton, self.stopButton, \
                    self.skipForwardButton, self.seekSlider, self.seekLabel, self.volumeButton:
            item.setEnabled(state is player.CONNECTED)
        if state == player.CONNECTING:
            self.titleLabel.setText(self.tr("connecting..."))
        elif state == player.DISCONNECTED:
            self.titleLabel.setText(self.tr('Connection failed. <a href="#connect">Retry?</a>'))
        else:
            self.updateTitleLabel()
            self.updateSlider(self.backend.elapsed())
            self.handleStateChange(self.backend.state())
            self.volumeButton.setVolume(self.backend.volume())
    
    def handleFlagsChange(self, flags=None):
        """React to changes of the backend's flags."""
        # In random mode, there is no reasonable meaning for this button
        self.skipBackwardButton.setEnabled(self.backend.getRandom() == player.RANDOM_OFF)
        
    def handleLevelChange(self, event):
        """Handle changes of the real-level."""
        current = self.backend.current()
        if current is not None and current.element.id in event.dataIds:
            self.updateTitleLabel() # title may have changed
            
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
                ("self.backend.flagsChanged", "self.handleFlagsChange"),
                ("self.backend.playlist.rowsInserted", "self.handlePlaylistChange"),
                ("self.backend.playlist.rowsRemoved", "self.handlePlaylistChange"),
                ("self.volumeButton.volumeChanged", "self.backend.setVolume"),
                ("self.ppButton.stateChanged", "self.backend.setState"),
                ("self.stopButton.clicked", "self.backend.stop"),
                ("self.seekSlider.sliderMoved", "self.backend.setElapsed"),
                ("self.skipBackwardButton.clicked", "self.backend.skipBackward"),
                ("self.skipForwardButton.clicked", "self.backend.skipForward")]
    
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
            self.setWindowTitle(self.tr("Playback"))
            return
        self.backend = backend
        self.seekSlider.backend = backend
        for source, sink in PlaybackWidget.signals:
            eval(source).connect(eval(sink))
        self.backend.registerFrontend(self)
        if self.backend.connectionState == player.CONNECTED:
            self.handleConnectionChange(player.CONNECTED)
        else:
            self.handleConnectionChange(player.DISCONNECTED)
        self.setWindowTitle("Playback [{}]".format(backend.name))
        self.handlePlaylistChange()
        self.handleFlagsChange()
        
    def saveState(self):
        return self.backend.name if self.backend is not None else None
    
    
data = mainwindow.WidgetData(id="playback",
                             name=translate("Playback", "playback"),
                             icon=utils.getIcon('widgets/playback.png'),
                             theClass=PlaybackWidget,
                             central=False,
                             preferredDockArea=Qt.LeftDockWidgetArea)
mainwindow.addWidgetData(data)


class OptionDialog(dialogs.FancyPopup):
    """Dialog for the option button in the playlist's (dock widget) title bar.""" 
    def __init__(self, parent, playback):
        super().__init__(parent)
        layout = QtGui.QVBoxLayout(self)
        hLayout = QtGui.QHBoxLayout()
        layout.addLayout(hLayout)
        hLayout.addWidget(QtGui.QLabel(self.tr("Backend:")))
        backendChooser = profilesgui.ProfileComboBox(player.profileCategory, default=playback.backend)
        backendChooser.profileChosen.connect(playback.setBackend)
        backendChooser.profileChosen.connect(self.setBackend)
        hLayout.addWidget(backendChooser)
        hLayout.addStretch()
        
        self.repeatBox = QtGui.QCheckBox(self.tr("Repeat playlist"))
        layout.addWidget(self.repeatBox)
        
        hLayout = QtGui.QHBoxLayout()
        layout.addLayout(hLayout)
        hLayout.addWidget(QtGui.QLabel(self.tr("Random:")))
        randomOffButton = QtGui.QRadioButton(self.tr("Off"))
        hLayout.addWidget(randomOffButton)
        randomOnButton = QtGui.QRadioButton(self.tr("On"))
        hLayout.addWidget(randomOnButton)
        randomWorksButton = QtGui.QRadioButton(self.tr("Works"))
        hLayout.addWidget(randomWorksButton)
        helpLabel = QtGui.QLabel()
        helpLabel.setPixmap(utils.getPixmap('help-browser.png'))
        helpLabel.setToolTip(self.tr("In 'Random Works' mode the playlist is played in random order,\n "
                                     "but containers of type 'Work' are kept together. Use this to e.g.\n "
                                     "play symphonies in random order, without mixing the movements."))
        hLayout.addWidget(helpLabel)
        
        self.randomButtonGroup = QtGui.QButtonGroup()
        self.randomButtonGroup.addButton(randomOffButton, player.RANDOM_OFF)
        self.randomButtonGroup.addButton(randomOnButton, player.RANDOM_ON)
        self.randomButtonGroup.addButton(randomWorksButton, player.RANDOM_WORKS)
        
        layout.addStretch()
        
        self.backend = -1
        self.setBackend(playback.backend)
        
    def setBackend(self, backend):
        if backend != self.backend:
            if self.backend is not None and self.backend != -1:
                self.repeatBox.toggled.disconnect(self.backend.setRepeating)
                self.randomButtonGroup.buttonClicked[int].disconnect(self.backend.setRandom)
            self.backend = backend
            self.repeatBox.setEnabled(backend is not None)
            for button in self.randomButtonGroup.buttons():
                button.setEnabled(backend is not None)
                
            if backend is not None:
                self.repeatBox.setChecked(backend.isRepeating())
                self.repeatBox.toggled.connect(backend.setRepeating)
                self.randomButtonGroup.button(backend.getRandom()).setChecked(True)
                self.randomButtonGroup.buttonClicked[int].connect(backend.setRandom)


class PlayPauseButton(QtGui.QToolButton):
    """Special button with two states. Depending on the state different signals (play and pause)
    are emitted when the button is clicked and the button shows different icons."""
    
    # Signals and icons used for the two states
    play = QtCore.pyqtSignal()
    pause = QtCore.pyqtSignal()
    playIcon = QtGui.QIcon(renderPixmap("media_playback_start", ICON_SIZE, ICON_SIZE))
    pauseIcon = QtGui.QIcon(renderPixmap("media_playback_pause", ICON_SIZE, ICON_SIZE))
    stateChanged = QtCore.pyqtSignal(int)
    
    def __init__(self, parent=None):
        """Initialize this button with the given parent. The button will be in pause-state."""
        super().__init__(parent)
        self.setIcon(self.playIcon)
        self.playing = False
        self.clicked.connect(lambda: self.pause.emit() if self.playing else self.play.emit() )
        self.pause.connect(lambda: self.stateChanged.emit(player.PAUSE))
        self.play.connect(lambda: self.stateChanged.emit(player.PLAY))

    def setPlaying(self, playing):
        """Set the state of this button to play if *playing* is true or pause otherwise."""
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
    
    mutedIcon = utils.getIcon("audio_volume_muted")
    lowIcon = utils.getIcon("audio_volume_low")
    mediumIcon = utils.getIcon("audio_volume_medium")
    highIcon = utils.getIcon("audio_volume_high")
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIconSize(QtCore.QSize(24, 24))
        self.setContentsMargins(0,0,0,0)
        
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
            #self.setEnabled(volume != -1)
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
        self.setRange(0, 100)
        
    def contextMenuEvent(self, event):
        menu = QtGui.QMenu()
        for v in [100, 80, 60, 40, 20, 0]:
            menu.addAction(self.tr("{}%").format(v)).setData(v)
        action = menu.exec_(self.mapToGlobal(event.pos()))
        if action is not None:
            self.setValue(action.data())


class SeekSlider(QtGui.QSlider):
    """Fancy seek slider. This is a Python port of the TimeSlider from Amarok 2.7.1."""
    sliderHeight = 14
    knobSize = 14
    
    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setRange(0, 1000)
        self.setFocusPolicy(Qt.NoFocus)
        self.backend = None # backend is necessary to get current track
        
    def mouseReleaseEvent(self, event):
        if not self.isSliderDown():
            val = QtGui.QStyle.sliderValueFromPosition(self.minimum(),
                    self.maximum(), event.x(), self.width())
            self.sliderMoved.emit(val)
        return super().mouseReleaseEvent(event)
    
    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setClipRegion(event.region())
        
        fraction = self.value() / self.maximum() if self.maximum() > 0 else 0
        left = int(round((self.width() - self.knobSize) * fraction))
        top = (self.height() - self.sliderHeight) // 2
        knobRect = QtCore.QRect(left, top+1, self.knobSize, self.knobSize)
        
        pt = QtCore.QPoint(0, top)
        p.drawPixmap(pt, renderPixmap("progress_slider_left", self.sliderHeight, self.sliderHeight))

        pt = QtCore.QPoint(self.sliderHeight, top)
        midRect = QtCore.QRect(pt, QtCore.QSize(self.width() - self.sliderHeight*2, self.sliderHeight))
        p.drawTiledPixmap(midRect, renderPixmap("progress_slider_mid", 32, self.sliderHeight))
        
        pt = midRect.topRight() + QtCore.QPoint(1, 0)
        p.drawPixmap(pt, renderPixmap("progress_slider_right", self.sliderHeight, self.sliderHeight))

        # draw the played background.
        playedBarHeight = self.sliderHeight - 6

        sizeOfLeftPlayed = max(0, min(knobRect.x()-2, playedBarHeight))

        if sizeOfLeftPlayed > 0:
            tl = QtCore.QPoint(3, top+4)
            br = QtCore.QPoint(knobRect.x() + 5, tl.y() + playedBarHeight - 1)
            p.drawPixmap(tl.x(), tl.y(),
                         renderPixmap("progress_slider_played_left", playedBarHeight, playedBarHeight),
                         0, 0, sizeOfLeftPlayed + 3, playedBarHeight) 
            tl = QtCore.QPoint(tl.x() + playedBarHeight, tl.y())
            if sizeOfLeftPlayed >= playedBarHeight:
                p.drawTiledPixmap(QtCore.QRect(tl, br),
                                  renderPixmap("progress_slider_played_mid", 32, playedBarHeight))

        if self.isEnabled():
            # Draw the knob (handle)
            if self.underMouse() and knobRect.contains(self.mapFromGlobal(QtGui.QCursor.pos())):
                file = "slider_knob_200911_active"
            else: file = "slider_knob_200911"
            p.drawPixmap(knobRect.topLeft(),
                         renderPixmap(file, knobRect.width(), knobRect.height()))

        p.end()
        
    def event(self, event):
        if event.type() == QtCore.QEvent.ToolTip and self.backend is not None \
                and self.backend.current() is not None:
            seconds = int(event.x() / self.width() * self.backend.current().element.length)
            self.setToolTip(self.tr("Jump to {}").format(strutils.formatLength(seconds)))
            
        return super().event(event)
