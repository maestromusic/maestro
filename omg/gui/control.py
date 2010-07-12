#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import SIGNAL
from omg import constants, mpclient, strutils
from omg import control as controlModule
from omg.models import playlist
import mpd
import logging

logger = logging.getLogger("gui.control")

class ControlWidget(QtGui.QWidget):
    """Widget providing buttons to control a music player."""
    
    # Maximal value for the seekSlider
    SEEK_SLIDER_MAX = 1000
    
    # Time information of the currently played song.
    time = None
    
    def __init__(self,parent):
        """Initialize this ControlWidget with the given parent."""
        QtGui.QWidget.__init__(self,parent)
        
        # Layout
        layout = QtGui.QVBoxLayout()
        self.setLayout(layout)
        firstLine = QtGui.QHBoxLayout()
        secondLine = QtGui.QHBoxLayout()
        layout.addLayout(firstLine)
        layout.addLayout(secondLine)
        
        # Controls in the first line
        self.previousButton = QtGui.QPushButton(QtGui.QIcon(constants.IMAGES+"icons/previous.png"),'',self)
        self.ppButton = PPButton(self)
        self.stopButton = QtGui.QPushButton(QtGui.QIcon(constants.IMAGES+"icons/stop.png"),'',self)
        self.nextButton = QtGui.QPushButton(QtGui.QIcon(constants.IMAGES+"icons/next.png"),'',self)
        self.firstLabel = QtGui.QLabel(self)
        self.secondLabel = QtGui.QLabel(self)
        
        self.seekSlider = QtGui.QSlider(QtCore.Qt.Horizontal,self)
        self.seekSlider.setRange(0,self.SEEK_SLIDER_MAX)
        self.seekSlider.setTracking(False)
        self.seekSlider.actionTriggered.connect(self._handleSeekSliderAction)
        
        self.previousButton.clicked.connect(self._handlePrevious)
        self.ppButton.play.connect(mpclient.play)
        self.ppButton.pause.connect(mpclient.pause)
        self.stopButton.clicked.connect(self._handleStop)
        self.nextButton.clicked.connect(self._handleNext)
        
        for widget in (self.previousButton,self.ppButton,self.stopButton,self.nextButton,self.firstLabel):
            firstLine.addWidget(widget)
        firstLine.addWidget(self.seekSlider,1)
        firstLine.addWidget(self.secondLabel)
        
        # Controls in the second line
        self.titleLabel = QtGui.QLabel(self)
        self.volumeLabel = VolumeLabel(self)
        self.volumeLabel.clicked.connect(self.toggleMute)
        self.volumeSlider = QtGui.QSlider(QtCore.Qt.Horizontal,self)
        self.volumeSlider.setRange(0,100)
        self.volume = 50
        self.volumeSlider.actionTriggered.connect(self._handleVolumeSliderAction)
        self.muted = False
        self.time = None
        
        secondLine.addWidget(self.titleLabel,1)
        secondLine.addWidget(self.volumeLabel)
        secondLine.addWidget(self.volumeSlider)
        
        #TODO: This button just helps debugging
        from omg import test
        testButton = QtGui.QPushButton("Test")
        testButton.clicked.connect(test.test)
        secondLine.addWidget(testButton)


    def setStatus(self,status):
        """Sets all controls in this widget to reflect the given status (which should be returned by mpclient.status())."""
        self.ppButton.setPlaying(status['state'] == 'play')
        if 'time' in status:
            if self.time != status['time']:
                self.time = status['time']
                self.firstLabel.setText(strutils.formatLength(self.time.getElapsed()))
                self.secondLabel.setText("-"+strutils.formatLength(self.time.getRemaining()))
                # Don't move the slider, if the user presses it down to move it personally.
                if not self.seekSlider.isSliderDown():
                    self.seekSlider.setValue(int(self.SEEK_SLIDER_MAX * self.time.getRatio()))
            
            element = controlModule.playlist.currentlyPlayingElement
            if element is not None: # This may happen when the playlist has not been synchronized already.
                if isinstance(element,playlist.ExternalFile):
                    title = element.getPath()
                else: title = element.getTitle()
                if self.titleLabel.text() != title:
                    font = self.titleLabel.font()
                    font.setPixelSize(14)
                    font.setBold(True)
                    font.setItalic(isinstance(element,playlist.ExternalFile))
                    self.titleLabel.setFont(font)
                    self.titleLabel.setText(title)
            if not self.volumeSlider.isSliderDown():
                self.volumeLabel.setVolume(status['volume'])
                self.volumeSlider.setValue(status['volume'])
                if status['volume'] == 0:
                    self.muted = True
            
                
        else: # Currently nothing is playing
            self.time = None
            self.firstLabel.setText('')
            self.secondLabel.setText('')
            self.seekSlider.setValue(0)
            self.titleLabel.setText('')
    
    def setVolume(self, volume):
        if volume == -1 or self.time == None:
            return
        #logger.debug("setting volume to {}".format(volume))
        self.volumeLabel.setVolume(volume)
        self.volumeSlider.setValue(volume)
        try:
            mpclient.setvol(str(volume))
        except mpd.CommandError as e:
            print(e)
            logger.warning("problem setting volume")
            print(str(volume))
        if volume > 0:
            self.muted = False
        
    def toggleMute(self):
        """Toggles the muting state of the player."""
        if self.muted:
            self.muted = False
            self.setVolume(self.volume)
        else:
            # don't call setVolume here to avoid loops
            self.muted = True
            self.setVolume(0)
        
    def _handlePrevious(self,checked=False):
        """Handle the click on self.previousButton."""
        mpclient.previous()
        
    def _handleNext(self,checked=False):
        """Handle the click on self.nextButton."""
        mpclient.next()
        
    def _handleStop(self,checked=False):
        """Handle the click on self.stopButton."""
        mpclient.stop()
        
    def _handleSeekSliderAction(self,action):
        """Handle any change of the seekSlider."""
        if self.time is not None: # i.e. some music file is playing at the moment
            mpclient.seek(controlModule.status['song'],
                           int(self.seekSlider.sliderPosition() / self.SEEK_SLIDER_MAX * self.time.getTotal()))

    def _handleVolumeSliderAction(self,action):
        """Handle any change of the volumeSlider."""
        # mpclient.volume adds its parameter to the volume...so we pass the difference between new and old slider value:
        if self.time != None:
            vol = self.volumeSlider.sliderPosition()
            mpclient.setvol(vol)
            self.volume = vol
    

        
