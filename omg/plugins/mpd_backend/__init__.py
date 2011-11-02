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

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from omg import player, config
import mpd

MPD_STATES = { 'play': player.PLAY, 'stop': player.STOP, 'pause': player.PAUSE}

class MPDThread(QtCore.QThread):
    
    def __init__(self, playerInstance, host, port, password = ''):
        super().__init__()
        self.host = host
        self.port = port
        self.password = password
        self.state = player.STOP
        self.elapsed = 0
        self.player = playerInstance
        self.start()
        
    def run(self):
        print('run!')
        self.client = mpd.MPDClient()
        self.client.connect(self.host, self.port)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.poll)
        self.timer.start(50)
        self.exec_()
        print('wtf')
        
    def poll(self):
        #print('poll!(threaded)')
        self.mpdStatus = self.client.status()
        newState = MPD_STATES[self.mpdStatus['state']]
        self.currentSongInfo = self.client.currentsong()
        if self.state != newState:
            self.state = newState
            self.player.stateChanged.emit(newState)
            
        newElapsed = 0 if newState == player.STOP else float(self.mpdStatus['elapsed'])
        if newElapsed != self.elapsed:
            self.elapsed = newElapsed
            self.player.elapsedChanged.emit(newElapsed, int(self.currentSongInfo['time']))
            
    def setElapsed(self, time):
        self.client.seek(self.mpdStatus['song'], time)
 
    def setState(self, state):
        if state == player.PLAY:
            self.client.play()
        elif state == player.PAUSE:
            self.client.pause()
        elif state == player.STOP:
            self.client.stop()       
class MPDPlayerBackend(player.PlayerBackend):
    
    def __init__(self, name):
        super().__init__(name)
        
        self.host = "unspecified"
        self.port = 6600
        if name in config.storage.mpd.profiles:
            self.connect(**config.storage.mpd.profiles[name])
        self.thread = MPDThread(self, self.host, self.port)
        self.setElapsed = self.thread.setElapsed
        self.setState = self.thread.setState
            
    def connect(self, host = 'localhost', port = 6600, password = ''):
        print('connect!')
        self.host = host
        self.port = port
        

        
    def __str__(self):
        return "MPDPlayerBackend(host={},port={})".format(self.host, self.port)
def defaultStorage():
    return {"mpd":
            {'profiles': ({'mpd_local': {'host':'localhost', 'port': 6600, 'password': ''}},) } }

def enable():
    player.playerClasses['mpd'] = MPDPlayerBackend 