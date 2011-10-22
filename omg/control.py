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

import logging

from PyQt4.QtCore import QTimer
from . import mpclient
from omg.config import options

# A reference to the ControlWidget
widget = None

# The playlist which is synchronized with MPD.
playlist = None

# The timer used to synchronize with MPD.
_timer = QTimer()

# Status of MPD
status = None

logger = logging.getLogger("omg.control")

def createWidget(parent = None):
    """Create a ControlWidget and store a reference to it in control.widget."""
    from omg.gui import control as controlwidget
    globals()["widget"] = controlwidget.ControlWidget(parent)
    return widget

def synchronizePlaylist(playlist):
    """Start synchronization between MPD and the given playlist. This method also calls the playlist's startSynchronizatin-method and the stopSynchronization-method of the last playlist which was synchronized."""
    playlist.startSynchronization()
    oldPlaylist = globals()["playlist"]
    globals()["playlist"] = playlist
    if oldPlaylist is not None:
        oldPlaylist.stopSynchronization()
    else: # Start Timer for the first time
        _timer.timeout.connect(_sync)
        _timer.start(options.control.timer_interval)
        
    _sync() # Synchronize right away. In particular this is useful when the timer-interval is large for debugging.

def stopSynchronization():
    if playlist is not None:
        playlist.stopSynchronization()
    _timer.stop()
    globals()["playlist"] = None
    
def _sync():
    """Synchronize playlist and widget with MPD."""
    global status
    if _timer.interval() >= 1000: #TODO: Remove this debugging feature
        print("Control: Syncing with MPD")
    try:
        status = mpclient.status()
        widget.setStatus(status)
        playlist.synchronize(mpclient.playlist(),status)
    except mpclient.CommandError as e:
        logger.critical("Synchronization with MPD failed and was stopped. Error Message: "+e.message())
        stopSynchronization()
        status = None