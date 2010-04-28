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

class State:
    PLAY,PAUSE,STOP = range(0,3)
    
    def fromString(string):
        if string == 'play':
            return PLAY
        elif string == 'pause':
            return PAUSE
        elif string == 'stop':
            return STOP
        raise ValueError("Unknown state")

# A reference to the ControlWidget
widget = None

# The timer used to synchronize with MPD.
timer = QTimer()

def createWidget(parent):
    """Creates a ControlWidget and stores a reference to it in this module."""
    globals()["widget"] = widgetModule.ControlWidget(parent)
    return widget

def startSynchronization():
    timer.timeout.connect(_sync)
    timer.start(int(config.get("control","timer_interval")))
    
def _sync():
    status = mpclient.status()
    widget.setStatus(status)