class PPButton(QtGui.QPushButton):
    """Special button with two states. Depending on the state different signals (play and pause) are emitted when the button is clicked and the button shows different icons."""
    
    # Signals and icons used for the two states
    play = QtCore.pyqtSignal()
    pause = QtCore.pyqtSignal()
    playIcon = QtGui.QIcon(constants.IMAGES+"icons/play.png")
    pauseIcon = QtGui.QIcon(constants.IMAGES+"icons/pause.png")
    
    def __init__(self,parent):
        """Initialize this button with the given parent. The button will be in pause-state."""
        QtGui.QPushButton.__init__(self,self.playIcon,'',parent)
        self.playing = False
        self.clicked.connect(self._handleClicked)

    def _handleClicked(self,checked = False):
        """Handle a click on the button."""
        if self.playing:
            self.pause.emit()
        else: self.play.emit()
        # Do NOT change self.playing! The flag will be changed, when a change in mpd's status is detected.

    def setPlaying(self,playing):
        """Set the state of this button to play if <playing> is true or pause otherwise."""
        if playing != self.playing:
            self.playing = playing
            self.setIcon(self.pauseIcon if playing else self.playIcon)


class VolumeLabel(QtGui.QLabel):
    """Special label displaying the icon next to the volumeSlider. The icon which is shown depends on the current volume level."""
    
    clicked = QtCore.pyqtSignal()
    
    def __init__(self,parent):
        """Initialize this label with the given parent."""
        QtGui.QLabel.__init__(self,parent)
        self.state = 'muted'
        self.setPixmap(QtGui.QPixmap(constants.IMAGES+"icons/volume_muted.png"))
    
    def setVolume(self,volume):
        """Display the icon appropriate for the given volume."""
        range = VolumeLabel.volumeRange(volume)
        if range != self.state:
            self.state = range
            self.setPixmap(QtGui.QPixmap(constants.IMAGES+"icons/volume_{}.png".format(range)))

    @staticmethod
    def volumeRange(volume):
        """Maps the given volume to a string from {muted,low,medium,high}"""
        if volume == 0:
            return 'muted'
        elif volume <= 33:
            return 'low'
        elif volume <= 66:
            return 'medium'
        else:
            return 'high'
        
    def mousePressEvent(self, event):
        self.clicked.emit()
        