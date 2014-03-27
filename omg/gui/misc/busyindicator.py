# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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


class BusyIndicator(QtGui.QWidget):
    """Displays an animation to indicate that some work is done. Based on the file process-working.png
    from the Tange icon gallery: http://tango.freedesktop.org/Tango_Icon_Library
    """
    def __init__(self):
        super().__init__()
        
        self.setMinimumSize(32,32)
        self.setMaximumSize(32,32)
        
        self._frame = None
        
        # Have a look at that image to understand this code  
        self._pixmap = QtGui.QPixmap(':omg/process-working.png')
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._handleTimer)
            
    def setInterval(self,interval):
        """Set the interval of the animation."""
        self._timer.setInterval(interval)
    
    def start(self):
        """Start the animation."""
        if not self._timer.isActive():
            self._frame = 0
            self.update()
            self._timer.start()
        
    def stop(self):
        """Stop the animation. Effectively this will hide the indicator."""
        if self._timer.isActive():
            self._frame = None
            self.update()
            self._timer.stop()
        
    def setRunning(self,running):
        """Set whether this animation should be running or not."""
        if running:
            self.start()
        else: self.stop()
        
    def _handleTimer(self):
        """React to the internal timer."""
        if self._frame is None:
            return
        self._frame += 1
        if self._frame == 32:
            self._frame = 1 # skip frame 0 which contains an empty pixmap
        self.update()
        
    def paintEvent(self,event):
        if self._frame is not None:
            x = 32 * (self._frame % 8)
            y = 32 * (self._frame // 8)
            painter = QtGui.QPainter(self)
            painter.drawPixmap(0,0,self._pixmap,x,y,32,32)
        
        
class BusyLabel(QtGui.QWidget):
    """This widget combines a BusyIndicator with a text. Like the BusyIndicator, it will only be visible
    when running."""
    def __init__(self,text):
        super().__init__()
        layout = QtGui.QHBoxLayout(self)
        self.busyIndicator = BusyIndicator()
        layout.addWidget(self.busyIndicator)
        self.stackLayout = QtGui.QStackedLayout()
        layout.addLayout(self.stackLayout)
        self.stackLayout.addWidget(QtGui.QWidget())
        self.label = QtGui.QLabel(text)
        self.stackLayout.addWidget(self.label)
        
    def setInterval(self,interval):
        """Set the interval of the animation."""
        self.busyIndicator.setInterval(interval)
    
    def start(self):
        """Start the animation."""
        self.busyIndicator.start()
        self.stackLayout.setCurrentIndex(1)
        
    def stop(self):
        """Stop the animation. Effectively this will hide the indicator."""
        self.busyIndicator.stop()
        self.stackLayout.setCurrentIndex(0)

    def setRunning(self,running):
        """Set whether this label should be busy or not."""
        if running:
            self.start()
        else: self.stop()
        