# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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

import enum
import functools

from PyQt5 import QtCore, QtGui, QtWidgets, QtSvg
from PyQt5.QtCore import Qt

from maestro import player, utils
from maestro.core import levels
from maestro.gui import actions, mainwindow, dialogs
from maestro.gui.preferences import profiles as profilesgui

translate = QtCore.QCoreApplication.translate
renderer = QtSvg.QSvgRenderer(":maestro/playback.svg")
ICON_SIZE = 16


class PlayCommand(enum.Enum):
    PlayPause = 'playPause'
    Stop = 'stop'
    SkipForward = 'skipForward'
    SkipBackward = 'skipBackward'
    AddMark = 'addMark'

    def label(self):
        if self is PlayCommand.PlayPause:
            return translate('PlayCommand', 'Toggle play / pause')
        elif self is PlayCommand.Stop:
            return translate('PlayCommand', 'Stop')
        elif self is PlayCommand.SkipForward:
            return translate('PlayCommand', 'Next track')
        elif self is PlayCommand.SkipBackward:
            return translate('PlayCommand', 'Previous track')
        else:
            return translate('PlayCommand', 'addMark')


class PlayControlAction(actions.GlobalAction):
    """Global actions for controlling playback, like play/pause, stop, skip, addMark"""

    def __init__(self, parent, command: PlayCommand):
        super().__init__(parent, identifier=command.value, label=command.label())
        self.command = command

    def doAction(self):

        currentWidget = mainwindow.mainWindow.currentWidgets.get('playback')
        currentBackend = None if currentWidget is None else currentWidget.backend
        backends = [b for b in player.profileCategory.profiles()
                    if b.connectionState is player.ConnectionState.Connected]
        if self.command is PlayCommand.PlayPause:

            if any(backend.state() is player.PlayState.Play for backend in backends):
                # When a single backend is playing, stop all
                for backend in backends:
                    backend.setState(player.PlayState.Pause)
            elif currentBackend:
                # otherwise start only the current one
                currentBackend.setState(player.PlayState.Play)
        elif self.command is PlayCommand.Stop:
            for backend in backends:
                backend.setState(player.PlayState.Stop)
        elif self.command is PlayCommand.AddMark:
            if currentWidget:
                currentWidget.seekSlider.addMark()
        else:
            if currentBackend is None:
                return
            if self.command is PlayCommand.SkipForward:
                currentBackend.skipForward()
            elif self.command is PlayCommand.SkipBackward:
                currentBackend.skipBackward()

for command in PlayCommand:
    PlayControlAction.register(context='playback', identifier=command.value, label=command.label(),
                               shortcut=Qt.Key_Space if command is PlayCommand.PlayPause else None)


