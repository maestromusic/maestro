#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4.QtCore import QTimer
from omg import config, mpclient
from . import widget as widgetModule
from . import syncplaylist

# A reference to the ControlWidget
widget = None

# The playlist which is synchronized with MPD.
playlist = syncplaylist.Playlist()

# The timer used to synchronize with MPD.
_timer = QTimer()

def createWidget(parent):
    """Create a ControlWidget and store a reference to it in this control.widget."""
    globals()["widget"] = widgetModule.ControlWidget(parent)
    return widget

def startSynchronization():
    """Start synchronization with MPD."""
    _timer.timeout.connect(_sync)
    _timer.start(int(config.get("control","timer_interval")))
    _sync() # Synchronize right away. In particular this is useful when the timer-interval is large for debugging.
    
def _sync():
    """Synchronize playlist and widget with MPD."""
    if _timer.interval() >= 1000: #TODO: Remove this debugging feature
        print("Control: Syncing with MPD")
    widget.setStatus(mpclient.status())
    playlist.synchronize(mpclient.playlist())