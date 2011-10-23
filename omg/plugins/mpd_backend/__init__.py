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
class MPDPlayerBackend(player.PlayerBackend):
    
    def __init__(self, name):
        super().__init__(name)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.poll)
        if name in config.storage.mpd.profiles:
            self.connect(**config.storage.mpd.profiles[name])
        else:
            pass#self.connect()
        
            
    def connect(self, host = 'localhost', port = 6600, password = ''):
        print('connect!')
        self.client = mpd.MPDClient()
        self.client.connect(host, port)
        print(self.client.status())
        self.timer.start(200)
        
    def poll(self):
        print('poll!')
        self.mpdStatus = self.client.status()
        newState = MPD_STATES[self.mpdStatus['state']]
        if self.state != newState:
            self.state = newState
            self.stateChanged.emit(newState)
            
        newElapsed = 0 if newState == player.STOP else float(self.mpdStatus['elapsed'])
        if newElapsed != self.elapsed:
            self.elapsed = newElapsed
            self.elapsedChanged.emit(newElapsed)
        

def defaultStorage():
    return {"mpd":
            {'profiles': ({'mpd_local': {'host':'localhost', 'port': 6600, 'password': ''}},) } }

def enable():
    player.playerClasses['mpd'] = MPDPlayerBackend 