class PlaybackWidget(mainwindow.Widget):
    """A dock widget providing playback controls for the selected player backend.
    """
    def __init__(self, state=None, **args):
        super().__init__(**args)
        self.hasOptionDialog = True
        self.backend = None
        self.areaChanged.connect(self._areaChanged)
        
        self.topLayout = QtWidgets.QBoxLayout(QtWidgets.QBoxLayout.TopToBottom)
        self._areaChanged(self.area) # the direction of topLayout depends on the area 
        self.topLayout.setContentsMargins(0,0,0,0)
        self.titleLabel = QtWidgets.QLabel()
        self.titleLabel.setTextFormat(Qt.AutoText)
        self.titleLabel.linkActivated.connect(lambda: self.backend.connectBackend())
        self.topLayout.addWidget(self.titleLabel, 1)  
        
        buttonLayout = QtWidgets.QHBoxLayout()
        buttonLayout.setContentsMargins(0,0,0,0)
        # Do not inhertit spacing from self.topLayout, see self._areaChanged
        buttonLayout.setSpacing(self.style().pixelMetric(QtWidgets.QStyle.PM_LayoutHorizontalSpacing))
        self.topLayout.addLayout(buttonLayout)
        
        self.skipBackwardButton = QtWidgets.QToolButton()
        self.skipBackwardButton.setIcon(QtGui.QIcon(utils.images.renderSvg(renderer, "media_skip_backward",
                                                                           ICON_SIZE, 10)))
        self.ppButton = PlayPauseButton(self)
        self.stopButton = QtWidgets.QToolButton()
        self.stopButton.setIcon(QtGui.QIcon(utils.images.renderSvg(renderer, "media_playback_stop",
                                                                   ICON_SIZE, ICON_SIZE)))
        self.skipForwardButton = QtWidgets.QToolButton()
        self.skipForwardButton.setIcon(QtGui.QIcon(utils.images.renderSvg(renderer, "media_skip_forward",
                                                                          ICON_SIZE, 10)))
        self.volumeButton = VolumeButton()
        
        for button in (self.skipBackwardButton, self.ppButton, self.stopButton,
                       self.skipForwardButton, self.volumeButton):
            button.setAutoRaise(True)
            buttonLayout.addWidget(button)
        buttonLayout.addStretch()
            
        bottomLayout = QtWidgets.QHBoxLayout()
        self.seekLabel = QtWidgets.QLabel("", self)
        self.seekSlider = SeekSlider(self)
        bottomLayout.addWidget(self.seekSlider)
        bottomLayout.addWidget(self.seekLabel)
        mainLayout = QtWidgets.QVBoxLayout(self)
        mainLayout.addLayout(self.topLayout)
        mainLayout.addLayout(bottomLayout)
        self.seekSlider.sliderMoved.connect(self.updateSeekLabel)
        
        levels.real.connect(self.handleLevelChange)
        
    def initialize(self, state=None):
        super().initialize(state)
        if state:
            backend = player.profileCategory.get(state)  # may be None
        elif len(player.profileCategory.profiles()) > 0:
            backend = player.profileCategory.profiles()[0]
        else:
            backend = None
        self.setBackend(backend)
        
    def _areaChanged(self, area):
        """Handle changes in the dock's position."""
        if self.area in ['left', 'right']:
            self.topLayout.setDirection(QtWidgets.QBoxLayout.TopToBottom)
            self.topLayout.setSpacing(self.style().pixelMetric(QtWidgets.QStyle.PM_LayoutVerticalSpacing))
        else:
            self.topLayout.setDirection(QtWidgets.QBoxLayout.RightToLeft)
            self.topLayout.setSpacing(30 + self.style().pixelMetric(QtWidgets.QStyle.PM_LayoutHorizontalSpacing))
    
    def createOptionDialog(self, button=None):
        return OptionDialog(button, self)
    
    def updateSeekLabel(self, value):
        """Display elapsed and total time on the seek label."""
        current = self.backend.current()
        if current is None:
            text = ""
        elif current.element.length > 0:
            text = "{} - {}".format(utils.strings.formatLength(value),
                                    utils.strings.formatLength(self.seekSlider.maximum()))
        else:
            text = utils.strings.formatLength(value)
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
        if self.backend.connectionState == player.ConnectionState.Connected:
            current = self.backend.current()
            if current is not None:
                self.titleLabel.setText(current.getTitle())
            else: self.titleLabel.setText('')
        
    def updateMarks(self):
        """Create and use SliderMarks for the stickers of type 'MARK' of the current song."""
        marks = []
        if self.backend is not None and self.backend.current() is not None:
            stickers = self.backend.current().element.getStickers('MARK')
            if stickers is not None:
                marks = [SliderMark.fromSticker(sticker) for sticker in stickers]
        self.seekSlider.setMarks(marks)
    
    def handleStateChange(self, state):
        """Update labels, buttons etc. when the playback state has changed."""
        self.ppButton.setPlaying(state == player.PlayState.Play)
        if state == player.PlayState.Stop:
            self.updateSlider(0)
            self.seekSlider.setEnabled(False)
        else:
            self.seekSlider.setEnabled(True)
    
    def handleConnectionChange(self, state):
        """Update GUI elements when the connection state has changed."""
        for item in self.skipBackwardButton, self.ppButton, self.stopButton, \
                    self.skipForwardButton, self.seekSlider, self.seekLabel, self.volumeButton:
            item.setEnabled(state is player.ConnectionState.Connected)
        if state is player.ConnectionState.Connecting:
            self.titleLabel.setText(self.tr("connecting..."))
        elif state is player.ConnectionState.Disconnected:
            self.titleLabel.setText(self.tr('Connection failed. <a href="#connect">Retry?</a>'))
        else:
            self.updateTitleLabel()
            self.updateMarks()
            self.updateSlider(self.backend.elapsed())
            self.handleStateChange(self.backend.state())
            self.volumeButton.setVolume(self.backend.volume())

    def handleLevelChange(self, event):
        """Handle changes of the real-level."""
        current = self.backend.current()
        if current is not None and current.element.id in event.dataIds:
            self.updateTitleLabel() # title may have changed
            self.updateMarks()
            
    def handlePlaylistChange(self, *args):
        """Enable or disable play and stop buttons when the playlist becomes empty / is filled."""
        playlistEmpty = len(self.backend.playlist.root.contents) == 0
        self.ppButton.setEnabled(not playlistEmpty)
        self.stopButton.setEnabled(not playlistEmpty) 
               
    def closeEvent(self, event):
        super().closeEvent(event)
        if event.isAccepted():
            # Bugfix: Without this line I usually get errors because handleStateChanged is still called:
            # RuntimeError: wrapped C/C++ object of type SeekSlider has been deleted
            self.setBackend(None)
    
    signals = [ ("self.backend.elapsedChanged", "self.updateSlider"),
                ("self.backend.volumeChanged", "self.volumeButton.setVolume"),
                ("self.backend.stateChanged", "self.handleStateChange"),
                ("self.backend.currentChanged", "self.updateTitleLabel"),
                ("self.backend.currentChanged", "self.updateMarks"),
                ("self.backend.connectionStateChanged", "self.handleConnectionChange"),
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
        if self.backend.connectionState == player.ConnectionState.Connected:
            self.handleConnectionChange(player.ConnectionState.Connected)
        else:
            self.handleConnectionChange(player.ConnectionState.Disconnected)
        self.setWindowTitle("Playback [{}]".format(backend.name))
        self.handlePlaylistChange()
        
    def saveState(self):
        return self.backend.name if self.backend is not None else None

    
mainwindow.addWidgetClass(mainwindow.WidgetClass(
        id = "playback",
        name = translate("Playback", "playback"),
        icon = utils.images.icon('widgets/playback.png'),
        theClass = PlaybackWidget,
        areas = 'dock',
        preferredDockArea = 'left'))


class OptionDialog(dialogs.FancyPopup):
    """Dialog for the option button in the playlist's (dock widget) title bar.""" 
    def __init__(self, parent, playback):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        hLayout = QtWidgets.QHBoxLayout()
        layout.addLayout(hLayout)
        hLayout.addWidget(QtWidgets.QLabel(self.tr("Backend:")))
        backendChooser = profilesgui.ProfileComboBox(player.profileCategory, default=playback.backend)
        backendChooser.profileChosen.connect(playback.setBackend)
        hLayout.addWidget(backendChooser)
        hLayout.addStretch()
        layout.addStretch()
    

class PlayPauseButton(QtWidgets.QToolButton):
    """Special button with two states. Depending on the state different signals (play and pause)
    are emitted when the button is clicked and the button shows different icons."""
    
    # Signals and icons used for the two states
    playIcon = QtGui.QIcon(utils.images.renderSvg(renderer, "media_playback_start", ICON_SIZE, ICON_SIZE))
    pauseIcon = QtGui.QIcon(utils.images.renderSvg(renderer, "media_playback_pause", ICON_SIZE, ICON_SIZE))
    stateChanged = QtCore.pyqtSignal(player.PlayState)
    
    def __init__(self, parent=None):
        """Initialize this button with the given parent. The button will be in pause-state."""
        super().__init__(parent)
        self.setIcon(self.playIcon)
        self.playing = False
        self.clicked.connect(lambda: self.stateChanged.emit(player.PlayState.Pause if self.playing
                                                            else player.PlayState.Play))

    def setPlaying(self, playing):
        """Set the state of this button to play if *playing* is true or pause otherwise."""
        if playing != self.playing:
            self.playing = playing
            self.setIcon(self.pauseIcon if playing else self.playIcon)
        
    
class VolumeButton(QtWidgets.QToolButton):
    """Button displaying an icon that visualizes the current volume. When clicked it opens a popup menu
    that allows to change the volume. Alternatively the volume can be changed using the mouse-wheel.
    The middle mouse button can be used to mute/unmute.
    """
    # Inspired by the VolumePopupButton from Amarok 2.7.1
    volumeChanged = QtCore.pyqtSignal(int)
    
    mutedIcon = QtGui.QIcon.fromTheme('audio-volume-muted')
    lowIcon = QtGui.QIcon.fromTheme('audio-volume-low')
    mediumIcon = QtGui.QIcon.fromTheme('audio-volume-medium')
    highIcon = QtGui.QIcon.fromTheme('audio-volume-high')
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIconSize(QtCore.QSize(24, 24))
        self.setContentsMargins(0,0,0,0)
        
        self.popup = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.popup)
        layout.setContentsMargins(1,1,1,1)
        layout.setSpacing(0)
        self.volumeLabel = QtWidgets.QLabel()
        # Make sure the menu is wide enough to hold all possible values
        self.volumeLabel.setText(self.tr("{}%").format(100))
        self.volumeLabel.setMinimumWidth(self.volumeLabel.sizeHint().width())
        self.volumeLabel.setAlignment(Qt.AlignHCenter)
        layout.addWidget(self.volumeLabel, 0, Qt.AlignHCenter)
        
        self.volumeSlider = VolumeSlider()
        self.volumeSlider.setFixedHeight(170)
        self.volumeSlider.valueChanged.connect(self.setVolume)
        layout.addWidget(self.volumeSlider, 0, Qt.AlignHCenter)
        
        muteButton = QtWidgets.QToolButton()
        muteButton.setIcon(self.mutedIcon)
        muteButton.setIconSize(QtCore.QSize(20, 20))
        muteButton.clicked.connect(self.toggleMute)
        layout.addWidget(muteButton, 0, Qt.AlignHCenter)
        
        self.menu = QtWidgets.QMenu()
        action = QtWidgets.QWidgetAction(self)
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
        req = volume + event.angleDelta().y() // 20
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
        

