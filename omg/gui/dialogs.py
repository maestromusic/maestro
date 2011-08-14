# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from .. import utils


class FancyTabbedPopup(QtGui.QFrame):
    """Fancy popup that looks like a tooltip. It is shown beneath its parent component (usually the button
    that opens the popup) and contains at least one tab.
    """
    
    # The popup will close itself if the user leaves its parent (the button that opened the popup)
    # unless the popup is entered within a short timespan.
    _entered = False
    
    def __init__(self,parent = None):
        QtGui.QFrame.__init__(self,parent)
        self.setWindowFlags(self.windowFlags() | Qt.ToolTip)
        parent.installEventFilter(self)
        
        # Create components
        self.setLayout(QtGui.QVBoxLayout())
        self.tabWidget = QtGui.QTabWidget(self)
        self.tabWidget.setDocumentMode(True)
        self.layout().addWidget(self.tabWidget)
        
        closeButton = QtGui.QToolButton()
        closeButton.setIcon(utils.getIcon('close_button.png'))
        closeButton.setStyleSheet(
            "QToolButton { border: None; margin-bottom: 1px; } QToolButton:hover { border: 1px solid white; }")
        closeButton.clicked.connect(self.close)
        self.tabWidget.setCornerWidget(closeButton)
        
        # Fancy design code
        self.setAutoFillBackground(True)
        self.setFrameStyle(QtGui.QFrame.Box | QtGui.QFrame.Plain);
        self.setLineWidth(1);
        p = self.palette()
        p.setColor(QtGui.QPalette.Window,p.window().color().lighter(105))
        # Unbelievably this is used for the border...
        p.setColor(QtGui.QPalette.WindowText, Qt.darkGray)
        self.setPalette(p)
        
        # Therefore we also have to change the palette of tabWidget so that the font is rendered normally.
        p = self.tabWidget.palette()
        p.setBrush(QtGui.QPalette.WindowText,self.parent().palette().windowText())
        self.tabWidget.setPalette(p)
        
        effect = QtGui.QGraphicsDropShadowEffect()
        effect.setOffset(0,0)
        effect.setBlurRadius(20)
        self.setGraphicsEffect(effect)
        
        # Move to correct position
        pos = self.parent().mapToGlobal(QtCore.QPoint(0,self.parent().height()))
        #TODO: It would be nice to ensure that the window does not leave the screen.
        # Unfortunately there seems to be no way to get the correct size prior to showing the dialog.
        self.move(pos)
    
    def close(self):
        self.parent().removeEventFilter(self)
        QtGui.QFrame.close(self)
    
    def enterEvent(self,event):
        self._entered = True
        QtGui.QFrame.enterEvent(self,event)
    
    def leaveEvent(self,event):
        if self.isVisible():
            self.close()
             
    def eventFilter(self,object,event):
        if event.type() == QtCore.QEvent.Leave:
            QtCore.QTimer.singleShot(100,self._handleTimer)
        return False
        
    def _handleTimer(self):
        # Close the window shortly after the parent has been left by the cursor unless the cursor has
        # entered the popup in the meantime.
        if not self._entered:
            self.close()
        