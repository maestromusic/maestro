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

class ControlWidget(QtGui.QWidget):
    SLIDER_MAX = 1000
    
    # Storing time information of the currently played song.
    time = None
    
    def __init__(self,parent):
        QtGui.QWidget.__init__(self,parent)
        
        layout = QtGui.QVBoxLayout()
        self.setLayout(layout)
        firstLine = QtGui.QHBoxLayout()
        secondLine = QtGui.QHBoxLayout()
        layout.addLayout(firstLine)
        layout.addLayout(secondLine)
        
        self.previousButton = QtGui.QPushButton(QtGui.QIcon(constants.IMAGES+"icons/previous.png"),'',self)
        self.ppButton = PPButton(self)
        self.stopButton = QtGui.QPushButton(QtGui.QIcon(constants.IMAGES+"icons/stop.png"),'',self)
        self.nextButton = QtGui.QPushButton(QtGui.QIcon(constants.IMAGES+"icons/next.png"),'',self)
        self.firstLabel = QtGui.QLabel(self)
        self.secondLabel = QtGui.QLabel(self)
        
        self.seekSlider = QtGui.QSlider(QtCore.Qt.Horizontal,self)
        self.seekSlider.setRange(0,self.SLIDER_MAX)
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
        
        self.titleLabel = QtGui.QLabel(self)
        self.volumeLabel = VolumeLabel(self)
        self.volumeSlider = QtGui.QSlider(QtCore.Qt.Horizontal,self)
        self.volumeSlider.setRange(0,100)
        self.volumeSlider.actionTriggered.connect(self._handleVolumeSliderAction)
        
        secondLine.addWidget(self.titleLabel,1)
        secondLine.addWidget(self.volumeLabel)
        secondLine.addWidget(self.volumeSlider)


    def setStatus(self,status):
        self.ppButton.setPlaying(status['state'] == 'play')
        if 'time' in status:
            if self.time != status['time']:
                self.time = status['time']
                self.firstLabel.setText(strutils.formatLength(self.time.getElapsed()))
                self.secondLabel.setText("-"+strutils.formatLength(self.time.getRemaining()))
                # Don't move the slider, if the user presses it down to move it personally.
                if not self.seekSlider.isSliderDown():
                    self.seekSlider.setValue(int(self.SLIDER_MAX * self.time.getRatio()))
        else:
            self.time = None
            self.firstLabel.setText('')
            self.secondLabel.setText('')
            self.seekSlider.setValue(0)
        
        self.volumeLabel.setVolume(status['volume'])
        self.volumeSlider.setValue(status['volume'])
    
    def _handlePrevious(self,checked=False):
        mpclient.previous()
        
    def _handleNext(self,checked=False):
        mpclient.next()
        
    def _handleStop(self,checked=False):
        mpclient.stop()
        
    def _handleSeekSliderAction(self,action):
        if self.time is not None:
            mpclient.seek(0,int(self.seekSlider.sliderPosition() / self.SLIDER_MAX * self.time.getTotal()))

    def _handleVolumeSliderAction(self,action):
        # mpcline.volume adds its parameter to the volume...so we pass the difference between old and new slider value:
        mpclient.volume(self.volumeSlider.sliderPosition()-self.volumeSlider.value())

        
class PPButton(QtGui.QPushButton):
    play = QtCore.pyqtSignal()
    pause = QtCore.pyqtSignal()
    playIcon = QtGui.QIcon(constants.IMAGES+"icons/play.png")
    pauseIcon = QtGui.QIcon(constants.IMAGES+"icons/pause.png")
    
    def __init__(self,parent):
        QtGui.QPushButton.__init__(self,self.playIcon,'',parent)
        self.playing = False
        self.clicked.connect(self._handleClicked)

    def _handleClicked(self,checked = False):
        if self.playing:
            self.pause.emit()
        else: self.play.emit()
        # Do NOT change self.playing! The flag will be changed, when a change in mpd's status is detected.

    def setPlaying(self,playing):
        if playing != self.playing:
            self.playing = playing
            self.setIcon(self.pauseIcon if playing else self.playIcon)


class VolumeLabel(QtGui.QLabel):
    def __init__(self,parent):
        QtGui.QLabel.__init__(self,parent)
    
    def setVolume(self,volume):
        if volume == 0:
            self.setPixmap(QtGui.QPixmap(constants.IMAGES+"icons/volume_muted.png"))
        elif volume <= 33:
            self.setPixmap(QtGui.QPixmap(constants.IMAGES+"icons/volume_low.png"))
        elif volume <= 66:
            self.setPixmap(QtGui.QPixmap(constants.IMAGES+"icons/volume_medium.png"))
        else: self.setPixmap(QtGui.QPixmap(constants.IMAGES+"icons/volume_high.png"))