class VolumeSlider(QtWidgets.QSlider):
    """Special slider used in the menu of VolumeButton."""
    def __init__(self, parent=None):
        super().__init__(Qt.Vertical, parent)
        self.setRange(0, 100)
        
    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        for v in [100, 80, 60, 40, 20, 0]:
            menu.addAction(self.tr("{}%").format(v)).setData(v)
        action = menu.exec_(self.mapToGlobal(event.pos()))
        if action is not None:
            self.setValue(action.data())


class SeekSlider(QtWidgets.QSlider):
    """Fancy seek slider. This is a Python port of the TimeSlider from Amarok 2.7.1."""
    sliderHeight = 14
    knobSize = 14
    
    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setRange(0, 1000)
        self.setFocusPolicy(Qt.NoFocus)
        self.backend = None # backend is necessary to get current track
        self.marks = []
    
    def currentElement(self):
        """Return the currently playing element or None."""
        if self.backend is not None and self.backend.current() is not None:
            return self.backend.current().element
        else: return None
            
    def _posToSeconds(self, pos):
        """Convert from position (0 <= pos < self.width) to seconds."""
        current = self.currentElement()
        return pos / self.width() * current.length if current is not None else None
        
    def _secondsToPos(self, seconds):
        """Convert from seconds to position (0 <= pos < self.width)."""
        current = self.currentElement()
        return int(seconds / current.length * self.width()) if current is not None else None
        
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and not self.isSliderDown():
            self.sliderMoved.emit(int(event.x() / self.width() * self.maximum()))
        return super().mouseReleaseEvent(event)
    
    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setClipRegion(event.region())
        
        fraction = self.value() / self.maximum() if self.maximum() > 0 else 0
        left = int(round((self.width() - self.knobSize) * fraction))
        top = (self.height() - self.sliderHeight) // 2
        knobRect = QtCore.QRect(left, top+1, self.knobSize, self.knobSize)
        
        pt = QtCore.QPoint(0, top)
        p.drawPixmap(pt, utils.images.renderSvg(renderer, "progress_slider_left",
                                                self.sliderHeight, self.sliderHeight))

        pt = QtCore.QPoint(self.sliderHeight, top)
        midRect = QtCore.QRect(pt, QtCore.QSize(self.width() - self.sliderHeight*2, self.sliderHeight))
        p.drawTiledPixmap(midRect, utils.images.renderSvg(renderer, "progress_slider_mid",
                                                          32, self.sliderHeight))
        
        pt = midRect.topRight() + QtCore.QPoint(1, 0)
        p.drawPixmap(pt, utils.images.renderSvg(renderer, "progress_slider_right",
                                                self.sliderHeight, self.sliderHeight))

        # draw the played background.
        playedBarHeight = self.sliderHeight - 6

        sizeOfLeftPlayed = max(0, min(knobRect.x()-2, playedBarHeight))

        if sizeOfLeftPlayed > 0:
            tl = QtCore.QPoint(3, top+4)
            br = QtCore.QPoint(knobRect.x() + 5, tl.y() + playedBarHeight - 1)
            p.drawPixmap(tl.x(), tl.y(), utils.images.renderSvg(renderer, "progress_slider_played_left",
                                                                playedBarHeight, playedBarHeight),
                         0, 0, sizeOfLeftPlayed + 3, playedBarHeight) 
            tl = QtCore.QPoint(tl.x() + playedBarHeight, tl.y())
            if sizeOfLeftPlayed >= playedBarHeight:
                p.drawTiledPixmap(QtCore.QRect(tl, br),
                                  utils.images.renderSvg(renderer, "progress_slider_played_mid",
                                                         32, playedBarHeight))

        if self.isEnabled():
            # Draw the knob (handle)
            if self.underMouse() and knobRect.contains(self.mapFromGlobal(QtGui.QCursor.pos())):
                obj = "slider_knob_200911_active"
            else: obj = "slider_knob_200911"
            p.drawPixmap(knobRect.topLeft(), utils.images.renderSvg(renderer, obj,
                                                                    knobRect.width(), knobRect.height()))
        p.end()
        
    def event(self, event):
        if event.type() == QtCore.QEvent.ToolTip:
            seconds = self._posToSeconds(event.x())
            if seconds is not None:
                self.setToolTip(self.tr("Jump to {}").format(utils.strings.formatLength(seconds)))
            
        return super().event(event)
        
    def setMarks(self, marks):
        """Set the SliderMarks that are displayed on this slider."""
        for widget in self.marks:
            widget.hide()
            widget.setParent(None)
        self.marks = [SliderMarkWidget(mark, self) for mark in marks]
        for widget in self.marks:
            widget.show()
        self._updateMarks()
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._updateMarks()
         
    def _updateMarks(self):
        """Move the SliderMarkWidgets to the correct position."""
        if self.currentElement() is not None:
            for widget in self.marks:
                widget.move(self._secondsToPos(widget.mark.seconds) - SliderMarkWidget.SIZE.width() // 2, 0)
                    
    def contextMenuEvent(self, event):
        if self.currentElement() is not None:
            menu = QtWidgets.QMenu(self)
            markAction = QtWidgets.QAction(self.tr("Add mark..."), menu)
            markAction.triggered.connect(functools.partial(self.addMark, self._posToSeconds(event.x())))
            menu.addAction(markAction)
            removeAllAction = QtWidgets.QAction(self.tr("Remove all marks"), menu)
            removeAllAction.triggered.connect(self.removeAllMarks)
            removeAllAction.setEnabled(len(self.marks) > 0)
            menu.addAction(removeAllAction)
            menu.exec_(event.globalPos())
        event.accept()
        
    def addMark(self, seconds=None):
        """Add a mark to the given position within the current song."""
        current = self.currentElement()
        if current is None:
            return
        if seconds is None:
            seconds = self.backend.elapsed()
        if any(widget.mark.seconds == seconds for widget in self.marks):
            return # do not add two marks at the same time
            
        text = dialogs.getText(self.tr("Mark text"), self.tr("Enter the mark's text:"), self)
        if text is not None:
            data = str(SliderMark(int(seconds), text))
            stickers = current.getStickers('MARK')
            if stickers is not None: # stickers are tuples!
                stickers = stickers + (data, )
            else: stickers = (data, )
            levels.real.setStickers('MARK', {current: stickers}, message=self.tr("Add mark"))
        
    def changeMark(self, seconds):
        """Ask the user to submit a new text for the mark at the given number of seconds."""
        current = self.currentElement()
        if current is None:
            return
        marks = [widget.mark for widget in self.marks]
        for mark in marks:
            if mark.seconds == seconds:
                text = dialogs.getText(self.tr("Mark text"), self.tr("Enter the mark's text:"), self,
                                       default=mark.text)
                if text is not None and text != mark.text:
                    marks = [mark if mark.seconds != seconds else SliderMark(seconds, text)
                             for mark in marks]
                    stickers = [str(mark) for mark in marks]
                    levels.real.setStickers('MARK', {current: stickers}, message=self.tr("Change mark"))
                return
            
    def removeMark(self, seconds):
        """Remove the mark at the given number of seconds."""
        current = self.currentElement()
        if current is None:
            return
        marks = [widget.mark for widget in self.marks if widget.mark.seconds != seconds]
        if len(marks) < len(self.marks):
            stickers = [str(mark) for mark in marks]
            levels.real.setStickers('MARK', {current: stickers}, message=self.tr("Remove mark"))       
        
    def removeAllMarks(self):
        """Remove all marks from the current song."""
        current = self.currentElement()
        if current is not None:
            levels.real.setStickers('MARK', {current: None}, message=self.tr("Remove all marks"))


class SliderMark:
    """A SliderMark is a small text that is displayed (using SliderMarkWidget) at a certain position
    on the SeekSlider."""
    def __init__(self, seconds, text):
        self.seconds = seconds
        self.text = text
        
    def __str__(self):
        return "{};{}".format(self.seconds, self.text)
    
    @staticmethod
    def fromSticker(sticker):
        args, text = sticker.split(';', 1)
        return SliderMark(int(args), text)


class SliderMarkWidget(QtWidgets.QWidget):
    """This widget is used to display SliderMarks on the SeekSlider."""
    SIZE = QtCore.QSize(8, 8)
    
    def __init__(self, mark, parent=None):
        super().__init__(parent)
        self.mark = mark
        self.setToolTip(mark.text + ' ({})'.format(utils.strings.formatLength(mark.seconds)))
        
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.drawPixmap(0, 0, utils.images.renderSvg(renderer, "blue_triangle",
                                                        self.SIZE.width(), self.SIZE.height()))

    def sizeHint(self):
        return self.SIZE
        
    def minimumSizeHint(self):
        return self.SIZE
    
    def sizePolicy(self):
        return QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
    
    def mouseDoubleClickEvent(self, event):
        if self.parent().backend is not None:
            self.parent().backend.setElapsed(self.mark.seconds)
        event.accept()
        
    def contextMenuEvent(self, event):
        backend = self.parent().backend
        if backend is not None and backend.current() is not None:
            menu = QtWidgets.QMenu(self)
            changeAction = QtWidgets.QAction(self.tr("Change text"), menu)
            changeAction.triggered.connect(functools.partial(self.parent().changeMark, self.mark.seconds))
            menu.addAction(changeAction)
            removeAction = QtWidgets.QAction(self.tr("Remove mark"), menu)
            removeAction.triggered.connect(functools.partial(self.parent().removeMark, self.mark.seconds))
            menu.addAction(removeAction)
            menu.exec_(event.globalPos())
        event.accept()
